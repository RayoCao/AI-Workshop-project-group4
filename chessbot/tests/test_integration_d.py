"""B+C+D integration checks. Run inside chessbot: python -m pytest tests -q."""

import chess
import pytest

from src.engine import build_engine
from src.evaluate import evaluate, evaluate_white, evaluate_breakdown, load_weights
from src.mcts import MCTS, Node, _backpropagate, choose_move
from src.experiment import ExperimentRunner, _build_default_engine


def test_d_evaluation_preserves_original_side_to_move_contract():
    a = chess.Board("4k3/8/8/8/8/8/3Q4/4K3 w - - 0 1")
    b = chess.Board("4k3/8/8/8/8/8/3Q4/4K3 b - - 0 1")
    assert evaluate(a) > 0
    assert evaluate(b) < 0
    assert evaluate_white(a) > 0
    assert evaluate_white(b) > 0
    assert evaluate_white(a) == evaluate_white(b)


def test_c_loads_white_perspective_evaluator():
    engine = build_engine("L2")
    assert "evaluate_white" in engine.evaluator_source
    b = chess.Board("4k3/8/8/8/8/8/3Q4/4K3 b - - 0 1")
    assert engine.evaluator(b) > 0


def test_evaluation_file_is_readable_and_original_api_kept():
    board = chess.Board()
    before = board.fen()
    assert isinstance(evaluate(board), int)
    assert evaluate_breakdown(board)["total"] == 0
    assert all(k in load_weights() for k in ("material", "pst", "mobility"))
    assert board.fen() == before


def test_fixed_mcts_backpropagation_is_normalized():
    b = chess.Board()
    root = Node(b)
    b.push_uci("e2e4")
    white_node = Node(b, parent=root, player_just_moved=chess.WHITE)
    b.push_uci("e7e5")
    black_node = Node(b, parent=white_node, player_just_moved=chess.BLACK)
    _backpropagate(black_node, -1.0, chess.WHITE)
    assert root.wins == 0 and white_node.wins == 0 and black_node.wins == 1
    assert all(0 <= n.wins <= n.visits for n in (root, white_node, black_node))


def test_mcts_preserves_repetition_history_in_nodes():
    b = chess.Board()
    b.push_uci("g1f3")
    b.push_uci("g8f6")
    assert len(Node(b).board.move_stack) == 2


def test_d_choose_move_still_works():
    b = chess.Board()
    before = b.fen()
    move = choose_move(b, time_limit=0.02, rollout_limit=2)
    assert move in b.legal_moves
    assert b.fen() == before


def test_c_can_build_mcts_and_get_five_fields():
    board = chess.Board()
    original = board.fen()
    engine = build_engine("MCTS")
    result = engine.choose(board, time_limit=0.03)
    assert set(result) == {"move", "score", "depth", "nodes", "ms"}
    assert chess.Move.from_uci(result["move"]) in board.legal_moves
    assert result["depth"] >= 0 and result["nodes"] >= 0 and result["ms"] >= 0
    assert board.fen() == original


def test_g5_position_uses_d_without_score_reversal():
    engine = _build_default_engine("POSITION")
    b = chess.Board("4k3/8/8/8/8/8/3Q4/4K3 b - - 0 1")
    assert engine.evaluator(b) > 0


@pytest.mark.parametrize("group", ["G3", "G5"])
def test_batch_experiment_uses_d_modules(tmp_path, group):
    runner = ExperimentRunner(
        group, games=1, max_plies=2, time_limit=0.03,
        output_csv=tmp_path / (group + ".csv"))
    outcome = runner.run()
    assert outcome["completed"] == 1
    assert runner.output_csv.is_file()
    assert len(runner.output_csv.read_text(encoding="utf-8").splitlines()) == 2
