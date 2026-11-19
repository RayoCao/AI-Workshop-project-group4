import chess
from src.mcts import choose_move, Node, _backpropagate, _terminal_score


def test_mcts_returns_legal_move_and_does_not_mutate():
    board = chess.Board()
    fen_before = board.fen()
    move = choose_move(board, time_limit=0.2, rollout_limit=5)
    assert move in board.legal_moves
    assert board.fen() == fen_before


def test_backpropagate_normalizes_reward_to_player_view():
    root = Node(chess.Board())
    b = root.board.copy(stack=True)
    b.push_uci("e2e4")
    child = Node(b, parent=root, player_just_moved=chess.WHITE)
    _backpropagate(child, -1.0, chess.WHITE)
    assert all(0 <= node.wins <= node.visits for node in (root, child))


def test_node_preserves_move_history():
    board = chess.Board()
    board.push_uci("g1f3")
    board.push_uci("g8f6")
    node = Node(board)
    assert len(node.board.move_stack) == 2


def test_draw_terminal_score_is_zero():
    board = chess.Board("7k/5Q2/6K1/8/8/8/8/8 b - - 0 1")
    assert board.is_stalemate()
    assert _terminal_score(board, chess.WHITE) == 0.0