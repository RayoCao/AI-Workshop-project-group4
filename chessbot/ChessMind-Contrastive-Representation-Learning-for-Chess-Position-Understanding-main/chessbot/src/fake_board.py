"""假规则：只为让界面先动起来，等 B 的真规则好了就换掉。

三个函数名就是今天的约定（B 的真 board.py 必须用同样的名字和返回格式）：
  get_board()            -> (8x8 的布局, 现在轮到谁走)
  moves_from(格子)        -> 这个格子的子能走到哪些格子
  make_move(从, 到)       -> True 走成了 / False 走不了

布局约定：8 行 8 列，第 0 行是棋盘最上面（黑方底线），
         每格是 "wP"/"bK" 这样的字符串，空格子用 None。
"""

START = [
    ["bR", "bN", "bB", "bQ", "bK", "bB", "bN", "bR"],
    ["bP"] * 8,
    [None] * 8,
    [None] * 8,
    [None] * 8,
    [None] * 8,
    ["wP"] * 8,
    ["wR", "wN", "wB", "wQ", "wK", "wB", "wN", "wR"],
]


def get_board():
    return [row[:] for row in START], True


def moves_from(square):
    return ["e3", "e4"] if square == "e2" else []


def make_move(a, b):
    return True
