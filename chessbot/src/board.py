"""Chess rules and board state for the ChessMind AI Chess Bot.

This module preserves the three UI functions agreed with team A/E:

    get_board()             -> (8x8 list, white_to_move: bool)
    moves_from(square)     -> list[str] (legal destination squares)
    make_move(from_sq, to_sq) -> bool

The upper/first row is rank 8 (Black's back rank). A cell is ``"wP"``,
``"bK"``, etc., or ``None`` for an empty square.

AI search and batch experiments SHOULD use separate ``ChessBoard`` instances
so that simultaneous games do not share the module-level UI board.

Dependency: pip install chess
"""

from __future__ import annotations

import chess


class ChessBoard:
    """A chess game with legal move validation and independent state."""

    def __init__(self, fen: str | None = None) -> None:
        self._board = chess.Board() if fen is None else self._checked_board(fen)

    @staticmethod
    def _checked_board(fen: str) -> chess.Board:
        """Reject malformed or internally impossible board positions."""
        try:
            board = chess.Board(fen)
        except (TypeError, ValueError) as exc:
            raise ValueError("Invalid FEN") from exc
        if not board.is_valid():
            raise ValueError("Invalid FEN position")
        return board

    def get_board(self) -> tuple[list[list[str | None]], bool]:
        """Return an 8x8 copy of the position and whose turn it is.

        Layout is rank 8 down to rank 1, file a through h. The color flag
        is True for White and False for Black (as in python-chess).
        """
        layout: list[list[str | None]] = []
        for rank in range(7, -1, -1):
            row: list[str | None] = []
            for file_index in range(8):
                piece = self._board.piece_at(chess.square(file_index, rank))
                if piece is None:
                    row.append(None)
                else:
                    color = "w" if piece.color == chess.WHITE else "b"
                    row.append(color + piece.symbol().upper())
            layout.append(row)
        return layout, self._board.turn

    def moves_from(self, square: str) -> list[str]:
        """Get deduplicated, sorted legal destinations in algebraic notation.

        Promotion moves with different promotion pieces share one destination
        square. Use make_move(..., promotion='n'/'b'/'r'/'q') to choose.
        """
        try:
            source = chess.parse_square(square)
        except (TypeError, ValueError):
            return []
        if self.is_game_over():
            return []
        return sorted({
            chess.square_name(move.to_square)
            for move in self._board.legal_moves
            if move.from_square == source
        })

    def make_move(
        self,
        from_sq: str,
        to_sq: str,
        promotion: str | None = None,
    ) -> bool:
        """Play one legal move, or leave the position unchanged and return False.

        For a promotion, the UI's two-argument call defaults to a queen.
        Call ``make_move('a7', 'a8', 'n')`` to promote to a knight. The
        equivalent ``make_move('a7', 'a8n')`` is also accepted.
        """
        if self.is_game_over():
            return False
        if not isinstance(from_sq, str) or not isinstance(to_sq, str):
            return False

        if len(to_sq) == 3 and promotion is None:
            to_sq, promotion = to_sq[:2], to_sq[2]

        try:
            from_index = chess.parse_square(from_sq)
            to_index = chess.parse_square(to_sq)
        except ValueError:
            return False

        if promotion is None:
            promote_to = None
        else:
            if not isinstance(promotion, str) or promotion.lower() not in ("q", "r", "b", "n"):
                return False
            promote_to = {"q": chess.QUEEN, "r": chess.ROOK,
                          "b": chess.BISHOP, "n": chess.KNIGHT}[promotion.lower()]

        move = chess.Move(from_index, to_index, promotion=promote_to)
        if move not in self._board.legal_moves and promote_to is None:
            # In the two-argument UI API, auto-promote a pawn to queen.
            move = chess.Move(from_index, to_index, promotion=chess.QUEEN)

        if move not in self._board.legal_moves:
            return False

        self._board.push(move)
        return True

    def make_uci_move(self, uci: str) -> bool:
        """Play a move in UCI form, e.g. 'e2e4' or 'a7a8n'."""
        if not isinstance(uci, str) or len(uci) not in (4, 5):
            return False
        return self.make_move(uci[:2], uci[2:4], uci[4] if len(uci) == 5 else None)

    def legal_moves_uci(self) -> list[str]:
        """Return current legal UCI moves, useful for AI engines."""
        if self.is_game_over():
            return []
        return sorted(move.uci() for move in self._board.legal_moves)

    def undo_move(self) -> bool:
        """Undo one move; return False if there is no move to undo."""
        if not self._board.move_stack:
            return False
        self._board.pop()
        return True

    def reset_game(self) -> None:
        """Start a new game with the standard starting position."""
        self._board.reset()

    def get_fen(self) -> str:
        """Return the current position as a FEN string."""
        return self._board.fen()

    def load_fen(self, fen: str) -> None:
        """Replace this game with a given valid FEN position."""
        new_board = self._checked_board(fen)
        self._board = new_board

    def is_game_over(self) -> bool:
        """Determine if play has ended, accepting claimable draws."""
        return self._board.is_game_over(claim_draw=True)

    def get_result(self) -> str | None:
        """Return '1-0', '0-1', '1/2-1/2', or None while playing."""
        return self._board.result(claim_draw=True) if self.is_game_over() else None

    def get_chess_board(self) -> chess.Board:
        """Return a *copy* for AI evaluation/search (never shared state)."""
        return self._board.copy(stack=True)

    def get_move_history(self) -> list[str]:
        """Return all moves in standard algebraic notation (SAN)."""
        moves = list(self._board.move_stack)
        replay = self._board.copy(stack=True)
        for _ in moves:
            replay.pop()
        history: list[str] = []
        for move in moves:
            history.append(replay.san(move))
            replay.push(move)
        return history


# Backward-compatible, shared UI instance used by A/E's fixed functions.
_ui_game = ChessBoard()


def get_board() -> tuple[list[list[str | None]], bool]:
    return _ui_game.get_board()


def moves_from(square: str) -> list[str]:
    return _ui_game.moves_from(square)


def make_move(from_sq: str, to_sq: str, promotion: str | None = None) -> bool:
    return _ui_game.make_move(from_sq, to_sq, promotion)


def make_uci_move(uci: str) -> bool:
    return _ui_game.make_uci_move(uci)


def legal_moves_uci() -> list[str]:
    return _ui_game.legal_moves_uci()


def undo_move() -> bool:
    return _ui_game.undo_move()


def reset_game() -> None:
    _ui_game.reset_game()


def get_fen() -> str:
    return _ui_game.get_fen()


def load_fen(fen: str) -> None:
    _ui_game.load_fen(fen)


def is_game_over() -> bool:
    return _ui_game.is_game_over()


def get_result() -> str | None:
    return _ui_game.get_result()


def get_chess_board() -> chess.Board:
    return _ui_game.get_chess_board()


def get_move_history() -> list[str]:
    return _ui_game.get_move_history()
