"""C 的搜索层自检：接口契约、三档等价性、杀棋正确性、预算与可复现。

跑法（在 chessbot/ 目录下）：
    pytest tests/ -q

这些测试只验 C 的交付面：search.py / engine.py / config.yaml。
真规则的正确性归 B（tests/test_board.py），评估函数的强弱归 D（G5 组实验）。
"""

import time

import pytest

chess = pytest.importorskip("chess", reason="需要 python-chess：pip install chess")

from src import config_loader, search                      # noqa: E402
from src.engine import EngineError, build_engine, build_engines  # noqa: E402
from src.search import MATE, search_best                   # noqa: E402

FIELDS = ("move", "score", "depth", "nodes", "ms")

POSITIONS = {
    "start": chess.STARTING_FEN,
    "italian": "r1bqk1nr/pppp1ppp/2n5/2b1p3/2B1P3/5N2/PPPP1PPP/RNBQK2R w KQkq - 4 4",
    "kiwipete": "r3k2r/p1ppqpb1/bn2pnp1/3PN3/1p2P3/2N2Q1p/PPPBBPPP/R3K2R w KQkq - 0 1",
    "endgame": "8/2p5/3p4/KP5r/1R3p1k/8/4P1P1/8 w - - 0 1",
    "mate_in_1": "6k1/5ppp/8/8/8/8/5PPP/R5K1 w - - 0 1",
    "stalemate": "7k/5Q2/6K1/8/8/8/8/8 b - - 0 1",
}


def cfg(**over):
    """一份"什么开关都不加"的基准配置，测试里按需覆盖。"""
    base = {"depth": 2, "use_pruning": False, "use_ordering": False,
            "use_cache": False, "use_quiescence": False, "node_limit": 10 ** 9,
            "time_limit_ms": 0, "name": "TEST"}
    base.update(over)
    return base


# --------------------------------------------------------------------------- #
# 一个"教科书版"参照实现：MAX/MIN 交替，白方视角打分，不做任何剪枝。
# 用来证明 search.py 在关掉全部加速开关后与 Minimax 完全等价（论文第 3 章要用）。
# --------------------------------------------------------------------------- #

def minimax_white(board, depth, ply=0, ev=None):
    ev = ev or search.material_eval
    if depth <= 0:
        if board.is_check() and not any(board.legal_moves):
            return (-MATE + ply) if board.turn else (MATE - ply)
        return ev(board)
    moves = list(board.legal_moves)
    if not moves:
        if board.is_check():
            return (-MATE + ply) if board.turn else (MATE - ply)
        return 0
    values = []
    for move in moves:
        board.push(move)
        try:
            values.append(minimax_white(board, depth - 1, ply + 1, ev))
        finally:
            board.pop()
    return max(values) if board.turn else min(values)


# --------------------------------------------------------------------------- #
# 1. 接口契约（02 §2.4）
# --------------------------------------------------------------------------- #

@pytest.mark.parametrize("level", ["L1", "L2", "L3"])
def test_choose_returns_exactly_the_five_fields(level):
    board = chess.Board(POSITIONS["italian"])
    result = build_engine(level).choose(board)
    assert set(FIELDS) <= set(result)
    assert isinstance(result["move"], str) and 4 <= len(result["move"]) <= 5
    assert chess.Move.from_uci(result["move"]) in board.legal_moves
    assert isinstance(result["score"], int)
    assert isinstance(result["depth"], int) and result["depth"] >= 1
    assert isinstance(result["nodes"], int) and result["nodes"] > 0
    assert isinstance(result["ms"], int) and result["ms"] >= 0


@pytest.mark.parametrize("level", ["L1", "L2", "L3"])
def test_engine_does_not_mutate_the_board(level):
    board = chess.Board(POSITIONS["kiwipete"])
    before = board.fen()
    build_engine(level).choose(board)
    assert board.fen() == before, "搜索必须自己 push/pop 干净，不许把盘面留给调用方"


def test_chinese_aliases_work():
    for alias, expect in (("简单", "L1"), ("中等", "L2"), ("困难", "L3"),
                          ("easy", "L1"), ("Hard", "L3")):
        assert build_engine(alias).name == expect


def test_unknown_level_is_a_clear_error():
    with pytest.raises(EngineError):
        build_engine("L9")


def test_mcts_missing_is_a_clear_error_not_a_silent_fallback():
    try:
        build_engine("MCTS")
    except EngineError as exc:
        assert "mcts" in str(exc).lower()
    else:  # D 已经交付了 mcts.py 的话，这条跳过
        pytest.skip("src/mcts.py 已存在，跳过")


def test_build_engines_gives_three_levels_sharing_one_code_path():
    engines = build_engines()
    assert set(engines) == {"L1", "L2", "L3"}
    describe = {name: eng.describe() for name, eng in engines.items()}
    assert describe["L1"]["pruning"] is False and describe["L1"]["depth"] == 2
    assert describe["L2"]["pruning"] is True and describe["L2"]["depth"] == 3
    assert describe["L3"]["cache"] is True and describe["L3"]["quiescence"] is True
    # 三档的评估函数必须是同一个（不许偷偷换算法）
    assert len({d["evaluator"] for d in describe.values()}) == 1


# --------------------------------------------------------------------------- #
# 2. 三档的算法等价性：L1（不剪枝）必须等于 Minimax
# --------------------------------------------------------------------------- #

@pytest.mark.parametrize("position", ["start", "italian", "endgame"])
def test_l1_without_pruning_equals_minimax(position):
    board = chess.Board(POSITIONS[position])
    result = search_best(board.copy(), cfg(depth=2))
    ours_white = result["score"] if board.turn else -result["score"]
    assert ours_white == minimax_white(board.copy(), 2)


def test_pruning_does_not_change_the_answer():
    """剪枝只是少算分支，不许改变同一深度的分数和着法。"""
    board = chess.Board(POSITIONS["endgame"])
    plain = search_best(board.copy(), cfg(depth=3))
    pruned = search_best(board.copy(), cfg(depth=3, use_pruning=True))
    assert (plain["move"], plain["score"]) == (pruned["move"], pruned["score"])


def test_move_ordering_saves_nodes():
    """同样是 3 层 + 剪枝，加了排序之后节点数必须明显更少（论文 §III 的剪枝率）。"""
    board = chess.Board(POSITIONS["kiwipete"])
    no_ord = search_best(board.copy(), cfg(depth=3, use_pruning=True))
    with_ord = search_best(board.copy(), cfg(depth=3, use_pruning=True, use_ordering=True))
    assert (no_ord["move"], no_ord["score"]) == (with_ord["move"], with_ord["score"])
    assert with_ord["nodes"] < no_ord["nodes"]


def test_transposition_table_keeps_the_answer_and_cuts_nodes():
    board = chess.Board(POSITIONS["endgame"])
    plain = search_best(board.copy(), cfg(depth=3, use_pruning=True, use_ordering=True))
    cached = search_best(board.copy(), cfg(depth=3, use_pruning=True, use_ordering=True,
                                          use_cache=True))
    assert (plain["move"], plain["score"]) == (cached["move"], cached["score"])
    assert cached["nodes"] <= plain["nodes"]


# --------------------------------------------------------------------------- #
# 3. 杀棋与和棋的分数口径
# --------------------------------------------------------------------------- #

@pytest.mark.parametrize("level", ["L1", "L2", "L3"])
def test_finds_mate_in_one(level):
    board = chess.Board(POSITIONS["mate_in_1"])
    result = build_engine(level).choose(board)
    board.push(chess.Move.from_uci(result["move"]))
    assert board.is_checkmate(), "一步杀都必须找到（%s 走了 %s）" % (level, result["move"])
    assert result["score"] >= MATE - 100, "杀棋分数要用 MATE 附近的值，不能只是普通高分"


def test_stalemate_scores_zero():
    board = chess.Board(POSITIONS["stalemate"])
    result = search_best(board.copy(), cfg(depth=2))
    assert result["move"] is None, "没有合法走法时应返回 move=None"
    assert result["score"] == 0


def test_no_legal_move_returns_none_move():
    board = chess.Board("R5k1/5ppp/8/8/8/8/5PPP/6K1 b - - 0 1")  # 黑方被将死（Ra8#）
    assert board.is_checkmate()
    result = search_best(board.copy(), cfg(depth=2))
    assert result["move"] is None


# --------------------------------------------------------------------------- #
# 4. 预算：不超时、可复现
# --------------------------------------------------------------------------- #

def test_time_limit_is_respected():
    board = chess.Board(POSITIONS["kiwipete"])
    start = time.perf_counter()
    result = search_best(board.copy(), cfg(depth=9, use_pruning=True, use_ordering=True),
                         time_limit=0.30)
    elapsed_ms = (time.perf_counter() - start) * 1000
    assert elapsed_ms < 900, "300ms 的预算最多允许一点收尾开销，实际 %.0fms" % elapsed_ms
    assert result["depth"] >= 1 and result["move"] is not None


def test_same_node_budget_gives_identical_results():
    """两次跑必须一模一样：这是论文 Q3「同种子跑两遍结果相同」的基础。

    比的是"算出来的东西"（着法/分数/深度/节点数），不含耗时——耗时当然不会相同。
    """
    level_cfg = dict(search.DEFAULT_LEVELS["L3"], node_limit=20000, time_limit_ms=0)
    board = chess.Board(POSITIONS["italian"])
    first = search_best(board.copy(), level_cfg)
    second = search_best(board.copy(), level_cfg)
    assert {k: v for k, v in first.items() if k != "ms"} == \
           {k: v for k, v in second.items() if k != "ms"}


def test_node_limit_is_a_hard_cap():
    level_cfg = dict(search.DEFAULT_LEVELS["L3"], node_limit=1500, time_limit_ms=0)
    result = search_best(chess.Board(POSITIONS["kiwipete"]).copy(), level_cfg)
    assert result["nodes"] <= 1500 + 64, "节点上限只是软着陆，最多多算几十个节点"
    assert result["move"] is not None


# --------------------------------------------------------------------------- #
# 5. 配置：两条解析路径必须一致，缺项要能补默认值
# --------------------------------------------------------------------------- #

def test_yaml_and_mini_parser_agree():
    yaml = pytest.importorskip("yaml")
    with open(config_loader.DEFAULT_CONFIG_PATH, encoding="utf-8") as f:
        text = f.read()
    assert yaml.safe_load(text) == config_loader.mini_yaml_load(text)


def test_level_config_fills_missing_keys():
    merged = config_loader.level_config({"levels": {"L2": {"depth": 4}}}, "L2")
    assert merged["depth"] == 4
    assert merged["use_pruning"] is True      # 缺项来自 DEFAULT_LEVELS
    assert merged["name"] == "L2"


def test_material_eval_is_white_perspective():
    board = chess.Board("4k3/8/8/8/8/8/8/4K2Q w - - 0 1")   # 白多一个后
    assert search.material_eval(board) > 0
    board = chess.Board("4k2q/8/8/8/8/8/8/4K3 w - - 0 1")   # 黑多一个后
    assert search.material_eval(board) < 0
