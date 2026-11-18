"""C 的实测脚本：跑出"三档实测对照表"（02 §2.7 · C 的第 3 条交付物）。

在 chessbot/ 目录下跑：

    python tools/bench_levels.py                  # 默认 6 个局面 × 每档 3 次
    python tools/bench_levels.py --repeats 1      # 赶时间
    python tools/bench_levels.py --positions quick

它会做三件事：
  1. 三个档位在固定局面上各算一步，记录 深度 / 节点数 / 耗时 / 静态搜索节点数；
  2. 同一个局面连算两遍，比对 着法+分数+节点数——不相等就说明搜索不可复现（论文 Q3）；
  3. 把结果写成 experiments/results/level_benchmark.csv 和 docs/C_三档实测表.md。

这些数字就是论文第 3 章那张"三档实测对照表"的来源，F 写第 5 章时也直接引用它。
"""

from __future__ import annotations

import argparse
import csv
import os
import sys
import time

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)
if ROOT not in sys.path:
    sys.path.insert(0, ROOT)

try:  # 只影响控制台中文显示
    sys.stdout.reconfigure(encoding="utf-8")
except Exception:
    pass

import chess  # noqa: E402

from src.engine import build_engines  # noqa: E402

# 固定局面：开局 / 两种中局 / 两种战术复杂的局面 / 残局
POSITIONS = [
    ("开局·标准棋", chess.STARTING_FEN),
    ("中局·意大利", "r1bqk1nr/pppp1ppp/2n5/2b1p3/2B1P3/5N2/PPPP1PPP/RNBQK2R w KQkq - 4 4"),
    ("中局·Kiwipete", "r3k2r/p1ppqpb1/bn2pnp1/3PN3/1p2P3/2N2Q1p/PPPBBPPP/R3K2R w KQkq - 0 1"),
    ("中局·封闭兵型", "r1bqk2r/pp2bppp/2n1pn2/3p4/3P4/2N1PN2/PP3PPP/R1BQKB1R w KQkq - 0 1"),
    ("残局·车兵", "8/2p5/3p4/KP5r/1R3p1k/8/4P1P1/8 w - - 0 1"),
    ("残局·三子", "8/5k2/8/8/8/8/5PK1/4R3 w - - 0 1"),
]

QUICK = POSITIONS[:3]


def run_one(engine, fen, repeats):
    """同一局面连跑 repeats 次，返回 [(结果, stats), ...]。"""
    board = chess.Board(fen)
    runs = []
    for _ in range(repeats):
        work = board.copy()
        result = engine.choose(work)
        runs.append((result, engine.last_stats))
    return runs


def main(argv=None):
    parser = argparse.ArgumentParser(description="三档实测对照表")
    parser.add_argument("--repeats", type=int, default=3, help="每个局面跑几次（取最慢/平均）")
    parser.add_argument("--positions", choices=("all", "quick"), default="all")
    parser.add_argument("--level", default="L1,L2,L3", help="只测这几档，逗号分隔")
    args = parser.parse_args(argv)

    positions = POSITIONS if args.positions == "all" else QUICK
    engines = build_engines()
    wanted = [name.strip().upper() for name in args.level.split(",") if name.strip()]
    engines = {name: engines[name] for name in wanted if name in engines}

    print("评估函数：", next(iter(engines.values())).evaluator_source)
    print("局面 %d 个，每档每局面 %d 次；python %s\n"
          % (len(positions), args.repeats, sys.version.split()[0]))

    rows, problems = [], []
    for level, engine in engines.items():
        d = engine.describe()
        print("[%s] 深度上限 %s / 剪枝 %s / 排序 %s / 置换表 %s / 静态搜索 %s / 节点上限 %s"
              % (level, d["depth"], d["pruning"], d["ordering"], d["cache"],
                 d["quiescence"], d["node_limit"]))
        for name, fen in positions:
            runs = run_one(engine, fen, args.repeats)
            results = [r for r, _ in runs]
            stats = [s for _, s in runs]

            keys = {(r["move"], r["score"], r["nodes"]) for r in results}
            if len(keys) > 1:
                problems.append("%s / %s 两次结果不一致：%s" % (level, name, keys))

            depths = [r["depth"] for r in results]
            nodes = [r["nodes"] for r in results]
            mss = [r["ms"] for r in results]
            rows.append({
                "level": level,
                "position": name,
                "move": results[0]["move"],
                "score": results[0]["score"],
                "depth": max(depths),
                "nodes": round(sum(nodes) / len(nodes)),
                "ms_avg": round(sum(mss) / len(mss)),
                "ms_max": max(mss),
                "qnodes": round(sum(s["qnodes"] for s in stats) / len(stats)),
                "tt_size": max(s["tt_size"] for s in stats),
            })
            print("    %-16s 着法 %-5s 分数 %7d 深度 %d 节点 %7d 平均 %5dms 最慢 %5dms"
                  % (name, results[0]["move"], results[0]["score"], max(depths),
                     rows[-1]["nodes"], rows[-1]["ms_avg"], rows[-1]["ms_max"]))
        print()

    write_csv(rows)
    write_markdown(rows, positions, args.repeats,
                   next(iter(engines.values())).evaluator_source.split("←")[0].strip())

    print("可复现性：", "全部一致 ✅" if not problems else "有问题 ❌")
    for p in problems:
        print("  -", p)

    slowest = max(r["ms_max"] for r in rows if r["level"] == "L3") if any(
        r["level"] == "L3" for r in rows) else None
    if slowest is not None:
        print("困难档最慢一步：%dms（论文 Q1 要求 ≤2000ms）→ %s"
              % (slowest, "达标 ✅" if slowest <= 2000 else "超标 ❌"))
    return 0 if not problems and (slowest is None or slowest <= 2000) else 1


def write_csv(rows):
    out_dir = os.path.join(ROOT, "experiments", "results")
    os.makedirs(out_dir, exist_ok=True)
    path = os.path.join(out_dir, "level_benchmark.csv")
    # utf-8-sig 带 BOM：F 用 Excel 双击打开时中文列才不会是乱码
    with open(path, "w", newline="", encoding="utf-8-sig") as f:
        writer = csv.DictWriter(f, fieldnames=list(rows[0]))
        writer.writeheader()
        writer.writerows(rows)
    print("CSV →", path)


def write_markdown(rows, positions, repeats, evaluator_source):
    out_dir = os.path.join(ROOT, "docs")
    os.makedirs(out_dir, exist_ok=True)
    path = os.path.join(out_dir, "C_三档实测表.md")

    levels = list(dict.fromkeys(r["level"] for r in rows))
    lines = ["# 三档实测对照表（由 tools/bench_levels.py 自动生成）", "",
             "- 生成时间：%s" % time.strftime("%Y-%m-%d %H:%M:%S"),
             "- 局面数：%d；每档每局面重复 %d 次（取平均，最慢单独记）" % (len(positions), repeats),
             "- 评估函数：%s（D 的 evaluate.py 交付后重跑本脚本即可刷新）" % evaluator_source,
             "", "## 汇总", "",
             "| 档位 | 平均深度 | 平均节点数 | 平均耗时 (ms) | 最慢一步 (ms) | 静态搜索节点 |",
             "| --- | --- | --- | --- | --- | --- |"]

    for level in levels:
        sub = [r for r in rows if r["level"] == level]
        lines.append("| %s | %.1f | %d | %d | %d | %d |" % (
            level,
            sum(r["depth"] for r in sub) / len(sub),
            sum(r["nodes"] for r in sub) / len(sub),
            sum(r["ms_avg"] for r in sub) / len(sub),
            max(r["ms_max"] for r in sub),
            sum(r["qnodes"] for r in sub) / len(sub),
        ))

    lines += ["", "## 逐局面明细", "",
              "| 档位 | 局面 | 着法 | 分数 | 深度 | 节点数 | 平均耗时 (ms) |",
              "| --- | --- | --- | --- | --- | --- | --- |"]
    for r in rows:
        lines.append("| %s | %s | %s | %d | %d | %d | %d |"
                     % (r["level"], r["position"], r["move"], r["score"],
                        r["depth"], r["nodes"], r["ms_avg"]))

    with open(path, "w", encoding="utf-8") as f:
        f.write("\n".join(lines) + "\n")
    print("Markdown →", path)


if __name__ == "__main__":
    raise SystemExit(main())
