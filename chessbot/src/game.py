"""Game controller for ChessMind (B's module).

Purpose
-------
Connect B's :class:`ChessBoard` with C's engines without implementing any
chess rules or AI search here. Supports human moves, one AI turn, complete
AI-vs-AI games, SAN/UCI logs, statistics, resign-by-error, and a safety cap.

Contract (project architecture, section 2.4):
    engine.choose(chess.Board, time_limit=None) ->
    {"move": "e2e4", "score": 35, "depth": 3, "nodes": 12000, "ms": 820}

All engine inputs are *copies* of the real position. An illegal or malformed
engine move forfeits the game rather than corrupting the real chess board.
"""

from __future__ import annotations

import time
from typing import Callable, Optional

import chess

from .board import ChessBoard

ENGINE_FIELDS = ("move", "score", "depth", "nodes", "ms")


class GameController:
    """Own one independently tracked chess game.

    ``white_engine`` / ``black_engine`` can be an object exposing ``choose``
    or ``None`` for a human player. ``max_plies`` counts *half-moves* (one
    player's turn); 200 is the agreed safety cap for experiments.
    """

    def __init__(
        self,
        white_engine=None,
        black_engine=None,
        *,
        fen: str | None = None,
        max_plies: int = 200,
    ) -> None:
        if not isinstance(max_plies, int) or isinstance(max_plies, bool) or max_plies < 1:
            raise ValueError("max_plies must be a positive integer")
        self._starting_fen = fen
        self.max_plies = max_plies
        self.board = ChessBoard(fen)
        self.engines = {chess.WHITE: white_engine, chess.BLACK: black_engine}
        self._records: list[dict] = []
        self._forced_result: str | None = None
        self._forced_reason: str = ""
        self.error: str = ""

    @classmethod
    def from_levels(cls, white_level="L1", black_level="L2", **kwargs):
        """Construct a game using C's existing ``build_engine`` function."""
        from .engine import build_engine

        white = build_engine(white_level) if white_level is not None else None
        black = build_engine(black_level) if black_level is not None else None
        return cls(white, black, **kwargs)

    @property
    def turn(self) -> bool:
        """``True`` = White to move; ``False`` = Black."""
        return self.board.get_chess_board().turn

    @property
    def move_records(self) -> list[dict]:
        """A defensive copy; callers cannot rewrite the internal log."""
        return [dict(record) for record in self._records]

    def get_board(self):
        return self.board.get_board()

    def moves_from(self, square: str) -> list[str]:
        return [] if self.is_finished() else self.board.moves_from(square)

    def get_fen(self) -> str:
        return self.board.get_fen()

    def get_move_history(self) -> list[str]:
        return self.board.get_move_history()

    def _end_status(self) -> tuple[str, str]:
        if self._forced_result is not None:
            return self._forced_result, self._forced_reason
        if self.board.is_game_over():
            return self.board.get_result() or "1/2-1/2", "rules"
        if len(self._records) >= self.max_plies:
            return "1/2-1/2", "ply_limit"
        return "*", "in_progress"

    def is_finished(self) -> bool:
        return self._end_status()[0] != "*"

    def _register(self, uci: str, *, kind: str, score=None,
                  depth: int = 0, nodes: int = 0, ms: int = 0) -> bool:
        if self.is_finished():
            return False
        color = self.turn
        if not self.board.make_uci_move(uci):
            return False
        try:
            # The board may add an implicit queen promotion. Record the actual
            # five-character UCI in that case, not the original four letters.
            actual_uci = self.board.get_chess_board().move_stack[-1].uci()
            record = {
                "ply": len(self._records) + 1,
                "color": "white" if color else "black",
                "source": kind,
                "uci": actual_uci,
                "san": self.board.get_move_history()[-1],
                "score": score,
                "depth": depth,
                "nodes": nodes,
                "ms": ms,
                "fen": self.board.get_fen(),
            }
            self._records.append(record)
        except Exception:
            self.board.undo_move()  # Never leave a half-recorded move behind.
            raise
        return True

    def make_uci_move(self, uci: str) -> bool:
        """Human/UI move; invalid input leaves the game untouched."""
        if not isinstance(uci, str):
            return False
        return self._register(uci, kind="human")

    def make_move(self, from_sq: str, to_sq: str, promotion: str | None = None) -> bool:
        """UI-friendly two-square move, with optional promotion letter."""
        if not isinstance(from_sq, str) or not isinstance(to_sq, str):
            return False
        suffix = promotion or ""
        if not isinstance(suffix, str):
            return False
        # Keep B's queen-by-default promotion behavior through make_uci_move.
        return self.make_uci_move(from_sq + to_sq + suffix)

    def _forfeit(self, color: bool, reason: str) -> None:
        self._forced_result = "0-1" if color == chess.WHITE else "1-0"
        self._forced_reason = "engine_error"
        self.error = ("white" if color else "black") + " engine: " + reason

    def play_engine_turn(self, time_limit: float | None = None,
                         timeout_seconds: float | None = None) -> dict | None:
        """Call only the engine whose turn it is and play one legal move.

        ``time_limit`` is passed to the engine as its thinking budget. Optional
        ``timeout_seconds`` is a *post-return* overrun check, **not** a hard
        pre-emptive timeout (the UI should run this in a worker thread).

        Returns a move record on success, ``None`` at game end or on forfeit.
        """
        if self.is_finished():
            return None
        color = self.turn
        engine = self.engines[color]
        try:
            if engine is None or not callable(getattr(engine, "choose", None)):
                raise ValueError("no AI engine configured for this side")
            if timeout_seconds is not None and timeout_seconds <= 0:
                raise ValueError("timeout_seconds must be positive")
            copied = self.board.get_chess_board()
            start = time.perf_counter()
            result = engine.choose(copied, time_limit=time_limit)
            elapsed = time.perf_counter() - start
            if timeout_seconds is not None and elapsed > timeout_seconds:
                raise TimeoutError("thinking exceeded %.3fs (finished after %.3fs)" %
                                   (timeout_seconds, elapsed))
            if not isinstance(result, dict):
                raise ValueError("choose() must return a dict")
            missing = [key for key in ENGINE_FIELDS if key not in result]
            if missing:
                raise ValueError("choose() missing fields: " + ", ".join(missing))
            uci = result["move"]
            if not isinstance(uci, str) or uci not in self.board.legal_moves_uci():
                raise ValueError("illegal engine move: %r" % (uci,))
            for key in ("depth", "nodes", "ms"):
                val = result[key]
                if not isinstance(val, int) or isinstance(val, bool) or val < 0:
                    raise ValueError("invalid %s: %r" % (key, val))
            if not isinstance(result["score"], (int, float)) or isinstance(result["score"], bool):
                raise ValueError("invalid score: %r" % (result["score"],))
            if not self._register(
                uci, kind="engine", score=result["score"],
                depth=result["depth"], nodes=result["nodes"], ms=result["ms"]
            ):
                raise RuntimeError("board rejected an engine move")
            return dict(self._records[-1])
        except Exception as exc:
            self._forfeit(color, "%s: %s" % (type(exc).__name__, exc))
            return None

    def undo_move(self, count: int = 1) -> bool:
        """Undo 1 ply normally or 2 plies for a human-vs-AI full turn."""
        if (not isinstance(count, int) or isinstance(count, bool) or
                count <= 0 or count > len(self._records)):
            return False
        for _ in range(count):
            if not self.board.undo_move():
                raise RuntimeError("move history and board are inconsistent")
            self._records.pop()
        self._forced_result = None
        self._forced_reason = ""
        self.error = ""
        return True

    def reset_game(self, fen: str | None = None) -> None:
        """Reset game and stats; absent FEN restores the original starting FEN."""
        target = self._starting_fen if fen is None else fen
        new_board = ChessBoard(target)   # Check input before modifying state.
        self.board = new_board
        self._records = []
        self._forced_result = None
        self._forced_reason = ""
        self.error = ""
        if fen is not None:
            self._starting_fen = fen

    def get_summary(self) -> dict:
        """Result record for E's UI and B's future experiment.py."""
        result, reason = self._end_status()
        winner = {"1-0": "white", "0-1": "black"}.get(result)
        white = [m for m in self._records if m["color"] == "white"]
        black = [m for m in self._records if m["color"] == "black"]
        return {
            "result": result,
            "winner": winner,
            "finished": result != "*",
            "termination": reason,
            "error": self.error,
            "plies": len(self._records),
            "san_moves": [m["san"] for m in self._records],
            "uci_moves": [m["uci"] for m in self._records],
            "white_nodes": sum(m["nodes"] for m in white),
            "black_nodes": sum(m["nodes"] for m in black),
            "white_ms": sum(m["ms"] for m in white),
            "black_ms": sum(m["ms"] for m in black),
            "fen": self.board.get_fen(),
        }

    def run_ai_vs_ai(self, *, time_limit: float | None = None,
                     timeout_seconds: float | None = None,
                     on_move: Callable[[dict], None] | None = None) -> dict:
        """Play unattended until game over, forfeit, or max_plies draw."""
        while not self.is_finished():
            record = self.play_engine_turn(time_limit=time_limit,
                                           timeout_seconds=timeout_seconds)
            if record is not None and on_move is not None:
                on_move(dict(record))
        return self.get_summary()


# Both spellings are supported for the future UI integration.
Game = GameController
