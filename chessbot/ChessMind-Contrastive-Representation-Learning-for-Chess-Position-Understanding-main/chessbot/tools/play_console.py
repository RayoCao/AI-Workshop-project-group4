"""在终端里跟 AI 下一盘——最直观的验收方式。

在 chessbot/ 目录下跑：

    python tools/play_console.py                       # 你执白，对"中等"
    python tools/play_console.py --level 困难          # 对困难档
    python tools/play_console.py --level 简单 --side black

输入走法用四个字符（UCI）：e2e4、g1f3；兵升变写五个字母：e7e8q。
其他命令：hint（让我给一步建议）、undo（悔一步）、moves（列出所有合法走法）、quit（退出）。

看什么：
  · 简单档会不会白送子、中等档能不能吃到你的无保护子、困难档会不会设陷阱；
  · 每步打印的 深度 / 节点数 / 耗时，和 docs/C_三档实测表.md 应该是一个量级。
注意：这是开发自检用的命令行入口，正式演示一律走界面（02 §1.5 的"不许必须敲命令"是针对最终用户）。
"""

from __future__ import annotations

import argparse
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

try:
    import chess
except ImportError:
    print("没装 python-chess：pip install chess")
    raise SystemExit(1)

from src.engine import LEVEL_LABELS, build_engine  # noqa: E402


def render(board):
    try:
        return board.unicode(invert_color=False, borders=True)
    except Exception:
        return str(board)


def describe(result, board):
    """把五字段翻译成一句人话。分数换算成白方视角，方便对照。"""
    white_score = result["score"] if board.turn else -result["score"]
    tag = "白方" if white_score >= 0 else "黑方"
    return ("引擎：%-5s 白方视角 %+6d（%s好 %.2f 个兵） 深度 %d  节点 %-7d 耗时 %d ms"
            % (result["move"], white_score, tag, abs(white_score) / 100.0,
               result["depth"], result["nodes"], result["ms"]))


def main(argv=None):
    parser = argparse.ArgumentParser(description="终端人机对战")
    parser.add_argument("--level", default="中等", help="简单 / 中等 / 困难 / 自创")
    parser.add_argument("--side", default="white", choices=("white", "black"),
                        help="你执哪一方")
    parser.add_argument("--time", type=float, default=None,
                        help="每步最多几秒；不传就用 config.yaml 的预算")
    args = parser.parse_args(argv)

    engine = build_engine(args.level)
    human_is_white = args.side == "white"
    board = chess.Board()

    print("你对 %s（%s），你执%s。输入 e2e4 这样的四字符走法；hint / undo / moves / quit。\n"
          % (engine.label, engine.name, "白" if human_is_white else "黑"))

    plies = 0
    while not board.is_game_over(claim_draw=True):
        human_turn = board.turn == human_is_white
        if human_turn:
            print(render(board))
            print("轮到你了。")
            while True:
                cmd = input("> ").strip().lower()
                if cmd in ("quit", "exit", "q"):
                    print("再见。")
                    return 0
                if cmd == "moves":
                    print(" ".join(sorted(m.uci() for m in board.legal_moves)))
                    continue
                if cmd == "undo":
                    # 退两步：你的 + 电脑的
                    for _ in range(2):
                        if board.move_stack:
                            board.pop()
                    print("已退回你上一步之前。")
                    print(render(board))
                    continue
                if cmd == "hint":
                    result = engine.choose(board.copy())
                    print("建议：%s（深度 %d，%d 节点，%d ms）"
                          % (result["move"], result["depth"], result["nodes"], result["ms"]))
                    continue
                try:
                    move = chess.Move.from_uci(cmd)
                except ValueError:
                    print("看不懂，示例：e2e4 / g1f3 / e7e8q")
                    continue
                if move not in board.legal_moves:
                    print("这步不合法。输 moves 看能走哪些。")
                    continue
                board.push(move)
                plies += 1
                break
        else:
            print("AI 思考中……")
            result = engine.choose(board.copy(), time_limit=args.time)
            if result["move"] is None:
                break
            print(describe(result, board))
            board.push(chess.Move.from_uci(result["move"]))
            plies += 1

    print("\n" + render(board))
    if board.is_checkmate():
        loser = "白方" if board.turn else "黑方"
        print("将死：%s输，%s赢。" % (loser, "黑方" if board.turn else "白方"))
    elif board.is_stalemate():
        print("逼和（stalemate）：和棋。")
    else:
        print("对局结束：%s" % board.result(claim_draw=True))
    print("共 %d 个半回合。" % plies)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
