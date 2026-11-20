"""GUI 卡顿验证：三档 AI 每一步到底会让界面等多久（给 E 用）。

E 的界面里"卡住"只有一个来源：在 Tk 主线程里调用 engine.choose()。
这个脚本把"一步棋的阻塞时长"量出来，结论只有两条：

  1. 单步最坏多少毫秒 —— 决定能不能放主线程（结论：都不能，必须开线程）；
  2. 三档分别是多少 —— 决定进度提示/思考动画要怎么做。

跑法（chessbot/ 目录下，约 30 秒）：
    python tools/gui_latency.py
    python tools/gui_latency.py --plies 16

输出：docs/C_GUI卡顿验证.md + experiments/results/gui_latency.csv
"""

from __future__ import annotations

import argparse
import csv
import os
import statistics
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

import chess  # noqa: E402

from src.engine import build_engines  # noqa: E402

FRAME_MS = 16          # 60 fps 的一帧：超过这个就会掉帧
RED_LINE_MS = 2000     # 论文 Q1：困难档每步不超过 2 秒

# E 可以直接抄的写法（命令行验证与界面用的是同一个 engine 对象）
THREAD_PATTERN = '''
# E 的界面里请这样调（后台线程 + 主线程轮询，界面全程不卡）
import queue, threading

self._queue = queue.Queue()

def think_async(self, engine, board):
    def work():
        result = engine.choose(board.copy())   # 重活在后台
        self._queue.put(result)
    threading.Thread(target=work, daemon=True).start()

def poll(self):
    try:
        result = self._queue.get_nowait()
        self.apply_move(result["move"])        # 主线程只负责画
    except queue.Empty:
        pass
    self.root.after(50, self.poll)             # 每 50ms 看一眼
'''


def play_and_measure(engine, plies):
    """自己跟自己下一小段，记录每一步的墙钟耗时。"""
    board = chess.Board()
    times = []
    moves = []
    for _ in range(plies):
        if board.is_game_over(claim_draw=True):
            break
        started = time.perf_counter()
        result = engine.choose(board.copy())
        elapsed = (time.perf_counter() - started) * 1000
        times.append(elapsed)
        moves.append(result["move"])
        if result["move"] is None:
            break
        board.push(chess.Move.from_uci(result["move"]))
    return times, moves


def main(argv=None):
    parser = argparse.ArgumentParser(description="GUI 阻塞时长测量")
    parser.add_argument("--plies", type=int, default=10, help="每档走多少步（默认 10）")
    args = parser.parse_args(argv)

    engines = build_engines()
    print("每档连走 %d 步，记录每次调用 choose() 的阻塞时长\n" % args.plies)

    rows = []
    summary = {}
    for name, engine in engines.items():
        times, _ = play_and_measure(engine, args.plies)
        if not times:
            continue
        cold = times[0]
        warm = times[1:] or times
        row = {
            "level": name,
            "steps": len(times),
            "first_move_ms": round(cold),
            "median_ms": round(statistics.median(times)),
            "p95_ms": round(sorted(times)[max(0, int(len(times) * 0.95) - 1)]),
            "max_ms": round(max(times)),
            "warm_median_ms": round(statistics.median(warm)),
        }
        rows.append(row)
        summary[name] = row
        print("%s(%s)：首步 %dms，中位 %dms，p95 %dms，最慢 %dms"
              % (name, engine.label, row["first_move_ms"], row["median_ms"],
                 row["p95_ms"], row["max_ms"]))

    worst = max(r["max_ms"] for r in rows) if rows else 0
    print("\n单步最坏阻塞：%d ms" % worst)
    print("与 60fps 一帧(%dms)相比：%s" % (
        FRAME_MS, "远超 → 绝不能在主线程调用" if worst > FRAME_MS else "可接受"))
    print("与论文 2 秒红线相比：%s" % ("达标 ✅" if worst <= RED_LINE_MS else "超标 ❌"))
    print("\n给 E 的写法（后台线程 + after 轮询）：")
    print(THREAD_PATTERN)

    write_csv(rows)
    write_markdown(rows, worst, args.plies)
    return 0 if worst <= RED_LINE_MS else 1


def write_csv(rows):
    out_dir = os.path.join(ROOT, "experiments", "results")
    os.makedirs(out_dir, exist_ok=True)
    path = os.path.join(out_dir, "gui_latency.csv")
    with open(path, "w", newline="", encoding="utf-8-sig") as f:
        writer = csv.DictWriter(f, fieldnames=list(rows[0]))
        writer.writeheader()
        writer.writerows(rows)
    print("CSV →", path)


def write_markdown(rows, worst, plies):
    out_dir = os.path.join(ROOT, "docs")
    os.makedirs(out_dir, exist_ok=True)
    path = os.path.join(out_dir, "C_GUI卡顿验证.md")
    lines = [
        "# GUI 卡顿验证（C ↔ E）",
        "",
        "- 生成时间：%s" % time.strftime("%Y-%m-%d %H:%M:%S"),
        "- 方法：每档自己走 %d 步，记录每次 `engine.choose()` 的墙钟阻塞时长" % plies,
        "- 单步最坏阻塞：**%d ms**（论文 Q1 红线 %d ms）" % (worst, RED_LINE_MS),
        "",
        "## 结论（给 E）",
        "",
        "1. **三档都不能在主线程调用。** 最慢一步 %d ms，相当于 %d 帧画面停住；"
        % (worst, max(1, worst // FRAME_MS)),
        "   必须放后台线程，主线程只用 `after()` 轮询结果（下面有现成代码）。",
        '2. **首步最慢**（评估缓存是冷的），之后会明显变快 —— 所以「AI 思考中…」的提示',
        "要在点下棋的瞬间就出现，别等 200ms。",
        "3. 机机对战/实验面板是连续调用，一样要放后台线程 + 进度回调，否则界面假死。",
        "",
        "## 实测",
        "",
        "| 档位 | 步数 | 首步 (ms) | 中位 (ms) | p95 (ms) | 最慢 (ms) | 热缓存中位 (ms) |",
        "| --- | --- | --- | --- | --- | --- | --- |",
    ]
    for r in rows:
        lines.append("| %s | %d | %d | %d | %d | %d | %d |"
                     % (r["level"], r["steps"], r["first_move_ms"], r["median_ms"],
                        r["p95_ms"], r["max_ms"], r["warm_median_ms"]))
    lines += [
        "",
        "## E 的界面请照这个写",
        "",
        "```python",
        THREAD_PATTERN.strip(),
        "```",
        "",
        "要点：",
        "",
        "- `engine.choose(board.copy())` —— 传副本，别让后台线程和界面同时动同一个 board；",
        "- 后台线程**只**往 `queue.Queue` 放结果，绝不碰任何 Tk 控件；",
        "- 主线程用 `root.after(50, poll)` 取结果，再 `apply_move()` 画棋盘；",
        '- 想显示「AI 思考中」，在开线程之前就把状态改掉。',
        "",
        "## 判定",
        "",
        "- 单步最坏 %d ms %s %d ms 红线" % (worst, "≤" if worst <= RED_LINE_MS else ">", RED_LINE_MS),
        "- 与 60fps 一帧（%d ms）比：%s" % (FRAME_MS, "远超，必须开线程" if worst > FRAME_MS else "可接受"),
        "",
    ]
    with open(path, "w", encoding="utf-8") as f:
        f.write("\n".join(lines) + "\n")
    print("Markdown →", path)


if __name__ == "__main__":
    raise SystemExit(main())
