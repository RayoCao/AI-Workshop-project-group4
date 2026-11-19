"""让 `pytest tests/` 在 chessbot 目录下直接跑：把仓库根（chessbot/）放进 sys.path。

队友装了 chess 才能跑；没装的话 tests/test_search.py 会整体 skip 并提示
`pip install chess`（那是 B 的依赖，requirements.txt 里第一行）。
"""

import os
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if ROOT not in sys.path:
    sys.path.insert(0, ROOT)
