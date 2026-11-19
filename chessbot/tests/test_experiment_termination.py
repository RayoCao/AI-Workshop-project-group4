"""Audit that chess rule draws are distinguishable from safety-cap outcomes.

Run from chessbot/: python -m pytest tests/test_experiment_termination.py -v
"""
import csv
import threading

import pytest

from src.experiment import CSV_FIELDS, TERMINATION_FIELDS, ExperimentRunner


class StubEngine:
    def __init__(self, name):
        self.name = name


class StubGame:
    """Alternating scripted outcomes; no real engine search needed."""
    def __init__(self, white_engine, black_engine, *, fen, max_plies):
        self.white = white_engine.name
        self.black = black_engine.name
        self.max_plies = max_plies

    def run_ai_vs_ai(self, *, time_limit=None, timeout_seconds=None):
        # Two draw records: first was stopped at the cap, second by rules.
        reason = "ply_limit" if self.white == "L1" else "rules"
        return dict(result="1/2-1/2", termination=reason,
                    plies=self.max_plies, white_nodes=4, black_nodes=5,
                    white_ms=1, black_ms=2, error="")

    @property
    def move_records(self):
        return [{"color":"white", "depth":2}, {"color":"black", "depth":3}]


class ErrorGame(StubGame):
    def run_ai_vs_ai(self, **kwargs):
        result = super().run_ai_vs_ai(**kwargs)
        result.update(result="0-1", termination="engine_error", error="engine crash")
        return result


class LegacyGame(StubGame):
    def run_ai_vs_ai(self, **kwargs):
        result = super().run_ai_vs_ai(**kwargs)
        result.pop("termination")  # Simulate older game factories.
        return result


def make_runner(tmp_path, *, games=2, factory=StubGame, group="G1", **kwargs):
    return ExperimentRunner(group, games=games, seed=42,
        output_csv=tmp_path/"results.csv", opening_fens=["test-fen"],
        engine_factory=StubEngine, game_factory=factory, max_plies=4, **kwargs)


def read_rows(path):
    with path.open(encoding="utf-8-sig", newline="") as f:
        reader = csv.DictReader(f)
        return tuple(reader.fieldnames or ()), list(reader)


def test_companion_csv_distinguishes_same_result_same_ply_count(tmp_path):
    runner = make_runner(tmp_path)
    out = runner.run()
    fields, rows = read_rows(runner.output_csv)
    audit_fields, audit_rows = read_rows(runner.termination_csv)
    assert fields == CSV_FIELDS and len(fields) == 14
    assert all(row["result"] == "1/2-1/2" and row["plies"] == "4" for row in rows)
    assert all(row["error"] == "" for row in rows)
    assert audit_fields == TERMINATION_FIELDS
    assert [r["termination"] for r in audit_rows] == ["ply_limit", "rules"]
    assert [r["game_id"] for r in audit_rows] == ["1", "2"]
    assert out["draws"] == 2  # Original 14-column/GUI contract preserved.
    assert out["rule_draws"] == 1
    assert out["ply_limits"] == 1
    assert out["unknown_draws"] == 0
    assert out["termination_csv"] == str(runner.termination_csv)


def test_callback_preserves_original_shape_and_adds_disaggregated_counts(tmp_path):
    seen=[]
    make_runner(tmp_path).run(on_progress=seen.append)
    assert len(seen) == 2
    assert seen[0]["draws"] == 1 and seen[0]["ply_limits"] == 1
    assert seen[1]["rule_draws"] == 1 and seen[1]["draws"] == 2
    assert len(seen[-1]["record"]) == 14


def test_engine_errors_remain_errors_not_rules_draws(tmp_path):
    runner = make_runner(tmp_path, games=1, factory=ErrorGame)
    result = runner.run()
    _, main = read_rows(runner.output_csv)
    _, audit = read_rows(runner.termination_csv)
    assert main[0]["error"] == "engine crash"
    assert audit[0]["termination"] == "engine_error"
    assert result["engine_errors"] == 1
    assert result["draws"] == 0


def test_resume_keeps_audit_and_results_idempotent(tmp_path):
    runner = make_runner(tmp_path)
    stopper=threading.Event()
    def callback(p):
        if p["completed"] == 1:
            stopper.set()
    part = runner.run(on_progress=callback, stop_event=stopper)
    assert part["completed"] == 1 and part["stopped"]
    assert len(read_rows(runner.termination_csv)[1]) == 1
    resume = runner.run()
    assert resume["new_games"] == 1 and resume["resumed_games"] == 1
    assert resume["rule_draws"] == 1 and resume["ply_limits"] == 1
    main_bytes, audit_bytes = runner.output_csv.read_bytes(), runner.termination_csv.read_bytes()
    again = runner.run()
    assert again["new_games"] == 0
    assert runner.output_csv.read_bytes() == main_bytes
    assert runner.termination_csv.read_bytes() == audit_bytes


def test_old_csv_without_companion_is_unclassified_not_guessed(tmp_path):
    runner = make_runner(tmp_path, factory=LegacyGame)
    runner.run()
    # Simulate older repository exports without the new audit file.
    runner.termination_csv.unlink()
    main_bytes=runner.output_csv.read_bytes()
    summary = runner.run()
    assert summary["draws"] == 2
    assert summary["rule_draws"] == 0
    assert summary["ply_limits"] == 0
    assert summary["unknown_draws"] == 2
    assert runner.output_csv.read_bytes() == main_bytes
    assert not runner.termination_csv.exists()  # Do not fabricate old causes.


def test_missing_game_termination_is_explicitly_unknown(tmp_path):
    runner = make_runner(tmp_path, factory=LegacyGame)
    summary=runner.run()
    assert summary["unknown_draws"] == 2
    assert [r["termination"] for r in read_rows(runner.termination_csv)[1]] == ["unknown", "unknown"]


def test_reject_audit_with_wrong_header(tmp_path):
    runner=make_runner(tmp_path)
    runner.run()
    runner.termination_csv.write_text("bad,header\n", encoding="utf-8")
    with pytest.raises(ValueError, match="audit CSV header"):
        runner.run()


def test_reject_duplicate_audit_row(tmp_path):
    runner=make_runner(tmp_path)
    runner.run()
    text=runner.termination_csv.read_text(encoding="utf-8")
    runner.termination_csv.write_text(text + text.splitlines()[1] + "\n", encoding="utf-8")
    with pytest.raises(ValueError, match="duplicate termination audit"):
        runner.run()


def test_reject_audit_conflicting_with_results(tmp_path):
    runner=make_runner(tmp_path)
    runner.run()
    text=runner.termination_csv.read_text(encoding="utf-8")
    text=text.replace("1/2-1/2", "1-0", 1)
    runner.termination_csv.write_text(text, encoding="utf-8")
    with pytest.raises(ValueError, match="disagrees"):
        runner.run()


def test_real_b_c_one_match_yields_ply_limit(tmp_path):
    pytest.importorskip("chess")
    runner = ExperimentRunner("G1", games=1, seed=42,
                              max_plies=2,
                              output_csv=tmp_path/"smoke.csv")
    summary = runner.run()
    assert summary["completed"] == 1
    assert summary["ply_limits"] == 1
    assert summary["rule_draws"] == 0
    assert read_rows(runner.termination_csv)[1][0]["termination"] == "ply_limit"
