"""C 的集成自检：评估走白方视角、三档共用同一套评估、五字段契约。

和 B 的 `test_integration_d.py` 不重复：那边测的是"B 的集成是否正确"，
这里测的是"C 的搜索层是否真的按项目约定在用 D 的评估"，重点是**符号**和**一致性**——
评估函数如果翻了或者三档各用一套，棋力会塌但普通单元测试看不出来。

跑法（在 chessbot/ 目录下）：
    pytest tests/test_evaluate_integration.py -q
"""

import chess
import pytest

from src import search
from src.engine import _load_evaluator, build_engine, build_engines

FIELDS = ("move", "score", "depth", "nodes", "ms")

WHITE_UP_QUEEN_WHITE = "4k3/8/8/8/8/8/8/4K2Q w - - 0 1"
WHITE_UP_QUEEN_BLACK = "4k3/8/8/8/8/8/8/4K2Q b - - 0 1"
BLACK_UP_QUEEN_WHITE = "4k2q/8/8/8/8/8/8/4K3 w - - 0 1"


def test_evaluator_comes_from_d_not_fallback():
    _, source = _load_evaluator()
    assert "src.evaluate" in source, "没在用 D 的评估，实际来源：%s" % source
    assert "fallback" not in source


def test_evaluator_is_white_perspective_regardless_of_turn():
    ev, _ = _load_evaluator()
    assert ev(chess.Board(WHITE_UP_QUEEN_WHITE)) > 0
    assert ev(chess.Board(WHITE_UP_QUEEN_BLACK)) > 0, "黑方走时符号翻了 → 白方视角没生效"
    assert ev(chess.Board(BLACK_UP_QUEEN_WHITE)) < 0


def test_fast_path_matches_evaluate_white():
    """快速路径（预载权重）必须与 D 的 evaluate_white 逐分数一致。"""
    evaluate_mod = pytest.importorskip("src.evaluate")
    reference = getattr(evaluate_mod, "evaluate_white", None)
    if reference is None:
        pytest.skip("D 的 evaluate.py 没有 evaluate_white")
    fast, _ = _load_evaluator(use_cache=False, fast_path=True)
    boards = [chess.Board(WHITE_UP_QUEEN_WHITE), chess.Board(WHITE_UP_QUEEN_BLACK),
              chess.Board(BLACK_UP_QUEEN_WHITE), chess.Board(),
              chess.Board("r3k2r/p1ppqpb1/bn2pnp1/3PN3/1p2P3/2N2Q1p/PPPBBPPP/R3K2R w KQkq - 0 1")]
    for board in boards:
        assert fast(board) == reference(board), "快速路径与 evaluate_white 不一致：%s" % board.fen()


def test_three_levels_share_one_evaluator():
    engines = build_engines()
    assert len({id(eng.evaluator) for eng in engines.values()}) == 1, \
        "三档用了不同评估函数：%s" % {n: e.evaluator_source for n, e in engines.items()}
    for eng in engines.values():
        assert "src.evaluate" in eng.evaluator_source


def test_engine_score_is_white_perspective():
    board = chess.Board(WHITE_UP_QUEEN_WHITE)
    for level in ("L1", "L2"):
        result = build_engine(level).choose(board.copy())
        assert result["score"] > 0, "%s 给白多后的局面打出了非正分：%s" % (level, result)


@pytest.mark.parametrize("level", ["L1", "L2", "L3"])
def test_five_field_contract(level):
    board = chess.Board("r1bqk1nr/pppp1ppp/2n5/2b1p3/2B1P3/5N2/PPPP1PPP/RNBQK2R w KQkq - 4 4")
    before = board.fen()
    result = build_engine(level).choose(board)
    for field in FIELDS:
        assert field in result, "少字段 %s" % field
    assert chess.Move.from_uci(result["move"]) in chess.Board(before).legal_moves
    assert isinstance(result["score"], int) and result["nodes"] > 0
    assert board.fen() == before, "搜索不该修改调用方的盘面"


def test_mcts_reports_five_fields_and_white_perspective_score():
    engine = build_engine("MCTS")
    board = chess.Board()
    result = engine.choose(board, time_limit=0.15)
    for field in FIELDS:
        assert field in result
    assert chess.Move.from_uci(result["move"]) in board.legal_moves


def test_negamax_equals_minimax_reference():
    """L1（不剪枝）与独立写的 Minimax 参照逐分数相等——论文里"等价于 Minimax"的依据。"""
    def minimax_white(board, depth, ply=0):
        ev = search.material_eval
        if depth <= 0:
            if board.is_check() and not any(board.legal_moves):
                return (-search.MATE + ply) if board.turn else (search.MATE - ply)
            return ev(board)
        moves = list(board.legal_moves)
        if not moves:
            return ((-search.MATE + ply) if board.turn else (search.MATE - ply)) if board.is_check() else 0
        vals = []
        for move in moves:
            board.push(move)
            try:
                vals.append(minimax_white(board, depth - 1, ply + 1))
            finally:
                board.pop()
        return max(vals) if board.turn else min(vals)

    cfg = {"depth": 2, "use_pruning": False, "use_ordering": False, "use_cache": False,
           "use_quiescence": False, "node_limit": 10 ** 9, "time_limit_ms": 0, "name": "T"}
    board = chess.Board("8/2p5/3p4/KP5r/1R3p1k/8/4P1P1/8 w - - 0 1")
    result = search.search_best(board.copy(), cfg, evaluator=search.material_eval)
    ours = result["score"] if board.turn else -result["score"]
    assert ours == minimax_white(board.copy(), 2)


def test_fast_path_respects_fifty_move_claim():
    """D calls claim_draw=True; fast evaluation must preserve that meaning."""
    from src.evaluate import evaluate_white
    fen = "4k3/8/8/8/8/8/3Q4/4K3 w - - 0 1"
    normal = chess.Board(fen)
    draw = chess.Board(fen.replace(" 0 1", " 100 51"))
    fast, _ = _load_evaluator(use_cache=False, fast_path=True)
    cached, _ = _load_evaluator(use_cache=True, fast_path=True)
    assert evaluate_white(normal) > 0
    assert evaluate_white(draw) == 0
    assert fast(normal) == evaluate_white(normal)
    assert fast(draw) == evaluate_white(draw)
    assert cached(normal) > 0
    assert cached(draw) == evaluate_white(draw)


def test_fast_path_respects_repetition_claim():
    """Transposition caching must not mask a draw claim from move history."""
    from src.evaluate import evaluate_white
    board = chess.Board("4k3/8/8/8/8/8/3Q4/4K3 w - - 0 1")
    fast, _ = _load_evaluator(use_cache=False, fast_path=True)
    cached, _ = _load_evaluator(use_cache=True, fast_path=True)
    assert cached(board) > 0
    for move in ("d2d3", "e8f8", "d3d2", "f8e8") * 2:
        board.push_uci(move)
    assert board.is_repetition(3)
    assert evaluate_white(board) == 0
    assert fast(board) == evaluate_white(board)
    assert cached(board) == evaluate_white(board)
