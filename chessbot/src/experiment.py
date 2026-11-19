"""Batch experiment runner for ChessMind (B's experiment module).

Run G1-G5 matches using the existing GameController and C's engine API.
The output CSV has exactly the 14 columns required by project section 2.6.

Example (from the chessbot directory)::

    from src.experiment import ExperimentRunner
    runner = ExperimentRunner("G1", games=2, seed=42)
    print(runner.run(on_progress=lambda p: print(p["completed"], p["total"])))

The UI should run ``runner.run()`` on a worker thread and send callbacks to
Tkinter's main thread via ``queue.Queue`` (do not change Tk widgets directly
from this worker). A threading.Event passed to ``stop_event`` stops *between*
games; each finished game's CSV row is flushed before the next one begins.
"""

from __future__ import annotations

import csv
from copy import deepcopy
from hashlib import sha256
from pathlib import Path
import random
from typing import Callable, Sequence

# The official 14-column data contract; do not rename fields without team A/F.
CSV_FIELDS = (
    "game_id", "group", "white", "black", "depth_w", "depth_b", "result",
    "plies", "nodes_w", "nodes_b", "ms_w", "ms_b", "seed", "error",
)

# Keep the official 14-column CSV unchanged. A companion CSV carries the
# separate termination reason already returned by GameController.get_summary().
# Old results without a companion record are classified as "unknown", NEVER
# retroactively guessed to be a rules draw or a ply-limit truncation.
TERMINATION_FIELDS = (
    "group", "seed", "game_id", "result", "plies", "termination",
)
KNOWN_TERMINATIONS = {"rules", "ply_limit", "engine_error"}

GROUP_PAIRS = {
    "G1": ("L1", "L2"),
    "G2": ("L2", "L3"),
    "G3": ("L3", "MCTS"),
    "G4": ("NOAB", "AB"),
    "G5": ("MATERIAL", "POSITION"),
}

# Five different, legal and fixed opening prefixes. Alternate colors for each
# *pair* of matches so engines see the same position from opposite sides.
OPENING_LINES = (
    ("e2e4", "e7e5"),
    ("d2d4", "d7d5"),
    ("c2c4", "e7e5"),
    ("g1f3", "d7d5"),
    ("e2e4", "c7c5"),
)


def _five_opening_fens() -> tuple[str, ...]:
    import chess

    positions = []
    for line in OPENING_LINES:
        board = chess.Board()
        for move in line:
            board.push_uci(move)
        positions.append(board.fen())
    return tuple(positions)


def _stable_match_seed(seed: int, group: str, game_id: int) -> int:
    # Python's built-in hash() is process-randomized. SHA256 is stable.
    raw = f"ChessMind|{seed}|{group}|{game_id}".encode("utf-8")
    return int.from_bytes(sha256(raw).digest()[:8], "big")


def _material_only(board) -> int:
    """White-perspective material-only baseline for G5; no position terms."""
    import chess

    values = {chess.PAWN: 100, chess.KNIGHT: 320, chess.BISHOP: 330,
              chess.ROOK: 500, chess.QUEEN: 900}
    return sum(
        value * (len(board.pieces(piece, chess.WHITE)) -
                 len(board.pieces(piece, chess.BLACK)))
        for piece, value in values.items()
    )


def _build_default_engine(label: str):
    """Assemble only; never alter C's search or D's evaluation code."""
    from .engine import build_engine

    if label in {"L1", "L2", "L3", "MCTS"}:
        return build_engine(label)

    from .config_loader import load_config
    cfg = deepcopy(load_config())
    # G4: same depth and evaluation; ONLY pruning differs, no ordering aid.
    # G5: same search settings; ONLY evaluation function differs.
    levels = cfg.setdefault("levels", {})
    baseline = deepcopy(levels.get("L2", {}))
    baseline.update(depth=3, use_ordering=False, use_cache=False,
                    use_quiescence=False)
    if label in ("AB", "NOAB"):
        baseline["use_pruning"] = label == "AB"
        levels["L2"] = baseline
        return build_engine("L2", cfg=cfg)

    if label in ("MATERIAL", "POSITION"):
        baseline["use_pruning"] = True
        levels["L2"] = baseline
        if label == "MATERIAL":
            evaluator = _material_only
        else:
            # Explicitly require D's evaluation implementation. Using C's
            # fallback here would invalidate the G5 scientific comparison.
            try:
                from .evaluate import evaluate as d_evaluate
            except ImportError as exc:
                raise RuntimeError(
                    "G5 requires D's chessbot/src/evaluate.py. "
                    "Integrate D's module and verify its scoring contract first."
                ) from exc

            def evaluator(board):
                # D returns side-to-move scores; C expects white-perspective.
                score = d_evaluate(board)
                return score if board.turn else -score

        return build_engine("L2", cfg=cfg, evaluator=evaluator)

    raise ValueError("Unknown engine label: %s" % label)


class ExperimentRunner:
    """Run a paired batch, append one result row per completed game.

    Args:
        group: G1, G2, G3, G4 or G5.
        games: Number of games for this group (default 20).
        seed: Reproducible opening order and global random seed per match.
        output_csv: CSV path relative to current working directory.
        max_plies: Safety cap passed to GameController (default 200).
        time_limit: Optional seconds passed to each engine's choose().
        timeout_seconds: Optional post-return overrun check for each move.
        opening_fens: Override opening positions (mainly for testing).
        engine_factory: Optional callable(label)->engine (testing/integration).
        game_factory: Optional GameController-compatible factory.

    NOTE: A fixed seed guarantees the opening order and global RNG seeds, NOT
    byte-identical elapsed-time metrics. Exact game replay additionally needs
    deterministic engines and fixed search budgets. C's time cutoffs can vary
    across hardware; D's MCTS may use its own independent RNG.
    """

    def __init__(
        self,
        group: str,
        games: int = 20,
        seed: int = 42,
        output_csv: str | Path = "experiments/results/results.csv",
        *,
        max_plies: int = 200,
        time_limit: float | None = None,
        timeout_seconds: float | None = None,
        opening_fens: Sequence[str] | None = None,
        engine_factory: Callable | None = None,
        game_factory: Callable | None = None,
    ) -> None:
        self.group = str(group).upper().strip()
        if self.group not in GROUP_PAIRS:
            raise ValueError("group must be G1, G2, G3, G4, or G5")
        for name, value in (("games", games), ("max_plies", max_plies)):
            if not isinstance(value, int) or isinstance(value, bool) or value < 1:
                raise ValueError("%s must be a positive integer" % name)
        if not isinstance(seed, int) or isinstance(seed, bool):
            raise ValueError("seed must be an integer")
        if time_limit is not None and time_limit <= 0:
            raise ValueError("time_limit must be positive")
        if timeout_seconds is not None and timeout_seconds <= 0:
            raise ValueError("timeout_seconds must be positive")
        if opening_fens is not None and (not opening_fens or
            any(not isinstance(f, str) or not f for f in opening_fens)):
            raise ValueError("opening_fens must be nonempty FEN strings")

        self.games = games
        self.seed = seed
        self.output_csv = Path(output_csv)
        self.termination_csv = self.output_csv.with_name(
            self.output_csv.stem + "_termination.csv"
        )
        self.max_plies = max_plies
        self.time_limit = time_limit
        self.timeout_seconds = timeout_seconds
        self.opening_fens = tuple(opening_fens) if opening_fens is not None else None
        self.engine_factory = engine_factory or _build_default_engine
        self.game_factory = game_factory

    def _positions(self) -> tuple[str, ...]:
        positions = self.opening_fens or _five_opening_fens()
        order = list(positions)
        random.Random(self.seed).shuffle(order)
        return tuple(order)

    def _pair(self, game_id: int) -> tuple[str, str]:
        a, b = GROUP_PAIRS[self.group]
        return (a, b) if game_id % 2 else (b, a)

    def _read_existing(self) -> dict[int, dict]:
        """Read only this group's rows with this seed; reject duplicates."""
        if not self.output_csv.exists() or self.output_csv.stat().st_size == 0:
            return {}
        with self.output_csv.open("r", encoding="utf-8-sig", newline="") as f:
            reader = csv.DictReader(f)
            if tuple(reader.fieldnames or ()) != CSV_FIELDS:
                raise ValueError("CSV header is incompatible with the 14-column project format")
            existing = {}
            for row in reader:
                if row["group"] != self.group or row["seed"] != str(self.seed):
                    continue
                try:
                    game_id = int(row["game_id"])
                except (TypeError, ValueError) as exc:
                    raise ValueError("CSV contains an invalid game_id") from exc
                if game_id < 1 or game_id > self.games or game_id in existing:
                    raise ValueError("CSV has duplicate/out-of-range game_id for this batch")
                if (row["white"], row["black"]) != self._pair(game_id):
                    raise ValueError("CSV has a conflicting matchup for game %s" % game_id)
                existing[game_id] = row
        return existing

    def _read_termination_audit(self, existing: dict[int, dict]) -> dict[int, str]:
        """Read companion rows for this batch, validating the matching result.

        A pre-existing main CSV without audit data is supported for resume, but
        those games have *unknown* termination. Never infer the cause from 200
        plies (a rules result can legitimately happen at that same ply count).
        """
        if (not self.termination_csv.exists() or
                self.termination_csv.stat().st_size == 0):
            return {}
        found: dict[int, str] = {}
        with self.termination_csv.open("r", encoding="utf-8-sig", newline="") as f:
            reader = csv.DictReader(f)
            if tuple(reader.fieldnames or ()) != TERMINATION_FIELDS:
                raise ValueError("termination audit CSV header is incompatible")
            for row in reader:
                if row["group"] != self.group or row["seed"] != str(self.seed):
                    continue
                try:
                    game_id = int(row["game_id"])
                except (TypeError, ValueError) as exc:
                    raise ValueError("termination audit contains invalid game_id") from exc
                if game_id in found:
                    raise ValueError("duplicate termination audit record")
                main = existing.get(game_id)
                if main is None:
                    raise ValueError("orphan termination audit record: no matching result row")
                if row["result"] != main["result"] or row["plies"] != main["plies"]:
                    raise ValueError("termination audit disagrees with results CSV")
                termination = row["termination"]
                if termination not in KNOWN_TERMINATIONS | {"unknown"}:
                    raise ValueError("invalid termination audit value")
                found[game_id] = termination
        return found

    def _append_termination(self, row: dict, reason: str) -> None:
        """Append a separate audit row without changing the 14-column format."""
        audit = {
            "group": row["group"],
            "seed": row["seed"],
            "game_id": row["game_id"],
            "result": row["result"],
            "plies": row["plies"],
            "termination": reason,
        }
        self.termination_csv.parent.mkdir(parents=True, exist_ok=True)
        new_file = (not self.termination_csv.exists() or
                    self.termination_csv.stat().st_size == 0)
        with self.termination_csv.open("a", encoding="utf-8", newline="") as f:
            writer = csv.DictWriter(f, fieldnames=TERMINATION_FIELDS)
            if new_file:
                writer.writeheader()
            writer.writerow(audit)
            f.flush()

    def _run_one(self, game_id: int, opening_fen: str) -> dict:
        white, black = self._pair(game_id)
        # C/D may use global random: seed separately for each game, then restore
        # to avoid surprising users' main-thread RNG. Do not run concurrent
        # ExperimentRunners sharing process-global random state.
        state = random.getstate()
        random.seed(_stable_match_seed(self.seed, self.group, game_id))
        try:
            white_engine = self.engine_factory(white)
            black_engine = self.engine_factory(black)
            if self.game_factory is None:
                from .game import GameController
                game_factory = GameController
            else:
                game_factory = self.game_factory
            game = game_factory(white_engine, black_engine,
                                fen=opening_fen, max_plies=self.max_plies)
            result = game.run_ai_vs_ai(time_limit=self.time_limit,
                                       timeout_seconds=self.timeout_seconds)
            records = game.move_records
        finally:
            random.setstate(state)

        if result.get("result") not in ("1-0", "0-1", "1/2-1/2"):
            raise RuntimeError("Game did not return a final result")
        white_moves = (m for m in records if m["color"] == "white")
        black_moves = (m for m in records if m["color"] == "black")
        depth_w = max((int(m["depth"]) for m in white_moves), default=0)
        depth_b = max((int(m["depth"]) for m in black_moves), default=0)
        # An internal key only: removed before writing the official CSV.
        # Fake/custom game factories that do not report termination remain
        # explicitly unclassified rather than being assumed to be rules draws.
        termination = result.get("termination")
        if termination not in KNOWN_TERMINATIONS:
            termination = "unknown"
        return {
            "_termination": termination,
            "game_id": game_id,
            "group": self.group,
            "white": white,
            "black": black,
            "depth_w": depth_w,
            "depth_b": depth_b,
            "result": result["result"],
            "plies": result["plies"],
            "nodes_w": result["white_nodes"],
            "nodes_b": result["black_nodes"],
            "ms_w": result["white_ms"],
            "ms_b": result["black_ms"],
            "seed": self.seed,
            "error": result.get("error", ""),
        }

    def run(self, *, on_progress: Callable[[dict], None] | None = None,
            stop_event=None, resume: bool = True) -> dict:
        """Run remaining games. If interrupted, rerun with resume=True.

        The callback receives one dictionary per completed game with:
        completed, total, white_wins, black_wins, draws, group, game_id,
        record (new row), resumed, stopped=False.
        Returns overall summary, including resumed and newly run counts.
        """
        if not isinstance(resume, bool):
            raise ValueError("resume must be True or False")
        existing = self._read_existing()
        if existing and not resume:
            raise ValueError("Matching group/seed rows already exist; use resume=True")
        terminations = self._read_termination_audit(existing)

        to_run = [i for i in range(1, self.games + 1) if i not in existing]
        positions = self._positions()
        # Fail fast for missing MCTS / D evaluator before touching the CSV.
        if to_run and not (stop_event is not None and stop_event.is_set()):
            for label in GROUP_PAIRS[self.group]:
                self.engine_factory(label)

        counts = {"1-0": 0, "0-1": 0, "1/2-1/2": 0}
        for row in existing.values():
            if row["result"] not in counts:
                raise ValueError("Existing CSV contains an invalid result")
            counts[row["result"]] += 1
        processed = dict(existing)
        new_games = 0
        stopped = False
        for game_id in to_run:
            if stop_event is not None and stop_event.is_set():
                stopped = True
                break
            opening_fen = positions[((game_id - 1) // 2) % len(positions)]
            row = self._run_one(game_id, opening_fen)
            termination = row.pop("_termination")
            self.output_csv.parent.mkdir(parents=True, exist_ok=True)
            is_new = (not self.output_csv.exists() or
                      self.output_csv.stat().st_size == 0)
            with self.output_csv.open("a", encoding="utf-8", newline="") as f:
                writer = csv.DictWriter(f, fieldnames=CSV_FIELDS)
                if is_new:
                    writer.writeheader()
                writer.writerow(row)
                f.flush()  # Save this game even if next game is cancelled.
            # Two separate files are not an atomic transaction. If interrupted
            # between writes, resume keeps the main result and reports the
            # missing audit as unknown rather than misclassifying the draw.
            self._append_termination(row, termination)
            terminations[game_id] = termination
            processed[game_id] = row
            counts[row["result"]] += 1
            new_games += 1
            if on_progress is not None:
                on_progress({
                    "completed": len(existing) + new_games,
                    "total": self.games,
                    "white_wins": counts["1-0"],
                    "black_wins": counts["0-1"],
                    "draws": counts["1/2-1/2"],  # legacy total, includes capped games
                    "rule_draws": sum(
                        (row0["result"] == "1/2-1/2" and
                         terminations.get(gid) == "rules")
                        for gid, row0 in processed.items()
                    ),
                    "ply_limits": sum(t == "ply_limit" for t in terminations.values()),
                    "group": self.group,
                    "game_id": game_id,
                    "record": dict(row),
                    "resumed": len(existing),
                    "stopped": False,
                })

        rule_draws = sum(
            row["result"] == "1/2-1/2" and terminations.get(gid) == "rules"
            for gid, row in processed.items()
        )
        ply_limits = sum(
            terminations.get(gid) == "ply_limit" for gid in processed
        )
        unknown_draws = sum(
            row["result"] == "1/2-1/2" and
            terminations.get(gid, "unknown") == "unknown"
            for gid, row in processed.items()
        )
        return {
            "group": self.group,
            "seed": self.seed,
            "total": self.games,
            "completed": len(existing) + new_games,
            "new_games": new_games,
            "resumed_games": len(existing),
            "white_wins": counts["1-0"],
            "black_wins": counts["0-1"],
            "draws": counts["1/2-1/2"],  # backward-compatible raw result count
            "rule_draws": rule_draws,
            "ply_limits": ply_limits,
            "unknown_draws": unknown_draws,
            "engine_errors": sum(
                terminations.get(gid) == "engine_error" for gid in processed
            ),
            "stopped": stopped,
            "output_csv": str(self.output_csv),
            "termination_csv": str(self.termination_csv),
        }


def run_experiment(group: str, games: int = 20, seed: int = 42, *,
                   on_progress=None, stop_event=None, resume=True, **kwargs) -> dict:
    """Convenient entry point for E's experiment page."""
    return ExperimentRunner(group, games=games, seed=seed, **kwargs).run(
        on_progress=on_progress, stop_event=stop_event, resume=resume)
