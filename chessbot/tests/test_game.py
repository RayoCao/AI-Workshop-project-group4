"""B's GameController tests: run from chessbot/ using pytest tests/ -q."""
import time

import chess
import pytest

from src.board import ChessBoard
from src.game import Game, GameController


class ScriptEngine:
    def __init__(self, moves, *, nodes=12, ms=4):
        self.moves = list(moves)
        self.calls = []
        self.nodes, self.ms = nodes, ms

    def choose(self, board, time_limit=None):
        self.calls.append((board.fen(), board.turn, time_limit))
        move = self.moves.pop(0)
        return {"move": move, "score": 0, "depth": 2,
                "nodes": self.nodes, "ms": self.ms}


class ErrorEngine:
    def choose(self, board, time_limit=None):
        raise RuntimeError("deliberate failure")


class InvalidEngine:
    def __init__(self, response):
        self.response = response

    def choose(self, board, time_limit=None):
        return self.response


class FirstLegalEngine:
    def choose(self, board, time_limit=None):
        return {"move": next(iter(board.legal_moves)).uci(), "score": 0,
                "depth": 1, "nodes": 1, "ms": 0}


def response(move="e2e4", **kwargs):
    result = {"move": move, "score": 0, "depth": 1, "nodes": 2, "ms": 3}
    result.update(kwargs)
    return result


def test_alias_and_initial_turn():
    game = Game()
    assert isinstance(game, GameController)
    assert game.turn == chess.WHITE
    assert game.get_summary()["result"] == "*"


def test_two_games_do_not_share_state():
    a, b = Game(), Game()
    assert a.make_uci_move("e2e4")
    assert b.get_fen() == chess.STARTING_FEN


def test_human_moves_change_turn_and_generate_san():
    g = Game()
    assert g.make_move("e2", "e4")
    assert g.make_uci_move("e7e5")
    assert g.get_move_history() == ["e4", "e5"]
    assert g.turn == chess.WHITE
    assert g.get_summary()["uci_moves"] == ["e2e4", "e7e5"]


def test_illegal_human_move_does_not_change_position():
    g = Game()
    before = g.get_fen()
    assert not g.make_uci_move("e2e5")
    assert not g.make_uci_move("bad")
    assert not g.make_move(1, "e4")
    assert g.get_fen() == before
    assert g.get_summary()["plies"] == 0


def test_fen_and_legal_highlights():
    g = Game()
    assert g.moves_from("e2") == ["e3", "e4"]
    assert g.get_board()[0][1][4] == "bP"


def test_engine_turn_uses_copy_and_updates_stats():
    engine = ScriptEngine(["e2e4"], nodes=120, ms=8)
    g = Game(white_engine=engine)
    r = g.play_engine_turn(time_limit=0.25)
    assert r["san"] == "e4" and r["color"] == "white"
    assert engine.calls[0][2] == 0.25
    assert engine.calls[0][0] == chess.STARTING_FEN
    assert g.get_summary()["white_nodes"] == 120
    assert g.get_summary()["white_ms"] == 8
    assert g.get_summary()["black_nodes"] == 0


def test_two_engines_alternate():
    w, b = ScriptEngine(["e2e4"]), ScriptEngine(["e7e5"])
    g = Game(w, b)
    g.play_engine_turn()
    g.play_engine_turn()
    assert len(w.calls) == 1 and len(b.calls) == 1
    assert g.get_move_history() == ["e4", "e5"]


def test_full_scripted_checkmate():
    w, b = ScriptEngine(["f2f3", "g2g4"]), ScriptEngine(["e7e5", "d8h4"])
    g = Game(w, b)
    summary = g.run_ai_vs_ai()
    assert summary["result"] == "0-1"
    assert summary["winner"] == "black"
    assert summary["termination"] == "rules"
    assert summary["plies"] == 4
    assert summary["san_moves"] == ["f3", "e5", "g4", "Qh4#"]
    assert summary["white_nodes"] == summary["black_nodes"] == 24
    assert summary["white_ms"] == summary["black_ms"] == 8
    assert g.play_engine_turn() is None


def test_callback_gets_each_successful_move():
    g = Game(ScriptEngine(["e2e4"]), ScriptEngine([]), max_plies=1)
    seen = []
    g.run_ai_vs_ai(on_move=seen.append)
    assert len(seen) == 1
    assert seen[0]["uci"] == "e2e4"


def test_ply_cap_is_draw_not_a_win():
    g = Game(ScriptEngine(["e2e4"]), max_plies=1)
    summary = g.run_ai_vs_ai()
    assert summary["result"] == "1/2-1/2"
    assert summary["termination"] == "ply_limit"
    assert summary["winner"] is None
    assert g.moves_from("e7") == []


def test_stalemate_is_draw_immediately():
    g = Game(fen="7k/5Q2/6K1/8/8/8/8/8 b - - 0 1")
    assert g.is_finished()
    assert g.run_ai_vs_ai()["result"] == "1/2-1/2"
    assert g.get_summary()["termination"] == "rules"


def test_undo_one_and_two_plies_and_recalculate_statistics():
    g = Game(ScriptEngine(["e2e4"]), ScriptEngine(["e7e5"]))
    g.play_engine_turn()
    g.play_engine_turn()
    assert g.undo_move(2)
    assert g.get_fen() == chess.STARTING_FEN
    assert g.get_summary()["white_nodes"] == 0
    assert g.get_summary()["black_nodes"] == 0
    assert not g.undo_move()


def test_undo_one_restores_turn():
    g = Game()
    g.make_uci_move("e2e4")
    assert g.undo_move()
    assert g.turn == chess.WHITE


@pytest.mark.parametrize("count", [0, -1, 2, 1.5, True])
def test_undo_bad_count_is_safe(count):
    g = Game()
    g.make_uci_move("e2e4")
    before = g.get_fen()
    assert not g.undo_move(count)
    assert g.get_fen() == before


def test_reset_clears_records():
    g = Game()
    g.make_uci_move("e2e4")
    g.reset_game()
    assert g.get_summary()["plies"] == 0
    assert g.get_fen() == chess.STARTING_FEN


def test_reset_with_invalid_fen_is_atomic():
    g = Game()
    g.make_uci_move("e2e4")
    before = g.get_fen()
    with pytest.raises(ValueError):
        g.reset_game("nonsense")
    assert g.get_fen() == before


def test_custom_position_is_preserved_by_reset():
    fen = "7k/8/8/8/8/8/8/K7 w - - 0 1"
    g = Game(fen=fen)
    assert g.get_fen() == fen
    g.reset_game()
    assert g.get_fen() == fen


def test_engine_failure_forfeits_white_and_keeps_board_intact():
    g = Game(ErrorEngine())
    before = g.get_fen()
    assert g.play_engine_turn() is None
    assert g.get_summary()["result"] == "0-1"
    assert g.get_summary()["termination"] == "engine_error"
    assert "deliberate failure" in g.get_summary()["error"]
    assert g.get_fen() == before


def test_engine_failure_forfeits_black():
    g = Game(ScriptEngine(["e2e4"]), ErrorEngine())
    g.play_engine_turn()
    assert g.play_engine_turn() is None
    assert g.get_summary()["winner"] == "white"
    assert g.get_summary()["result"] == "1-0"


@pytest.mark.parametrize("bad", [None, "e2e4", {}, {"move": "e2e4"},
                                       response("e2e5"), response("e2e4", nodes=-5),
                                       response("e2e4", ms="slow"),
                                       response("e2e4", score=None)])
def test_bad_engine_outputs_forfeit_not_corrupt_board(bad):
    g = Game(InvalidEngine(bad))
    before = g.get_fen()
    g.play_engine_turn()
    assert g.get_fen() == before
    assert g.get_summary()["result"] == "0-1"
    assert g.get_summary()["plies"] == 0


def test_missing_engine_forfeits_current_side():
    g = Game(white_engine=None)
    g.play_engine_turn()
    assert g.get_summary()["result"] == "0-1"
    assert "no AI engine" in g.get_summary()["error"]


def test_result_dict_is_not_mutable_internally():
    g = Game()
    g.make_uci_move("e2e4")
    records = g.move_records
    records[0]["san"] = "fake"
    records.append({})
    assert g.get_summary()["san_moves"] == ["e4"]


def test_max_plies_rejects_invalid_values():
    with pytest.raises(ValueError):
        Game(max_plies=0)
    with pytest.raises(ValueError):
        Game(max_plies=True)


def test_engine_promotion_uci_suffix():
    # Valid K/k and white pawn about to promote.
    fen = "7k/P7/8/8/8/8/8/K7 w - - 0 1"
    g = Game(ScriptEngine(["a7a8n"]), fen=fen)
    record = g.play_engine_turn()
    assert record is not None
    assert record["uci"] == "a7a8n"
    assert record["san"].startswith("a8=N")


def test_real_C_engine_one_move_integration():
    """This also tests B + C without changing either teammate's file."""
    from src.engine import build_engine

    g = Game(build_engine("L1"), max_plies=1)
    record = g.play_engine_turn()
    assert record is not None
    assert record["source"] == "engine"
    assert g.get_summary()["termination"] == "ply_limit"
    assert record["depth"] >= 1


def test_real_C_engines_run_small_ai_match():
    from src.engine import build_engine

    g = Game(build_engine("L1"), build_engine("L1"), max_plies=2)
    summary = g.run_ai_vs_ai()
    assert summary["plies"] == 2
    assert summary["result"] == "1/2-1/2"
    assert summary["white_nodes"] > 0
    assert summary["black_nodes"] > 0


def test_engine_copy_cannot_mutate_actual_game():
    class MutatingEngine:
        def choose(self, board, time_limit=None):
            board.push_uci("e2e4")
            return response("d2d4")

    g = Game(MutatingEngine())
    record = g.play_engine_turn()
    assert record["uci"] == "d2d4"
    assert g.get_summary()["plies"] == 1


def test_timeout_detected_after_engine_returns():
    class SlowEngine:
        def choose(self, board, time_limit=None):
            time.sleep(0.02)
            return response("e2e4")

    g = Game(SlowEngine())
    g.play_engine_turn(timeout_seconds=0.001)
    assert g.get_summary()["termination"] == "engine_error"
    assert "TimeoutError" in g.get_summary()["error"]


def test_human_default_queen_promotion_records_real_uci():
    fen = "7k/P7/8/8/8/8/8/K7 w - - 0 1"
    g = Game(fen=fen)
    assert g.make_move("a7", "a8")
    assert g.get_summary()["uci_moves"] == ["a7a8q"]
    assert g.get_summary()["san_moves"][0].startswith("a8=Q")
