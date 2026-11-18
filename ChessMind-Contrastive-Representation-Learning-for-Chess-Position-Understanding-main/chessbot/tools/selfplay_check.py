"""C 的自检：两档互相对打，先确认"难度越高越强"这条大方向没写反。

在 chessbot/ 目录下跑：

    python tools/selfplay_check.py --games 4                 # L2 先当白方，再换手
    python tools/selfplay_check.py --white L3 --black L2 --games 4 --time-limit 0.4

注意：这不是论文数据。论文的 G1–G5 由 F 用 src/experiment.py 跑（100 局、写 CSV、
带随机种子）。这个脚本只是 C 交付前的"冒烟验证"：如果 L3 打不过 L1，说明搜索写错了。

胜率口径与论文一致：赢 1 分、和 0.5 分，胜率 = 得分 / 局数（01 §6 术语表）。
"""

from __future__ import annotations

import argparse
import os
import random
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

from src.engine import build_engines  # noqa: E402


def play_game(white, black, rng, max_plies=200, time_limit=None):
    board = chess.Board()
    # 用小随机让每局开局不同（论文里 F 用 5 个固定开局，这里只是冒烟）
    for _ in range(rng.randint(0, 2)):
        moves = list(board.legal_moves)
        if not moves:
            break
        board.push(rng.choice(moves))

    engines = {True: white, False: black}
    plies = 0
    while not board.is_game_over(claim_draw=True) and plies < max_plies:
        engine = engines[board.turn]
        result = engine.choose(board, time_limit=time_limit)
        move = result["move"]
        if move is None:
            break
        board.push(chess.Move.from_uci(move))
        plies += 1

    outcome = board.result(claim_draw=True)
    if plies >= max_plies and outcome == "*":
        outcome = "1/2-1/2"
    if outcome == "*":
        outcome = "1/2-1/2"
    return outcome, plies


def main(argv=None):
    parser = argparse.ArgumentParser(description="两档互相对打（冒烟验证，不是论文数据）")
    parser.add_argument("--white", default="L3")
    parser.add_argument("--black", default="L2")
    parser.add_argument("--games", type=int, default=4)
    parser.add_argument("--max-plies", type=int, default=160)
    parser.add_argument("--seed", type=int, default=42)
    parser.add_argument("--time-limit", type=float, default=None,
                        help="每步最多几秒；不传就用 config.yaml 里的预算")
    args = parser.parse_args(argv)

    engines = build_engines()
    white = engines[args.white.upper()]
    black = engines[args.black.upper()]
    rng = random.Random(args.seed)

    table = {"1-0": 0, "0-1": 0, "1/2-1/2": 0}
    scored = 0.0
    for i in range(args.games):
        if i % 2 == 0:
            w, b, wname, bname = white, black, args.white, args.black
        else:
            w, b, wname, bname = black, white, args.black, args.white
        outcome, plies = play_game(w, b, rng, args.max_plies, args.time_limit)
        table[outcome] += 1
        if wname == args.white:                 # 换手后仍按"前面那个引擎"记分
            got = {"1-0": 1.0, "0-1": 0.0, "1/2-1/2": 0.5}[outcome]
        else:
            got = {"1-0": 0.0, "0-1": 1.0, "1/2-1/2": 0.5}[outcome]
        scored += got
        print("第 %d 局：%s(白) vs %s(黑) → %s，%d 个半回合" %
              (i + 1, wname, bname, outcome, plies))

    rate = scored / args.games if args.games else 0.0
    print("\n白胜 %d / 黑胜 %d / 和棋 %d" % (table["1-0"], table["0-1"], table["1/2-1/2"]))
    print("%s 对 %s：得分 %.1f / %d 局，胜率 %.0f%%（和棋算半局）"
          % (args.white, args.black, scored, args.games, rate * 100))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
