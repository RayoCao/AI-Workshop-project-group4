"""Automated tests for B's batch ExperimentRunner. No full AI search needed.

Run from chessbot/: python -m pytest tests/test_experiment.py -v
"""

import csv
from pathlib import Path
import random
import threading

import pytest

from src.experiment import (CSV_FIELDS, GROUP_PAIRS, ExperimentRunner,
                            _stable_match_seed, run_experiment)


class FakeEngine:
    def __init__(self, label):
        self.label = label


class FakeGame:
    calls = []

    def __init__(self, white_engine, black_engine, *, fen, max_plies):
        self.white = white_engine.label
        self.black = black_engine.label
        self.fen = fen
        self.max_plies = max_plies
        self.seed_value = random.random()
        FakeGame.calls.append((self.white, self.black, fen, max_plies, self.seed_value))

    def run_ai_vs_ai(self, *, time_limit=None, timeout_seconds=None):
        return {
            "result": "1-0" if self.white.endswith("1") else "1/2-1/2",
            "plies": 4, "white_nodes": 10, "black_nodes": 15,
            "white_ms": 2, "black_ms": 4, "error": "",
        }

    @property
    def move_records(self):
        return [
            {"color": "white", "depth": 2},
            {"color": "black", "depth": 3},
            {"color": "white", "depth": 1},
        ]


def runner(tmp_path, **kwargs):
    return ExperimentRunner("G1", games=4, seed=42,
        output_csv=tmp_path / "results.csv", opening_fens=["fen1", "fen2"],
        engine_factory=FakeEngine, game_factory=FakeGame, **kwargs)


def rows(path):
    with path.open(encoding="utf-8-sig", newline="") as f:
        return list(csv.DictReader(f))


def test_all_five_groups_defined():
    assert set(GROUP_PAIRS) == {"G1", "G2", "G3", "G4", "G5"}


@pytest.mark.parametrize("bad", ["oops", "G0", "", None])
def test_reject_bad_group(tmp_path, bad):
    with pytest.raises(ValueError):
        ExperimentRunner(bad, output_csv=tmp_path / "x.csv")


@pytest.mark.parametrize("bad", [0, -1, 1.5, True])
def test_reject_bad_games(tmp_path, bad):
    with pytest.raises(ValueError):
        ExperimentRunner("G1", games=bad, output_csv=tmp_path / "x.csv")


def test_reject_bad_seed_and_plies(tmp_path):
    with pytest.raises(ValueError):
        ExperimentRunner("G1", seed=True, output_csv=tmp_path / "x.csv")
    with pytest.raises(ValueError):
        ExperimentRunner("G1", max_plies=0, output_csv=tmp_path / "x.csv")


def test_reject_invalid_openings_and_time_limit(tmp_path):
    with pytest.raises(ValueError):
        ExperimentRunner("G1", opening_fens=[], output_csv=tmp_path / "x.csv")
    with pytest.raises(ValueError):
        ExperimentRunner("G1", time_limit=0, output_csv=tmp_path / "x.csv")


def test_csv_exact_14_columns_and_values(tmp_path):
    r = runner(tmp_path)
    s = r.run()
    assert s["completed"] == 4 and s["new_games"] == 4
    with r.output_csv.open() as f:
        assert tuple(next(csv.reader(f))) == CSV_FIELDS
    data = rows(r.output_csv)
    assert len(data) == 4
    assert len(data[0]) == 14
    assert data[0]["group"] == "G1" and data[0]["seed"] == "42"
    assert data[0]["depth_w"] == "2" and data[0]["depth_b"] == "3"
    assert data[0]["nodes_w"] == "10" and data[0]["ms_b"] == "4"
    assert data[0]["plies"] == "4"


def test_swap_colors_every_second_game(tmp_path):
    r = runner(tmp_path)
    r.run()
    data = rows(r.output_csv)
    assert [(d["white"], d["black"]) for d in data] == [
        ("L1", "L2"), ("L2", "L1"), ("L1", "L2"), ("L2", "L1")]


def test_same_opening_for_pair(tmp_path):
    FakeGame.calls.clear()
    runner(tmp_path).run()
    fens = [x[2] for x in FakeGame.calls]
    assert fens[0] == fens[1]
    assert fens[2] == fens[3]
    assert fens[0] != fens[2]


def test_progress_callback_has_counts_and_row(tmp_path):
    seen = []
    runner(tmp_path).run(on_progress=seen.append)
    assert [x["completed"] for x in seen] == [1, 2, 3, 4]
    assert all(x["total"] == 4 for x in seen)
    assert seen[-1]["white_wins"] + seen[-1]["black_wins"] + seen[-1]["draws"] == 4
    assert seen[-1]["record"]["game_id"] == 4


def test_resume_is_idempotent(tmp_path):
    r = runner(tmp_path)
    r.run()
    original = r.output_csv.read_bytes()
    summary = r.run()
    assert summary["new_games"] == 0 and summary["resumed_games"] == 4
    assert r.output_csv.read_bytes() == original


def test_resume_after_stop_event(tmp_path):
    stop = threading.Event()
    seen = []
    def callback(p):
        seen.append(p)
        if p["completed"] == 2:
            stop.set()
    r = runner(tmp_path)
    part = r.run(on_progress=callback, stop_event=stop)
    assert part["stopped"] and part["completed"] == 2
    assert len(rows(r.output_csv)) == 2
    full = r.run()
    assert full["completed"] == 4 and full["new_games"] == 2
    assert len(rows(r.output_csv)) == 4
    assert [int(x["game_id"]) for x in rows(r.output_csv)] == [1, 2, 3, 4]


def test_stopped_before_start_creates_no_file(tmp_path):
    stop = threading.Event()
    stop.set()
    r = runner(tmp_path)
    s = r.run(stop_event=stop)
    assert s["stopped"] and s["completed"] == 0
    assert not r.output_csv.exists()


def test_seed_changes_match_random_and_not_global_rng(tmp_path):
    original = random.getstate()
    try:
        FakeGame.calls.clear()
        runner(tmp_path).run()
        s1 = [x[4] for x in FakeGame.calls]
        assert random.getstate() == original
        FakeGame.calls.clear()
        r2 = ExperimentRunner("G1", games=4, seed=42,
            output_csv=tmp_path / "other.csv", opening_fens=["fen1", "fen2"],
            engine_factory=FakeEngine, game_factory=FakeGame)
        r2.run()
        assert s1 == [x[4] for x in FakeGame.calls]
    finally:
        random.setstate(original)


def test_stable_seed_not_python_hash(tmp_path):
    assert _stable_match_seed(42, "G1", 1) == _stable_match_seed(42, "G1", 1)
    assert _stable_match_seed(42, "G1", 1) != _stable_match_seed(42, "G1", 2)


def test_refuse_duplicate_batch_when_resume_false(tmp_path):
    r = runner(tmp_path)
    r.run()
    with pytest.raises(ValueError, match="resume"):
        r.run(resume=False)


def test_reject_invalid_csv_header(tmp_path):
    path = tmp_path / "results.csv"
    path.write_text("hello,there\n1,2\n", encoding="utf-8")
    with pytest.raises(ValueError, match="header"):
        runner(tmp_path).run()


def test_reject_duplicate_existing_ids(tmp_path):
    r = runner(tmp_path)
    r.run()
    data = r.output_csv.read_text(encoding="utf-8")
    r.output_csv.write_text(data + data.splitlines()[1] + "\n", encoding="utf-8")
    with pytest.raises(ValueError, match="duplicate"):
        r.run()


def test_reject_conflicting_existing_matchup(tmp_path):
    r = runner(tmp_path)
    r.run()
    text = r.output_csv.read_text()
    text = text.replace(",G1,L1,L2,", ",G1,L2,L1,", 1)
    r.output_csv.write_text(text)
    with pytest.raises(ValueError, match="conflicting"):
        r.run()


def test_other_groups_coexist_in_same_csv(tmp_path):
    path = tmp_path / "results.csv"
    kwargs = dict(games=2, output_csv=path, opening_fens=["fen1", "fen2"],
                  engine_factory=FakeEngine, game_factory=FakeGame)
    ExperimentRunner("G1", **kwargs).run()
    ExperimentRunner("G2", **kwargs).run()
    assert len(rows(path)) == 4
    assert ExperimentRunner("G1", **kwargs).run()["new_games"] == 0


def test_error_recorded_and_not_silently_discarded(tmp_path):
    class FailureGame(FakeGame):
        def run_ai_vs_ai(self, **kwargs):
            out = super().run_ai_vs_ai(**kwargs)
            out.update(result="0-1", error="engine crash")
            return out
    r = ExperimentRunner("G1", games=1, output_csv=tmp_path / "results.csv",
       opening_fens=["fen1"], engine_factory=FakeEngine, game_factory=FailureGame)
    result = r.run()
    assert result["black_wins"] == 1
    assert rows(r.output_csv)[0]["error"] == "engine crash"


def test_missing_mcts_fails_before_creating_csv(tmp_path):
    def missing(label):
        if label == "MCTS":
            raise RuntimeError("MCTS integration required")
        return FakeEngine(label)
    path = tmp_path / "x.csv"
    r = ExperimentRunner("G3", games=1, output_csv=path,
        opening_fens=["fen1"], engine_factory=missing, game_factory=FakeGame)
    with pytest.raises(RuntimeError, match="MCTS"):
        r.run()
    assert not path.exists()


def test_run_experiment_convenience_api(tmp_path):
    out = run_experiment("G1", games=1, seed=10,
        output_csv=tmp_path / "x.csv", opening_fens=["fen1"],
        engine_factory=FakeEngine, game_factory=FakeGame)
    assert out["new_games"] == 1
