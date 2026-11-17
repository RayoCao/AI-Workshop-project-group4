"""Automated unit tests for B's chess rules module.

Run from inside the chessbot directory:
    python -m pytest tests/test_board.py -v
"""

import sys
from pathlib import Path

import chess
import pytest

# Allow running tests from either the repository root or chessbot/.
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from src import board as ui_board
from src.board import ChessBoard


@pytest.fixture
def game():
    """Each test gets its own independent chess position."""
    return ChessBoard()


def test_initial_fen(game):
    assert game.get_fen() == chess.STARTING_FEN


def test_initial_position_has_20_legal_moves(game):
    assert len(game.legal_moves_uci()) == 20


def test_board_is_eight_rows(game):
    assert len(game.get_board()[0]) == 8


def test_each_row_has_eight_squares(game):
    assert all(len(row) == 8 for row in game.get_board()[0])


def test_black_back_rank_is_top_row(game):
    assert game.get_board()[0][0] == ["bR", "bN", "bB", "bQ", "bK", "bB", "bN", "bR"]


def test_white_back_rank_is_bottom_row(game):
    assert game.get_board()[0][7] == ["wR", "wN", "wB", "wQ", "wK", "wB", "wN", "wR"]


def test_black_pawn_row(game):
    assert game.get_board()[0][1] == ["bP"] * 8


def test_white_pawn_row(game):
    assert game.get_board()[0][6] == ["wP"] * 8


def test_empty_square_is_none(game):
    assert game.get_board()[0][4][4] is None


def test_white_moves_first(game):
    assert game.get_board()[1] is True


def test_white_e_pawn_has_two_moves(game):
    assert game.moves_from("e2") == ["e3", "e4"]


def test_white_knight_has_two_moves(game):
    assert game.moves_from("g1") == ["f3", "h3"]


def test_black_cannot_move_on_white_turn(game):
    assert game.moves_from("e7") == []


def test_invalid_square_has_no_moves(game):
    assert game.moves_from("z9") == []


def test_nonstr_square_has_no_moves(game):
    assert game.moves_from(None) == []


def test_empty_square_has_no_moves(game):
    assert game.moves_from("e4") == []


def test_legal_move_returns_true(game):
    assert game.make_move("e2", "e4") is True


def test_legal_move_changes_turn(game):
    game.make_move("e2", "e4")
    assert game.get_board()[1] is False


def test_legal_move_updates_piece_positions(game):
    game.make_move("e2", "e4")
    layout, _ = game.get_board()
    assert layout[6][4] is None and layout[4][4] == "wP"


def test_illegal_move_returns_false(game):
    assert game.make_move("e2", "e5") is False


def test_illegal_move_does_not_change_fen(game):
    before = game.get_fen()
    assert not game.make_move("e2", "e5")
    assert game.get_fen() == before


def test_empty_origin_is_invalid(game):
    assert game.make_move("e4", "e5") is False


def test_wrong_turn_move_is_invalid(game):
    assert game.make_move("e7", "e5") is False


def test_bad_destination_is_invalid(game):
    assert game.make_move("e2", "z9") is False


def test_bad_origin_type_is_invalid(game):
    assert game.make_move(None, "e4") is False


def test_same_square_move_is_invalid(game):
    assert game.make_move("e2", "e2") is False


def test_undo_empty_history_returns_false(game):
    assert game.undo_move() is False


def test_undo_returns_true_after_a_move(game):
    game.make_move("e2", "e4")
    assert game.undo_move() is True


def test_undo_restores_starting_fen(game):
    game.make_move("e2", "e4")
    game.undo_move()
    assert game.get_fen() == chess.STARTING_FEN


def test_reset_restores_starting_fen(game):
    game.make_move("e2", "e4")
    game.reset_game()
    assert game.get_fen() == chess.STARTING_FEN


def test_reset_clears_move_history(game):
    game.make_move("e2", "e4")
    game.reset_game()
    assert game.get_move_history() == []


def test_fen_after_e4_matches_python_chess(game):
    expected = chess.Board()
    expected.push_uci("e2e4")
    game.make_move("e2", "e4")
    assert game.get_fen() == expected.fen()


def test_uci_move_works(game):
    assert game.make_uci_move("e2e4") is True


def test_invalid_uci_move_rejected(game):
    assert game.make_uci_move("e2e5") is False


def test_uci_move_rejects_bad_input(game):
    assert game.make_uci_move(12) is False


def test_legal_moves_uci_is_sorted(game):
    assert game.legal_moves_uci() == sorted(game.legal_moves_uci())


def test_copied_board_does_not_modify_original(game):
    copied = game.get_chess_board()
    copied.push_uci("e2e4")
    assert game.get_fen() == chess.STARTING_FEN


def test_two_games_are_independent():
    left, right = ChessBoard(), ChessBoard()
    left.make_move("e2", "e4")
    assert right.get_fen() == chess.STARTING_FEN


def test_load_valid_fen(game):
    game.load_fen("4k3/8/8/8/8/8/8/4K3 w - - 0 1")
    assert game.get_board()[0][0][4] == "bK"


def test_load_invalid_fen_raises(game):
    with pytest.raises(ValueError):
        game.load_fen("not a FEN")


def test_invalid_fen_does_not_replace_current_board(game):
    before = game.get_fen()
    with pytest.raises(ValueError):
        game.load_fen("not a FEN")
    assert game.get_fen() == before


def test_fen_missing_black_king_is_rejected():
    with pytest.raises(ValueError):
        ChessBoard("8/8/8/8/8/8/8/4K3 w - - 0 1")


def test_castling_initially_not_legal(game):
    assert "g1" not in game.moves_from("e1")


def test_kingside_castling_legal_when_clear():
    game = ChessBoard("r3k2r/8/8/8/8/8/8/R3K2R w KQkq - 0 1")
    assert "g1" in game.moves_from("e1")
    assert game.make_move("e1", "g1")
    layout, _ = game.get_board()
    assert layout[7][6] == "wK" and layout[7][5] == "wR"


def test_queenside_castling_legal_when_clear():
    game = ChessBoard("r3k2r/8/8/8/8/8/8/R3K2R w KQkq - 0 1")
    assert "c1" in game.moves_from("e1")
    assert game.make_move("e1", "c1")
    layout, _ = game.get_board()
    assert layout[7][2] == "wK" and layout[7][3] == "wR"


def test_castling_rights_restored_on_undo():
    game = ChessBoard("r3k2r/8/8/8/8/8/8/R3K2R w KQkq - 0 1")
    before = game.get_fen()
    game.make_move("e1", "g1")
    game.undo_move()
    assert game.get_fen() == before


def test_en_passant_capture():
    game = ChessBoard("4k3/8/8/3pP3/8/8/8/4K3 w - d6 0 1")
    assert "d6" in game.moves_from("e5")
    assert game.make_move("e5", "d6")
    layout, _ = game.get_board()
    assert layout[2][3] == "wP" and layout[3][3] is None


def test_promotion_defaults_to_queen():
    game = ChessBoard("4k3/P7/8/8/8/8/8/4K3 w - - 0 1")
    assert game.make_move("a7", "a8")
    assert game.get_board()[0][0][0] == "wQ"


def test_promotion_to_knight():
    game = ChessBoard("4k3/P7/8/8/8/8/8/4K3 w - - 0 1")
    assert game.make_move("a7", "a8", "n")
    assert game.get_board()[0][0][0] == "wN"


def test_promotion_suffix_supported():
    game = ChessBoard("4k3/P7/8/8/8/8/8/4K3 w - - 0 1")
    assert game.make_move("a7", "a8r")
    assert game.get_board()[0][0][0] == "wR"


def test_invalid_promotion_rejected():
    game = ChessBoard("4k3/P7/8/8/8/8/8/4K3 w - - 0 1")
    assert game.make_move("a7", "a8", "k") is False


def test_promotion_destinations_are_deduplicated():
    game = ChessBoard("4k3/P7/8/8/8/8/8/4K3 w - - 0 1")
    assert game.moves_from("a7") == ["a8"]


def test_initial_game_not_over(game):
    assert game.is_game_over() is False


def test_initial_game_result_none(game):
    assert game.get_result() is None


def test_scholars_not_needed_fools_mate_result(game):
    for move in ("f2f3", "e7e5", "g2g4", "d8h4"):
        assert game.make_uci_move(move)
    assert game.is_game_over() is True
    assert game.get_result() == "0-1"


def test_no_moves_allowed_after_checkmate(game):
    for move in ("f2f3", "e7e5", "g2g4", "d8h4"):
        game.make_uci_move(move)
    old = game.get_fen()
    assert game.make_move("e1", "e2") is False
    assert game.get_fen() == old


def test_stalemate_is_draw():
    game = ChessBoard("7k/5Q2/6K1/8/8/8/8/8 b - - 0 1")
    assert game.is_game_over()
    assert game.get_result() == "1/2-1/2"


def test_insufficient_material_is_draw():
    game = ChessBoard("7k/8/8/8/8/8/8/K7 w - - 0 1")
    assert game.get_result() == "1/2-1/2"


def test_fifty_move_claim_is_draw():
    game = ChessBoard("7k/8/8/8/8/8/4K3/R7 w - - 100 50")
    assert game.is_game_over()
    assert game.get_result() == "1/2-1/2"


def test_threefold_repetition_is_draw(game):
    # With claim_draw=True, python-chess also allows a claim if the *next*
    # legal move would create the third repetition. Stop when claimable.
    for move in ("g1f3", "g8f6", "f3g1", "f6g8") * 2:
        if game.is_game_over():
            break
        assert game.make_uci_move(move)
    assert game.is_game_over() is True
    assert game.get_result() == "1/2-1/2"


def test_san_move_history(game):
    for move in ("e2e4", "e7e5", "g1f3"):
        game.make_uci_move(move)
    assert game.get_move_history() == ["e4", "e5", "Nf3"]


def test_board_layout_is_copy_not_shared(game):
    first, _ = game.get_board()
    first[7][4] = None
    assert game.get_board()[0][7][4] == "wK"


def test_module_level_ui_compatibility():
    ui_board.reset_game()
    try:
        assert ui_board.get_board()[1] is True
        assert ui_board.moves_from("e2") == ["e3", "e4"]
        assert ui_board.make_move("e2", "e4")
        assert ui_board.get_board()[1] is False
        assert ui_board.undo_move()
    finally:
        ui_board.reset_game()
