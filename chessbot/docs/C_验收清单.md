# C 的交付验收清单（你按顺序走一遍，10 分钟）

> 目标：你不读代码，也能判断 C 的搜索层**是不是真的能跑、跑得对不对、快到不到位**。
> 每一步都写了"该看到什么"。看到的不一样，就把那一步的输出发我。

---

## 0. 先解决 Python 和 chess（只做一次）

这台机器上 `python` 不在 PATH 里，用 Anaconda 的完整路径。**三选一**：

```bat
REM 方式一（推荐，一次装好）
C:\Users\35068\anaconda3\python.exe -m pip install chess

REM 方式二（不装，直接借用我已经准备好的临时库，只在这台机器有效）
set PYTHONPATH=E:\AI Workshop\_tmp\pylibs
```

PowerShell 里第二种写 `$env:PYTHONPATH='E:\AI Workshop\_tmp\pylibs'`。

然后进目录（所有命令都在 `chessbot` 里跑）：

```bat
cd /d "E:\AI Workshop\ChessMind-Contrastive-Representation-Learning-for-Chess-Position-Understanding-main\chessbot"
```

> 为什么不是双击 `启动.bat`：它找的是 `%LOCALAPPDATA%\Python\bin\pythonw.exe`，这台机器上没有。
> 那是 A 的文件，我没动。验收 C 的搜索层不需要界面。

---

## 1. 一条命令出体检报告（最重要，7 秒）

```bat
C:\Users\35068\anaconda3\python.exe tools\verify_all.py
```

**该看到**：`9 / 9 项通过` + `✅ 全部通过：C 的搜索层可以交差。`

九项分别是：

| 项 | 它在证明什么 |
| --- | --- |
| 三档 choose() 契约 | 界面/批量脚本要的五个字段齐全，走法合法，不改调用方的盘面 |
| 关掉剪枝 ≡ Minimax | L1 真的是"教科书 Minimax"，不是随便写的搜索 |
| 剪枝不改变答案 | Alpha-Beta 只是少算分支，同一个深度的答案不变 |
| 走法排序确实省节点 | 同一局面 3 层，节点数从约 2 万降到 2 千（省 87%） |
| 一步杀 | 三档都能一步将死，且分数落在杀棋区间 |
| 终局判定口径 | 被将死 / 逼和都返回 `move=None`，逼和记 0 分 |
| 可复现（Q3） | 同一局面跑两遍，着法/分数/节点数一字不差 |
| 困难档 ≤ 2 秒（Q1） | 最难的局面也不破 2 秒红线 |
| 实测表存在且完整 | 论文第 3 章的数据源文件在、三档齐全 |

赶时间可以加 `--quick`（跳过最慢那项，20 秒内）。

---

## 2. 跑 27 条单元测试（10 秒）

```bat
C:\Users\35068\anaconda3\python.exe -m pytest tests -q -p no:cacheprovider
```

**该看到**：`27 passed`。

这里比体检更细：还测了"引擎不许偷偷换算法"（三档必须用同一个评估函数）、
"中文难度名能认"（`简单/中等/困难`）、"没交 mcts.py 时要明确报错而不是静默降级"。

---

## 3. 看三档的数字（约 3 分钟）

```bat
C:\Users\35068\anaconda3\python.exe tools\bench_levels.py --repeats 2
```

**该看到**（我这台机器上的基准，你机器上的数字应该在 ±30% 以内）：

| 档位 | 深度 | 平均节点数 | 平均耗时 | 最慢一步 |
| --- | --- | --- | --- | --- |
| L1 简单 | 2 | 约 900 | 约 25 ms | 约 70 ms |
| L2 中等 | 3 | 约 1 400 | 约 50 ms | 约 130 ms |
| L3 困难 | 4（残局 5） | 约 20 000 | 约 1 000 ms | 约 1 800 ms |

最后两行是自动判定，必须是：

```
可复现性： 全部一致 ✅
困难档最慢一步：xxxx ms（论文 Q1 要求 ≤2000ms）→ 达标 ✅
```

跑完会顺手刷新 `docs/C_三档实测表.md` 和 `experiments/results/level_benchmark.csv`。

---

## 4. 自己下两盘（最直观，每盘 3–5 分钟）

```bat
C:\Users\35068\anaconda3\python.exe tools\play_console.py --level 简单
C:\Users\35068\anaconda3\python.exe tools\play_console.py --level 困难
```

输入四字符走法（`e2e4`），其他命令：`hint` 要建议、`undo` 悔棋、`moves` 看合法走法、`quit` 退出。

**该看到什么差别**：

- **简单档**：只看自己吃子、不看你下一步能吃回来，经常白送一个兵/一个马；每步 10–90 ms、深度 2。
- **困难档**：会躲开明显的丢子、会算换子，中局每步 1–2 秒、深度 3–4（屏幕上会打印）。
- 两档都会把"五字段"印出来，数字和上面第 3 步的表是一个量级。

> 注意：现在用的是**兜底评估**（D 的 `evaluate.py` 还没交），所以困难档并没有"很聪明"，
> 只是比简单档明显少犯错。D 交文件后重跑第 3 步，数字会变。

---

## 5. 不看代码也能核对的三条（对着文档打勾）

打开 `docs/C_搜索层说明.md`，只看这三处是否自洽：

1. **§2 三档参数表** 的开关组合，和运行 `verify_all.py` 第一段打印出来的
   `剪枝/排序/置换表/静态搜索` 是否一致（应该是 L1 全 False、L2 前两个 True、L3 全 True）。
2. **§3 实测表** 的深度/节点/耗时，和第 3 步屏幕上的是否能对上。
3. **§4 那 200 字**：三句话（剪枝 / 少算 / 算准）在 `src/search.py` 里都能找到对应实现——
   分别是 `_negamax` 里的 alpha-beta 截断、`_ordered_moves`+`ctx.tt`、`_quiescence`。

---

## 6. 常见问题

| 现象 | 原因 | 怎么办 |
| --- | --- | --- |
| `ModuleNotFoundError: No module named 'chess'` | 没装 python-chess | 第 0 步的方式一或二 |
| 中文变成乱码 | 终端编码不是 UTF-8 | 先 `chcp 65001`，或看写出来的 `.md` / `.csv` 文件 |
| 耗时比你机器慢 2 倍以上 | CPU 不同 | 改 `config.yaml` 里 L3 的 `node_limit` 调小，我文档 §8 写了口径 |
| 双击 `启动.bat` 没反应 | 它找的 python 路径本机不存在 | A 的问题，跟我这份无关；验收用命令行 |
| `build_engine("MCTS")` 报错 | D 的 `mcts.py` 还没交（故意的） | 等 D，或先只用 L1/L2/L3 |

---

## 7. 什么算通过

一句话：**第 1 步 `9 / 9 项通过` + 第 2 步 `27 passed` + 第 3 步两行判定都是 ✅ + 第 4 步困难档明显比简单档难打。**

四条都对上，C 这条线就可以签字收工了。任何一条不对，把那条命令的输出发我，我改。
