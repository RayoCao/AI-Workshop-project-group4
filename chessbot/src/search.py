"""C · 搜索层：三档共用同一套代码，靠 config.yaml 的开关区分。

对外只有一个入口：

    search_best(board, cfg, evaluator=None, time_limit=None) -> dict
        返回 02 §2.4 约定死的五个字段：
        {"move": "e2e4", "score": 35, "depth": 3, "nodes": 12000, "ms": 820}

三条不许改的约定（违反 = 界面和批量脚本全对不上）：
  1. 评估函数永远站在白方角度打分：正数 = 白方好，单位"百分之一兵"（兵 = 100）。
  2. 走法用四个字符：起点 + 终点；升变补第五个字母（e7e8q / r / b / n）。
  3. board 只用 python-chess 那一套接口：
     legal_moves / push / pop / turn / is_check / piece_at / fen。
     自己 push 的一定自己 pop（用 try/finally），不复制盘面。

三档怎么"共用一套代码"：
  L1 = 不剪枝的全宽 negamax（等价于 Minimax：同样的树、同样的节点数）
  L2 = L1 + alpha-beta 剪枝 + 走法排序
  L3 = L2 + 置换表 + 迭代加深 + 静态搜索（吃子延展）
  差别只在 cfg 里那四个开关，算法本体一个函数，这样"困难赢中等"才说明算法变强，
  而不是"换了一套别的代码"（02 §2.5 的关键点）。
"""

from __future__ import annotations

import time

# python-chess 的棋子类型常量（1..6），这里自己写数字免得依赖它的枚举名
PAWN, KNIGHT, BISHOP, ROOK, QUEEN, KING = 1, 2, 3, 4, 5, 6

# 子力价值，单位"百分之一兵"（与 01 §6 术语表一致：兵100 马320 象330 车500 后900）
VALUE = {PAWN: 100, KNIGHT: 320, BISHOP: 330, ROOK: 500, QUEEN: 900, KING: 0}

MATE = 100_000          # 将死分（远大于任何正常评估分）
MATE_LINE = MATE - 1000  # 超过这条线就认为是"算到了杀"，可以提前收工
INF = 1 << 30

# 置换表容量上限：超过就清空（纯 Python 用字典，别让它无限长）
TT_MAX = 200_000


class _Stop(Exception):
    """节点预算或时间预算用完，向上跳出搜索；根节点会保留上一层的完整结果。"""


class _Ctx:
    """一次搜索的公共上下文：预算、置换表、评估函数。"""

    __slots__ = ("nodes", "qnodes", "t0", "time_limit", "node_limit",
                 "tt", "ev", "cfg", "use_cache", "use_quiescence", "use_ordering", "q_depth")

    def __init__(self, cfg, ev, time_limit, node_limit):
        self.nodes = 0
        self.qnodes = 0
        self.t0 = time.perf_counter()
        self.time_limit = time_limit
        self.node_limit = node_limit
        self.tt = {}
        self.ev = ev
        self.cfg = cfg
        self.use_cache = bool(cfg.get("use_cache", False))
        self.use_quiescence = bool(cfg.get("use_quiescence", False))
        self.use_ordering = bool(cfg.get("use_ordering", False))
        # 吃子延展最多再往下几层：评估贵时调小它，把节点预算让给主搜索（默认 4）
        self.q_depth = int(cfg.get("q_depth", 4))

    def check_budget(self):
        if self.nodes >= self.node_limit:
            raise _Stop
        if self.time_limit is not None and (time.perf_counter() - self.t0) > self.time_limit:
            raise _Stop


# --------------------------------------------------------------------------- #
# 评估兜底：D 的 evaluate.py 还没交付时用它，交付后 engine.py 自动改用 D 的版本。
# 这里只做"子力 + 位置表"，故意简陋——它不是 C 的交付物，只是不让链路断掉。
# --------------------------------------------------------------------------- #

# 位置表（PST）：棋子的"哪一格更值钱"，行序从上往下 = 第 8 行 → 第 1 行，
# 白方按"离自己底线越远越好"读，黑方把行号翻过来读。数值单位同样是百分之一兵。
_PST_VISUAL = {
    PAWN: (
        0, 0, 0, 0, 0, 0, 0, 0,
        50, 50, 50, 50, 50, 50, 50, 50,
        10, 10, 20, 30, 30, 20, 10, 10,
        5, 5, 10, 25, 25, 10, 5, 5,
        0, 0, 0, 20, 20, 0, 0, 0,
        5, -5, -10, 0, 0, -10, -5, 5,
        5, 10, 10, -20, -20, 10, 10, 5,
        0, 0, 0, 0, 0, 0, 0, 0,
    ),
    KNIGHT: (
        -50, -40, -30, -30, -30, -30, -40, -50,
        -40, -20, 0, 0, 0, 0, -20, -40,
        -30, 0, 10, 15, 15, 10, 0, -30,
        -30, 5, 15, 20, 20, 15, 5, -30,
        -30, 0, 15, 20, 20, 15, 0, -30,
        -30, 5, 10, 15, 15, 10, 5, -30,
        -40, -20, 0, 5, 5, 0, -20, -40,
        -50, -40, -30, -30, -30, -30, -40, -50,
    ),
    BISHOP: (
        -20, -10, -10, -10, -10, -10, -10, -20,
        -10, 0, 0, 0, 0, 0, 0, -10,
        -10, 0, 5, 10, 10, 5, 0, -10,
        -10, 5, 5, 10, 10, 5, 5, -10,
        -10, 0, 10, 10, 10, 10, 0, -10,
        -10, 10, 10, 10, 10, 10, 10, -10,
        -10, 5, 0, 0, 0, 0, 5, -10,
        -20, -10, -10, -10, -10, -10, -10, -20,
    ),
    ROOK: (
        0, 0, 0, 0, 0, 0, 0, 0,
        5, 10, 10, 10, 10, 10, 10, 5,
        -5, 0, 0, 0, 0, 0, 0, -5,
        -5, 0, 0, 0, 0, 0, 0, -5,
        -5, 0, 0, 0, 0, 0, 0, -5,
        -5, 0, 0, 0, 0, 0, 0, -5,
        -5, 0, 0, 0, 0, 0, 0, -5,
        0, 0, 0, 5, 5, 0, 0, 0,
    ),
    QUEEN: (
        -20, -10, -10, -5, -5, -10, -10, -20,
        -10, 0, 0, 0, 0, 0, 0, -10,
        -10, 0, 5, 5, 5, 5, 0, -10,
        -5, 0, 5, 5, 5, 5, 0, -5,
        0, 0, 5, 5, 5, 5, 0, -5,
        -10, 5, 5, 5, 5, 5, 0, -10,
        -10, 0, 5, 0, 0, 0, 0, -10,
        -20, -10, -10, -5, -5, -10, -10, -20,
    ),
}


def _flatten_pst():
    """把"视觉行序"的表翻成"按格号直接查"的两张表：白方一张、黑方一张。"""
    white, black = {}, {}
    for pt, table in _PST_VISUAL.items():
        w = [0] * 64
        b = [0] * 64
        for sq in range(64):
            rank, file = sq >> 3, sq & 7      # rank 0 = 第 1 行（白方底线）
            w[sq] = table[(7 - rank) * 8 + file]
            b[sq] = table[rank * 8 + file]
        white[pt], black[pt] = w, b
    return white, black


_PST_W, _PST_B = _flatten_pst()
_PIECES_VALUED = (PAWN, KNIGHT, BISHOP, ROOK, QUEEN)   # 王的位置分不算：残局与中局口径相反


def material_eval(board):
    """白方视角的"子力 + 位置"分（临时兜底，D 的 evaluate.py 到位即让位）。

    用位棋盘 + bit_length 逐子累加，比 board.pieces() 建集合快一倍以上——搜索里
    每个叶子都要调它，慢一点就是几千个节点。
    """
    score = 0
    for color, sign, tables in ((True, 1, _PST_W), (False, -1, _PST_B)):
        for pt in _PIECES_VALUED:
            mask = board.pieces_mask(pt, color)
            if not mask:
                continue
            base = VALUE[pt]
            table = tables[pt]
            sub = 0
            while mask:
                lsb = mask & -mask
                sub += base + table[lsb.bit_length() - 1]
                mask ^= lsb
            score += sign * sub
    return score


# --------------------------------------------------------------------------- #
# 小工具：只碰 python-chess 的公共接口，B 的 board.py 包装层也能直接用
# --------------------------------------------------------------------------- #

def _key(board):
    """置换表的键：python-chess 自带的高效键，取不到就退回 FEN。"""
    try:
        return board._transposition_key()
    except AttributeError:
        return board.fen()


def _eval_white(board, ctx):
    s = ctx.ev(board)
    if s > MATE_LINE:
        return MATE_LINE
    if s < -MATE_LINE:
        return -MATE_LINE
    return s


def _eval_for_side(board, ctx):
    """评估函数是白方视角，negamax 要的是"当前走子方视角"，黑方走时取负。"""
    s = _eval_white(board, ctx)
    return s if board.turn else -s


def _captured_value(board, move):
    """这步棋吃了什么（用于 MVV-LVA 排序，不改变搜索正确性，只影响快慢）。"""
    victim = board.piece_at(move.to_square)
    if victim is not None:
        return VALUE[victim.piece_type]
    # 吃过路兵：目标格是空的，但确实吃了一个兵。这里只比一次 ep_square，
    # 不要调 board.is_en_passant()——那是个位运算函数，每个安静走法都调会慢一半。
    ep = board.ep_square
    if ep is not None and move.to_square == ep:
        attacker = board.piece_at(move.from_square)
        if attacker is not None and attacker.piece_type == PAWN:
            return VALUE[PAWN]
    return 0


def _ordered_moves(board, moves, tt_move=None):
    """走法排序：置换表那步 → 吃大子的小子（MVV-LVA）→ 升变 → 其余。

    剪枝只认"先搜好棋"，顺序对了，同样的深度节点数能少一大截（01 §37）。
    """
    scored = []
    for m in moves:
        if tt_move is not None and m == tt_move:
            scored.append(((0, 0), m))
            continue
        victim = _captured_value(board, m)
        if victim:
            attacker = board.piece_at(m.from_square)
            attacker_val = VALUE[attacker.piece_type] if attacker else 0
            scored.append(((1, -(victim * 16 - attacker_val)), m))
        elif getattr(m, "promotion", None):
            scored.append(((2, -VALUE[m.promotion]), m))
        else:
            scored.append(((3, 0), m))
    scored.sort(key=lambda x: x[0])
    return [m for _, m in scored]


def _captures_only(board, moves):
    """静态搜索只扩展吃子/升变，别的走法留着让评估函数去评价。"""
    keep = []
    for m in moves:
        if _captured_value(board, m) or getattr(m, "promotion", None):
            keep.append(m)
    return keep


# --------------------------------------------------------------------------- #
# 静态搜索（quiescence）：别在"换子换到一半"的时候停手（01 §35 水平线效应）
# --------------------------------------------------------------------------- #

def _quiescence(board, alpha, beta, ctx, ply, qdepth=0):
    ctx.nodes += 1
    ctx.qnodes += 1
    ctx.check_budget()

    in_check = board.is_check()
    if in_check:
        # 被将军时不能"站着不动"：必须先把将解掉（把杀棋算准）
        moves = list(board.legal_moves)
        if not moves:
            return -MATE + ply
        if qdepth >= ctx.q_depth + 2:
            return _eval_for_side(board, ctx)
        best = -INF
        for m in _ordered_moves(board, moves):
            board.push(m)
            try:
                score = -_quiescence(board, -beta, -alpha, ctx, ply + 1, qdepth + 1)
            finally:
                board.pop()
            if score > best:
                best = score
            if score > alpha:
                alpha = score
            if alpha >= beta:
                break
        return best

    # 不吃子时的静态分：随时可以停手，所以先当"已经够好"往后传
    stand = _eval_for_side(board, ctx)
    if stand >= beta:
        return stand
    if stand > alpha:
        alpha = stand

    if qdepth >= ctx.q_depth:
        return stand

    moves = _captures_only(board, list(board.legal_moves))
    if not moves:
        return stand

    best = stand
    for m in _ordered_moves(board, moves):
        board.push(m)
        try:
            score = -_quiescence(board, -beta, -alpha, ctx, ply + 1, qdepth + 1)
        finally:
            board.pop()
        if score > best:
            best = score
        if score > alpha:
            alpha = score
        if alpha >= beta:
            break
    return best


# --------------------------------------------------------------------------- #
# 主递归：negamax（L1 关掉剪枝后与 Minimax 完全等价，见 tests/test_search.py）
# --------------------------------------------------------------------------- #

def _negamax(board, depth, alpha, beta, ctx, ply):
    ctx.nodes += 1
    ctx.check_budget()

    tt_move = None
    key = None
    if ctx.use_cache:
        key = _key(board)
        hit = ctx.tt.get(key)
        if hit is not None:
            h_depth, h_score, h_flag, h_move = hit
            if h_depth >= depth:
                if h_flag == 0:                      # 精确值
                    return h_score
                if h_flag == 1 and h_score >= beta:  # 下界
                    return h_score
                if h_flag == -1 and h_score <= alpha:  # 上界
                    return h_score
            tt_move = h_move or None

    if depth <= 0:
        if board.is_check() and not any(board.legal_moves):
            return -MATE + ply
        if ctx.use_quiescence:
            return _quiescence(board, alpha, beta, ctx, ply)
        return _eval_for_side(board, ctx)

    moves = list(board.legal_moves)
    if not moves:
        if board.is_check():
            return -MATE + ply
        return 0                                  # 逼和（stalemate）记 0 分

    if ctx.use_ordering:
        moves = _ordered_moves(board, moves, tt_move)

    alpha_orig = alpha
    best_score = -INF
    best_move = None

    for m in moves:
        board.push(m)
        try:
            score = -_negamax(board, depth - 1, -beta, -alpha, ctx, ply + 1)
        finally:
            board.pop()

        if score > best_score:
            best_score = score
            best_move = m
        if score > alpha:
            alpha = score
        if ctx.cfg.get("use_pruning", False) and alpha >= beta:
            break                                 # beta 截断：这条分支不影响上面的决策

    if key is not None:
        flag = 0
        if best_score <= alpha_orig:
            flag = -1
        elif best_score >= beta:
            flag = 1
        if len(ctx.tt) >= TT_MAX:
            ctx.tt.clear()
        ctx.tt[key] = (depth, best_score, flag, best_move)

    return best_score


def _root(board, depth, ctx, prev_best=None):
    """根节点：同样一套 AB 搜索，但要把"最好的那一步"留下来。"""
    moves = list(board.legal_moves)
    if not moves:
        return 0, None
    if ctx.use_ordering:
        moves = _ordered_moves(board, moves, prev_best)

    alpha, beta = -INF, INF
    best_score, best_move = -INF, moves[0]
    for m in moves:
        board.push(m)
        try:
            score = -_negamax(board, depth - 1, -beta, -alpha, ctx, 1)
        finally:
            board.pop()
        if score > best_score:
            best_score, best_move = score, m
        if score > alpha:
            alpha = score
    return best_score, best_move


# --------------------------------------------------------------------------- #
# 对外入口
# --------------------------------------------------------------------------- #

def _resolve_time_limit(cfg, time_limit):
    if time_limit is not None:
        try:
            return None if time_limit <= 0 else float(time_limit)
        except TypeError:
            return None
    ms = cfg.get("time_limit_ms")
    return None if not ms else float(ms) / 1000.0


def search_best(board, cfg, evaluator=None, time_limit=None, stats=None):
    """算一步棋。

    参数
        board      当前局面（python-chess Board 或 B 的包装层，不改动它）
        cfg        一个难度档的参数 dict（来自 config.yaml 的 levels.<名>）
        evaluator  白方视角的评估函数；None 时用 material_eval 兜底
        time_limit 最多想几秒；None 时用 cfg 里的 time_limit_ms；<=0 表示只按节点算
        stats      可选 dict，回填 {"qnodes","tt_size","seldepth"} 给调试/论文用

    返回
        {"move": "e2e4", "score": 35, "depth": 3, "nodes": 12000, "ms": 820}
        move 为 None 表示没有合法走法（已经被将死或逼和）
    """
    ev = evaluator or material_eval
    ctx = _Ctx(cfg, ev, _resolve_time_limit(cfg, time_limit), int(cfg.get("node_limit") or 10 ** 9))

    legal = list(board.legal_moves)
    if not legal:
        return {"move": None, "score": 0, "depth": 0, "nodes": 0, "ms": 0}

    max_depth = max(1, int(cfg.get("depth", 2)))
    best_move, best_score, reached = legal[0], 0, 0

    # 第 1 层一定跑完（只有几十个节点，保证任何情况下都有棋可走）
    best_score, best_move = _root(board, 1, ctx, None)
    reached = 1

    # 之后逐层加深：任何一层被预算打断，就保留上一层已经完整算完的结果（01 §36）
    for depth in range(2, max_depth + 1):
        try:
            score, move = _root(board, depth, ctx, best_move)
        except _Stop:
            break
        best_score, best_move, reached = score, move, depth
        if abs(score) >= MATE_LINE:
            break                                  # 已经看到杀棋，不用再往深了

    ms = int((time.perf_counter() - ctx.t0) * 1000)
    if stats is not None:
        stats.update({"qnodes": ctx.qnodes, "tt_size": len(ctx.tt), "seldepth": reached,
                      "limit_nodes": ctx.node_limit,
                      "limit_ms": None if ctx.time_limit is None else int(ctx.time_limit * 1000)})

    return {
        "move": _to_uci(best_move),
        "score": int(best_score),
        "depth": int(reached),
        "nodes": int(ctx.nodes),
        "ms": ms,
    }


def _to_uci(move):
    """走法统一成四字符（升变带第五个字母）；python-chess 的 Move.uci() 就是这格式。"""
    if move is None:
        return None
    uci = getattr(move, "uci", None)
    return uci() if callable(uci) else str(move)


# 给"三档参数对照表"用的默认配置（真正的值在 config.yaml，改那里不用改代码）
DEFAULT_LEVELS = {
    "L1": {"depth": 2, "use_pruning": False, "use_ordering": False,
           "use_cache": False, "use_quiescence": False},
    "L2": {"depth": 3, "use_pruning": True, "use_ordering": True,
           "use_cache": False, "use_quiescence": False},
    "L3": {"depth": 5, "use_pruning": True, "use_ordering": True,
           "use_cache": True, "use_quiescence": True},
}
