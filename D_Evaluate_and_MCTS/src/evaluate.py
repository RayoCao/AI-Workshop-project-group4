import json
import os

import chess

# 子力基础价值（厘兵 centipawn）
PIECE_VALUES = {
    chess.PAWN: 100,
    chess.KNIGHT: 320,
    chess.BISHOP: 330,
    chess.ROOK: 500,
    chess.QUEEN: 900,
    chess.KING: 0,
}

DEFAULT_WEIGHTS = {
    "material": 1.0,
    "pst": 1.0,
    "mobility": 2.0,
}

MATE_SCORE = 100000


def load_weights(path: str = None) -> dict:
    """加载权重配置，若失败则返回默认权重。"""
    weights = DEFAULT_WEIGHTS.copy()
    if path is None:
        base_dir = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
        candidate_paths = [
            os.path.join(base_dir, "configs", "eval_weights.json"),
            os.path.join(os.getcwd(), "configs", "eval_weights.json"),
        ]
        for candidate in candidate_paths:
            if os.path.exists(candidate):
                path = candidate
                break

    if path is None:
        return weights

    try:
        with open(path, "r", encoding="utf-8") as f:
            loaded = json.load(f)
        if isinstance(loaded, dict):
            weights.update({k: float(v) for k, v in loaded.items() if k in DEFAULT_WEIGHTS})
    except Exception:
        return DEFAULT_WEIGHTS.copy()
    return weights


def _pst_value(piece_type: int, square: int, color: bool) -> int:
    """计算位置表分数 (Piece Square Table)。"""
    file = chess.square_file(square)
    rank = chess.square_rank(square)
    center_file = 3.5
    center_rank = 3.5
    distance = abs(file - center_file) + abs(rank - center_rank)
    center_bonus = max(0, 8 - int(distance * 2))

    if square in {chess.D4, chess.E4, chess.D5, chess.E5}:
        center_bonus += 12

    if piece_type == chess.PAWN:
        return 10 + center_bonus
    if piece_type == chess.KNIGHT:
        return 12 + center_bonus
    if piece_type == chess.BISHOP:
        return 10 + center_bonus
    if piece_type == chess.ROOK:
        return 6 + center_bonus
    if piece_type == chess.QUEEN:
        return 8 + center_bonus
    return 0


def _count_mobility(board: chess.Board, color: bool) -> int:
    """计算某一方的合法走法数量（机动性）。"""
    try:
        board_copy = board.copy(stack=False)
        board_copy.turn = color
        return len(list(board_copy.legal_moves))
    except Exception:
        return 0


def _white_breakdown(board: chess.Board, weights: dict) -> dict:
    """计算白方视角的分项得分。"""
    material = 0
    pst = 0
    mobility = 0

    for square, piece in board.piece_map().items():
        value = PIECE_VALUES.get(piece.piece_type, 0)
        if piece.color == chess.WHITE:
            material += value
            pst += _pst_value(piece.piece_type, square, piece.color)
        else:
            material -= value
            pst -= _pst_value(piece.piece_type, square, piece.color)

    mobility = _count_mobility(board, chess.WHITE) - _count_mobility(board, chess.BLACK)

    total = (
        weights.get("material", DEFAULT_WEIGHTS["material"]) * material
        + weights.get("pst", DEFAULT_WEIGHTS["pst"]) * pst
        + weights.get("mobility", DEFAULT_WEIGHTS["mobility"]) * mobility
    )

    return {
        "material": int(material),
        "pst": int(pst),
        "mobility": int(mobility),
        "total": int(total),
    }


def evaluate_breakdown(board: chess.Board, weights: dict = None) -> dict:
    """
    返回当前走子方视角的分项和 total。
    必须：不修改 board；确定性；不抛异常。
    """
    try:
        safe_board = board.copy(stack=False)
        effective_weights = load_weights() if weights is None else {**DEFAULT_WEIGHTS, **weights}
        white = _white_breakdown(safe_board, effective_weights)
        if safe_board.turn == chess.BLACK:
            return {
                "material": -white["material"],
                "pst": -white["pst"],
                "mobility": -white["mobility"],
                "total": -white["total"],
            }
        return white
    except Exception:
        return {
            "material": 0,
            "pst": 0,
            "mobility": 0,
            "total": 0,
        }


def evaluate(board: chess.Board) -> int:
    """
    从当前走子方 board.turn 的视角返回静态评估分。
    正数 = 当前走子方有利；负数 = 不利。
    单位：厘兵，整数。
    """
    try:
        safe_board = board.copy(stack=True)
        if safe_board.is_checkmate():
            return -MATE_SCORE
        if safe_board.is_game_over(claim_draw=True):
            return 0
        breakdown = evaluate_breakdown(safe_board)
        return int(breakdown["total"])
    except Exception:
        return 0

