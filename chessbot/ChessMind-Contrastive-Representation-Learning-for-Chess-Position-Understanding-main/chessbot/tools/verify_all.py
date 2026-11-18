"""一条命令体检 C 的交付：接口契约 + 算法正确性 + 预算 + 可复现。

在 chessbot/ 目录下跑：

    python tools/verify_all.py            # 约 1~2 分钟
    python tools/verify_all.py --quick    # 跳过最慢的两项，约 20 秒

每项都会打印 ✅ / ❌ 和该看什么，最后给一行总结与退出码：
    0 = 全部通过（可以交差）
    1 = 有不通过项（把 ❌ 那一行发群里）

它检查的是"我自己能保证的东西"：搜索写得对不对、快不快、可不可复现。
三档到底谁强谁弱要靠批量对局（G1–G5，F 跑），这里只用几局冒烟证明方向没写反。
"""

from __future__ import annotations

import argparse
import os
import sys
import time

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)
if ROOT not in sys.path:
    sys.path.insert(0, ROOT)

try:
    sys.stdout.reconfigure(encoding="utf-8")
except Exception:
    pass

try:
    import chess
except ImportError:
    print("❌ 没装 python-chess。先执行：  pip install chess")
    print("   （或者临时用：set PYTHONPATH=E:\\AI Workshop\\_tmp\\pylibs）")
    raise SystemExit(1)

from src import search                                    # noqa: E402
from src.config_loader import DEFAULT_CONFIG_PATH, load_config  # noqa: E402
from src.engine import build_engine, build_engines         # noqa: E402

RESULTS = []
MATE_LINE = search.MATE - 1000

ITALIAN = "r1bqk1nr/pppp1ppp/2n5/2b1p3/2B1P3/5N2/PPPP1PPP/RNBQK2R w KQkq - 4 4"
KIWIPETE = "r3k2r/p1ppqpb1/bn2pnp1/3PN3/1p2P3/2N2Q1p/PPPBBPPP/R3K2R w KQkq - 0 1"
ENDGAME = "8/2p5/3p4/KP5r/1R3p1k/8/4P1P1/8 w - - 0 1"
MATE_IN_1 = "6k1/5ppp/8/8/8/8/5PPP/R5K1 w - - 0 1"
STALEMATE = "7k/5Q2/6K1/8/8/8/8/8 b - - 0 1"
MATED = "R5k1/5ppp/8/8/8/8/5PPP/6K1 b - - 0 1"


def check(name, fn):
    try:
        detail = fn()
        print("✅ %-34s %s" % (name, detail or ""))
        RESULTS.append((name, True, detail))
    except AssertionError as exc:
        print("❌ %-34s %s" % (name, exc))
        RESULTS.append((name, False, str(exc)))
    except Exception as exc:  # 崩溃也算不通过，别让脚本自己挂掉
        print("❌ %-34s 异常：%r" % (name, exc))
        RESULTS.append((name, False, repr(exc)))


# --------------------------------------------------------------------------- #

def sec(title):
    print("\n" + title)


def main(argv=None):
    parser = argparse.ArgumentParser(description="C 的交付体检")
    parser.add_argument("--quick", action="store_true", help="跳过耗时最长的两项")
    parser.add_argument("--report", nargs="?", const=os.path.join(ROOT, "reports"),
                        default=None,
                        help="额外写一份 Markdown 验收报告（可给路径或目录，默认 chessbot/reports/）")
    parser.add_argument("--with-tests", action="store_true",
                        help="顺便跑一遍 pytest tests，把结果写进报告")
    args = parser.parse_args(argv)

    t_start = time.perf_counter()
    cfg = load_config()
    engines = build_engines()

    sec("一、环境")
    print("   python %s" % sys.version.split()[0])
    print("   python-chess %s" % chess.__version__)
    print("   配置      %s" % os.path.basename(DEFAULT_CONFIG_PATH))
    for name, eng in engines.items():
        d = eng.describe()
        print("   %s(%s) 深度%s 剪枝%s 排序%s 置换表%s 静态搜索%s 节点上限%s 评估=%s"
              % (name, d["label"], d["depth"], d["pruning"], d["ordering"],
                 d["cache"], d["quiescence"], d["node_limit"], d["evaluator"]))

    sec("二、接口契约（02 §2.4 的五字段）")

    def contract():
        bad = []
        for lvl, eng in engines.items():
            board = chess.Board(ITALIAN)
            before = board.fen()
            r = eng.choose(board)
            for f in ("move", "score", "depth", "nodes", "ms"):
                if f not in r:
                    bad.append("%s 缺 %s" % (lvl, f))
            if r.get("move") and chess.Move.from_uci(r["move"]) not in chess.Board(ITALIAN).legal_moves:
                bad.append("%s 返回了非法走法 %s" % (lvl, r["move"]))
            if board.fen() != before:
                bad.append("%s 把盘面改了" % lvl)
        assert not bad, "; ".join(bad)
        return "三档都返回五字段、走法合法、不动调用方盘面"

    check("三档 choose() 契约", contract)

    sec("三、算法正确性")

    def minimax_white(board, depth, ply=0, ev=None):
        """教科书 Maximin（MAX/MIN 交替），用来当参照答案。"""
        ev = ev or search.material_eval
        if depth <= 0:
            if board.is_check() and not any(board.legal_moves):
                return (-search.MATE + ply) if board.turn else (search.MATE - ply)
            return ev(board)
        moves = list(board.legal_moves)
        if not moves:
            return ((-search.MATE + ply) if board.turn else (search.MATE - ply)) if board.is_check() else 0
        vals = []
        for m in moves:
            board.push(m)
            try:
                vals.append(minimax_white(board, depth - 1, ply + 1, ev))
            finally:
                board.pop()
        return max(vals) if board.turn else min(vals)

    def equivalence():
        for fen, label in ((ITALIAN, "意大利"), (ENDGAME, "车兵残局")):
            board = chess.Board(fen)
            r = search.search_best(board.copy(), {"depth": 2, "name": "T", "time_limit_ms": 0,
                                                  "node_limit": 10 ** 9})
            ours = r["score"] if board.turn else -r["score"]
            ref = minimax_white(board.copy(), 2)
            assert ours == ref, "%s：negamax %d ≠ minimax %d" % (label, ours, ref)
        return "L1（不剪枝）与独立 Minimax 参照实现分数逐位相等"

    check("关掉剪枝 ≡ Minimax", equivalence)

    def pruning():
        board = chess.Board(ENDGAME)
        plain = search.search_best(board.copy(), {"depth": 3, "name": "T", "time_limit_ms": 0,
                                                  "node_limit": 10 ** 9})
        pruned = search.search_best(board.copy(), {"depth": 3, "use_pruning": True,
                                                   "name": "T", "time_limit_ms": 0,
                                                   "node_limit": 10 ** 9})
        assert (plain["move"], plain["score"]) == (pruned["move"], pruned["score"]), "剪枝改变了答案"
        return "3 层：剪枝前后着法与分数相同（%s）" % plain["move"]

    check("剪枝不改变答案", pruning)

    def ordering():
        board = chess.Board(KIWIPETE)
        base = {"depth": 3, "use_pruning": True, "name": "T", "time_limit_ms": 0,
                "node_limit": 10 ** 9}
        no_ord = search.search_best(board.copy(), dict(base))
        with_ord = search.search_best(board.copy(), dict(base, use_ordering=True))
        assert with_ord["nodes"] < no_ord["nodes"], "排序没有省节点"
        save = 100.0 * (1 - with_ord["nodes"] / no_ord["nodes"])
        return "同一局面 3 层：%d → %d 节点，省 %.0f%%" % (no_ord["nodes"], with_ord["nodes"], save)

    check("走法排序确实省节点", ordering)

    def mate():
        for lvl, eng in engines.items():
            board = chess.Board(MATE_IN_1)
            r = eng.choose(board)
            board.push(chess.Move.from_uci(r["move"]))
            assert board.is_checkmate(), "%s 没找到一步杀（走了 %s）" % (lvl, r["move"])
            assert r["score"] >= MATE_LINE, "%s 杀棋分数不对：%d" % (lvl, r["score"])
        return "三档都在一步内将死，分数落在 MATE 附近"

    check("一步杀", mate)

    def terminal():
        r1 = search.search_best(chess.Board(MATED), {"depth": 2, "name": "T", "time_limit_ms": 0,
                                                     "node_limit": 10 ** 9})
        assert r1["move"] is None, "被将死时应返回 move=None"
        r2 = search.search_best(chess.Board(STALEMATE), {"depth": 2, "name": "T",
                                                         "time_limit_ms": 0, "node_limit": 10 ** 9})
        assert r2["move"] is None and r2["score"] == 0, "逼和应记 0 分"
        return "被将死 / 逼和 → move=None；逼和分数 = 0"

    check("终局判定口径", terminal)

    sec("四、预算与可复现")

    def deterministic():
        l3 = dict(search.DEFAULT_LEVELS["L3"], node_limit=12000, time_limit_ms=0)
        a = search.search_best(chess.Board(ITALIAN), l3)
        b = search.search_best(chess.Board(ITALIAN), l3)
        strip = lambda r: {k: v for k, v in r.items() if k != "ms"}
        assert strip(a) == strip(b), "两遍结果不同：%s vs %s" % (strip(a), strip(b))
        return "同局面两遍：着法/分数/深度/节点数完全一致（节点上限 12000）"

    check("可复现（Q3）", deterministic)

    if not args.quick:
        def slowest():
            worst = (0, None)
            for fen, label in ((ITALIAN, "意大利"), (KIWIPETE, "Kiwipete")):
                r = build_engine("L3").choose(chess.Board(fen))
                if r["ms"] > worst[0]:
                    worst = (r["ms"], label)
            assert worst[0] <= 2000, "困难档 %s 用了 %d ms，超过 2000" % (worst[1], worst[0])
            return "困难档最慢一步 %d ms（%s），红线 2000 ms" % (worst[0], worst[1])

        check("困难档 ≤ 2 秒（Q1）", slowest)
    else:
        print("⏭  跳过「困难档 ≤ 2 秒」（--quick）")

    sec("五、三档实测表（论文第 3 章的数据源）")

    def bench_file():
        path = os.path.join(ROOT, "experiments", "results", "level_benchmark.csv")
        assert os.path.exists(path), "还没有实测 CSV，跑 python tools/bench_levels.py"
        rows = open(path, encoding="utf-8-sig").read().strip().splitlines()
        assert len(rows) > 3, "CSV 只有 %d 行，没跑全" % len(rows)
        levels = {r.split(",")[0] for r in rows[1:]}
        assert levels == {"L1", "L2", "L3"}, "CSV 里的档位不全：%s" % levels
        return "CSV 有 %d 行数据，三档齐全；文档见 docs/C_三档实测表.md" % (len(rows) - 1)

    check("实测表存在且完整", bench_file)

    sec("六、结论")
    passed = sum(1 for _, ok, _ in RESULTS if ok)
    total = len(RESULTS)
    elapsed = time.perf_counter() - t_start
    print("   %d / %d 项通过，用时 %.1f 秒" % (passed, total, elapsed))

    test_line = None
    if args.with_tests:
        print("   正在跑 pytest（约 8 秒）……")
        test_line = run_pytest()
        print("   " + test_line)

    if args.report:
        path = write_report(args.report, passed, total, elapsed, test_line)
        print("   报告 → %s" % path)

    if passed == total:
        print("   ✅ 全部通过：C 的搜索层可以交差。")
        return 0
    print("   ❌ 有 %d 项不通过：" % (total - passed))
    for name, ok, detail in RESULTS:
        if not ok:
            print("      - %s：%s" % (name, detail))
    return 1


def run_pytest():
    """在同一个进程里跑一遍测试，返回一行摘要（失败也不抛，写进报告）。"""
    try:
        import contextlib
        import io

        import pytest
    except ImportError:
        return "pytest 未安装，跳过（pip install pytest）"
    buf = io.StringIO()
    try:
        with contextlib.redirect_stdout(buf), contextlib.redirect_stderr(buf):
            code = pytest.main(["tests", "-q", "-p", "no:cacheprovider", "--no-header"])
    except Exception as exc:                      # noqa: BLE001
        return "pytest 运行异常：%r" % (exc,)
    lines = [ln for ln in buf.getvalue().splitlines() if ln.strip()]
    tail = lines[-1] if lines else "（无输出）"
    return "pytest %s（退出码 %s）" % (tail, code)


def bench_summary():
    """从实测 CSV 汇总每档的平均深度/节点/耗时，用于报告。"""
    path = os.path.join(ROOT, "experiments", "results", "level_benchmark.csv")
    if not os.path.exists(path):
        return []
    import csv as _csv
    with open(path, encoding="utf-8-sig") as f:
        rows = list(_csv.DictReader(f))
    out = []
    for level in ("L1", "L2", "L3"):
        sub = [r for r in rows if r.get("level") == level]
        if not sub:
            continue
        n = len(sub)
        out.append({
            "level": level,
            "depth": sum(int(r["depth"]) for r in sub) / n,
            "nodes": round(sum(int(r["nodes"]) for r in sub) / n),
            "ms_avg": round(sum(int(r["ms_avg"]) for r in sub) / n),
            "ms_max": max(int(r["ms_max"]) for r in sub),
        })
    return out


def write_report(dest, passed, total, elapsed, test_line):
    """把这次体检写成一份 Markdown，可以直接发群里当验收凭证。"""
    if os.path.isdir(dest) or not os.path.splitext(dest)[1]:
        os.makedirs(dest, exist_ok=True)
        name = "C_验收报告_%s.md" % time.strftime("%Y%m%d_%H%M")
        dest = os.path.join(dest, name)
    else:
        parent = os.path.dirname(dest)
        if parent:
            os.makedirs(parent, exist_ok=True)

    lines = [
        "# C · 搜索层验收报告",
        "",
        "- 生成时间：%s" % time.strftime("%Y-%m-%d %H:%M:%S"),
        "- 机器：%s / Python %s / python-chess %s"
        % (os.environ.get("COMPUTERNAME", "?"), sys.version.split()[0], chess.__version__),
        "- 结论：**%d / %d 项通过**%s，耗时 %.1f 秒"
        % (passed, total, "" if passed == total else "（有不通过项）", elapsed),
    ]
    if test_line:
        lines.append("- 单元测试：%s" % test_line)

    lines += ["", "## 一、逐项结果", "", "| # | 检查项 | 结果 | 说明 |", "| --- | --- | --- | --- |"]
    for i, (name, ok, detail) in enumerate(RESULTS, 1):
        lines.append("| %d | %s | %s | %s |"
                     % (i, name, "通过" if ok else "**不通过**",
                        (detail or "").replace("|", "/")))

    summary = bench_summary()
    if summary:
        lines += ["", "## 二、三档实测（来自 experiments/results/level_benchmark.csv）", "",
                  "| 档位 | 平均深度 | 平均节点数 | 平均耗时 (ms) | 最慢一步 (ms) |",
                  "| --- | --- | --- | --- | --- |"]
        for s in summary:
            lines.append("| %s | %.1f | %d | %d | %d |"
                         % (s["level"], s["depth"], s["nodes"], s["ms_avg"], s["ms_max"]))

    lines += [
        "", "## 三、交付物对照（02 §2.7 · C）", "",
        "| 任务书要求 | 文件 | 状态 |", "| --- | --- | --- |",
        "| search.py：三档共用一套代码 | `src/search.py` + `config.yaml` | 已交 |",
        "| engine.py：统一 choose() 五字段 | `src/engine.py` | 已交 |",
        "| 三档实测对照表 | `docs/C_三档实测表.md` + 本报告第二节 | 已交 |",
        "| 200 字“为什么省时间” | `docs/C_搜索层说明.md` §4 | 已交 |",
        "", "## 四、复现命令（在 chessbot/ 下）", "",
        "```bat",
        "pip install chess",
        "python tools\\verify_all.py --report --with-tests",
        "python tools\\bench_levels.py --repeats 2",
        "python tools\\play_console.py --level 困难",
        "```",
        "",
        "> 评估函数当前为 `material_eval` 兜底；D 的 `src/evaluate.py` 交付后重跑 bench 即可刷新。",
        "",
    ]
    with open(dest, "w", encoding="utf-8") as f:
        f.write("\n".join(lines))
    return dest


if __name__ == "__main__":
    raise SystemExit(main())
