"""G4 组实验：剪枝消融（同样 3 层，只改"剪不剪枝"这一个变量）。

论文里的说法（02 §2.6）：
    G4 = 同样 3 层：不剪枝 vs 剪枝 → 剪枝能省掉多少计算量

为什么必须单独写一个脚本而不是"随手跑两下"：
    消融实验最容易被质疑的就是"你改了不止一个变量"。
    这里两组唯一不同的设置是 use_pruning，其余（深度、评估函数、局面、
    走法排序、置换表、静态搜索、节点上限、时间上限）全部固定，
    并且额外校验两组给出的着法与分数必须**完全一致**（剪枝只该省节点，不该改答案）。

跑法（chessbot/ 目录下，约 1–2 分钟）：
    python tools/g4_ablation.py
    python tools/g4_ablation.py --depth 3 --positions 4
"""

from __future__ import annotations

import argparse
import csv
import os
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)
if ROOT not in sys.path:
    sys.path.insert(0, ROOT)

try:
    sys.stdout.reconfigure(encoding="utf-8")
except Exception:
    pass

import chess  # noqa: E402

from src import search             # noqa: E402
from src.engine import _load_evaluator  # noqa: E402

POSITIONS = [
    ("开局", chess.STARTING_FEN),
    ("意大利", "r1bqk1nr/pppp1ppp/2n5/2b1p3/2B1P3/5N2/PPPP1PPP/RNBQK2R w KQkq - 4 4"),
    ("Kiwipete", "r3k2r/p1ppqpb1/bn2pnp1/3PN3/1p2P3/2N2Q1p/PPPBBPPP/R3K2R w KQkq - 0 1"),
    ("封闭兵型", "r1bqk2r/pp2bppp/2n1pn2/3p4/3P4/2N1PN2/PP3PPP/R1BQKB1R w KQkq - 0 1"),
    ("中局混战", "r2qkb1r/pp2pppp/2n2n2/2pp4/3P1B2/2P1PN2/PP3PPP/RN1QKB1R w KQkq - 0 1"),
    ("残局", "8/2p5/3p4/KP5r/1R3p1k/8/4P1P1/8 w - - 0 1"),
]


def base_cfg(depth):
    """消融实验的"对照常量"：除了 use_pruning，下面的键两组完全一样。"""
    return {
        "name": "G4",
        "depth": depth,
        "use_ordering": False,      # 排序会改变剪枝率，消融时必须关掉，否则是第二个变量
        "use_cache": False,         # 置换表会改变节点数，同理
        "use_quiescence": False,    # 静态搜索会改变搜索树形状
        "node_limit": 10 ** 9,      # 不截断：要的是完整节点数，不是"跑 2 秒算到哪"
        "time_limit_ms": 0,         # 不限时
    }


def run_arm(ev, level_cfg, board):
    result = search.search_best(board.copy(), level_cfg, evaluator=ev)
    return result


def main(argv=None):
    parser = argparse.ArgumentParser(description="G4 剪枝消融")
    parser.add_argument("--depth", type=int, default=3, help="两组的深度（固定，默认 3 层）")
    parser.add_argument("--positions", type=int, default=4, help="用前 N 个局面（默认 4）")
    args = parser.parse_args(argv)

    ev, source = _load_evaluator()
    positions = POSITIONS[: max(1, args.positions)]
    print("评估函数：%s" % source)
    print("深度固定 %d 层；排序/置换表/静态搜索/节点上限/时间上限 两组完全一致" % args.depth)
    print("唯一变量：use_pruning（False vs True）\n")

    off = dict(base_cfg(args.depth), use_pruning=False)
    on = dict(base_cfg(args.depth), use_pruning=True)

    rows = []
    ok = True
    print("%-10s %8s %8s %8s %9s %9s %s"
          % ("局面", "不剪枝节点", "剪枝节点", "省掉", "不剪枝(ms)", "剪枝(ms)", "同着法/同分数"))
    for name, fen in positions:
        board = chess.Board(fen)
        a = run_arm(ev, off, board)
        b = run_arm(ev, on, board)
        same = (a["move"] == b["move"] and a["score"] == b["score"])
        ok = ok and same
        saved = 0.0 if not a["nodes"] else 100.0 * (1 - b["nodes"] / a["nodes"])
        rows.append({
            "position": name,
            "depth": args.depth,
            "nodes_no_pruning": a["nodes"],
            "nodes_pruning": b["nodes"],
            "saved_pct": round(saved, 1),
            "ms_no_pruning": a["ms"],
            "ms_pruning": b["ms"],
            "move": a["move"],
            "score": a["score"],
            "same_answer": "是" if same else "否",
        })
        print("%-10s %8d %8d %7.1f%% %9d %9d %s"
              % (name, a["nodes"], b["nodes"], saved, a["ms"], b["ms"],
                 "是" if same else "否（!! 剪枝改变了答案）"))

    total_off = sum(r["nodes_no_pruning"] for r in rows)
    total_on = sum(r["nodes_pruning"] for r in rows)
    overall = 100.0 * (1 - total_on / total_off) if total_off else 0.0
    print("\n合计：不剪枝 %d 节点 → 剪枝 %d 节点，省 %.1f%%"
          % (total_off, total_on, overall))
    print("答案一致性：%s" % ("全部一致 ✅" if ok else "出现不一致 ❌"))

    write_csv(rows, args.depth)
    write_markdown(rows, args.depth, overall, ok, len(positions))
    return 0 if ok else 1


def write_csv(rows, depth):
    out_dir = os.path.join(ROOT, "experiments", "results")
    os.makedirs(out_dir, exist_ok=True)
    path = os.path.join(out_dir, "g4_ablation.csv")
    with open(path, "w", newline="", encoding="utf-8-sig") as f:
        writer = csv.DictWriter(f, fieldnames=list(rows[0]))
        writer.writeheader()
        writer.writerows(rows)
    print("CSV →", path)


def write_markdown(rows, depth, overall, ok, n_positions):
    out_dir = os.path.join(ROOT, "docs")
    os.makedirs(out_dir, exist_ok=True)
    path = os.path.join(out_dir, "C_G4剪枝消融.md")
    lines = [
        "# G4 · 剪枝消融实验（tools/g4_ablation.py 自动生成）",
        "",
        "## 实验设计（只有一个变量）",
        "",
        "| 设置 | 不剪枝组 | 剪枝组 |",
        "| --- | --- | --- |",
        "| 搜索深度 | %d | %d |" % (depth, depth),
        "| Alpha-Beta 剪枝 | 关 | **开** |",
        "| 走法排序 / 置换表 / 静态搜索 | 关 / 关 / 关 | 关 / 关 / 关 |",
        "| 节点上限 / 时间上限 | 无 / 无 | 无 / 无 |",
        "| 评估函数 | 同一个 | 同一个 |",
        "",
        '> 排序、置换表、静态搜索两组都关掉：它们都会改变搜索树形状，',
        '放进对照组就变成「改了不止一个变量」。',
        "",
        "## 结果",
        "",
        "| 局面 | 不剪枝节点 | 剪枝节点 | 省掉 | 不剪枝耗时(ms) | 剪枝耗时(ms) | 答案一致 |",
        "| --- | --- | --- | --- | --- | --- | --- |",
    ]
    for r in rows:
        lines.append("| %s | %d | %d | %.1f%% | %d | %d | %s |"
                     % (r["position"], r["nodes_no_pruning"], r["nodes_pruning"],
                        r["saved_pct"], r["ms_no_pruning"], r["ms_pruning"], r["same_answer"]))
    lines += [
        "",
        "**合计：%d → %d 节点，省 %.1f%%；两组的着法与分数%s。**"
        % (sum(r["nodes_no_pruning"] for r in rows), sum(r["nodes_pruning"] for r in rows),
           overall, "完全一致" if ok else "出现不一致"),
        "",
        "## 怎么看这张表",
        "",
        '1. 剪枝是「纯赚」：节点数大幅下降，而同一深度的着法与分数一位不差 → ',
        '论文里可以写成 *pruning reduces the search tree without changing the decision*。',
        '2. 省下的比例越大，说明走法越好找、树越窄；深度越深、局面越封闭，省得越多。',
        '3. 这张表只回答「剪枝省多少」，不回答「哪档更强」——强度是 G1/G2 的活。',
        "",
    ]
    with open(path, "w", encoding="utf-8") as f:
        f.write("\n".join(lines) + "\n")
    print("Markdown →", path)


if __name__ == "__main__":
    raise SystemExit(main())
