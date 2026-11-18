# C · 搜索层交付说明

> 对应 02 文档 §2.7 的【C · 搜索与引擎】任务书。四条交付物全部在这里能找到出处。
> 一句话：三档难度共用同一套 negamax 代码，靠 `config.yaml` 的四个开关分档，困难档 2 秒内出招，
> 对外只暴露一个 `choose()` 五字段接口。

---

## 1. 交付清单

| 02 §2.7 要求 | 落在哪个文件 | 怎么验 |
| --- | --- | --- |
| ① `src/search.py`：三档共用同一套代码，靠 config.yaml 开关区分 | `src/search.py`（搜索）+ `config.yaml`（参数） | `pytest tests/ -q` 里"L1 等价 Minimax""剪枝不改答案"两组 |
| ② `src/engine.py`：把 search/evaluate/mcts 装配成统一 `choose()` | `src/engine.py` | `build_engine("L2").choose(board)` 返回五字段 |
| ③ 三档实测对照表（深度 / 节点数 / 耗时） | `docs/C_三档实测表.md`（自动生成）+ `experiments/results/level_benchmark.csv` | `python tools/bench_levels.py` |
| ④ "为什么这样能省时间"的 200 字说明 | 本文 §4 | — |

附带交付（不在任务书里，但没有它们交接会卡）：

- `config.yaml`：三档参数 + 评估权重 + MCTS 参数（A 原计划交，C 先落好，A 后续改数值即可）
- `src/config_loader.py`：读 yaml；队友没装 PyYAML 时自动退回内置小解析器（两条路径结果一致，有测试）
- `tests/test_search.py`：27 条自检，覆盖接口契约、三档等价性、杀棋、预算、可复现
- `tools/bench_levels.py`：出三档实测表
- `tools/selfplay_check.py`：两档对打冒烟（**不是论文数据**，论文数据由 F 跑 G1–G5）
- `requirements.txt`：只依赖 `chess`

---

## 2. 三档参数表（`config.yaml`）

| 档位 | 界面显示 | 深度上限 | Alpha-Beta | 走法排序 | 置换表 | 静态搜索 | 节点上限 | 时间阀 |
| --- | --- | --- | --- | --- | --- | --- | --- | --- |
| L1 | 简单 | 2 | ✗ | ✗ | ✗ | ✗ | 2 500 | 400 ms |
| L2 | 中等 | 3 | ✓ | ✓ | ✗ | ✗ | 12 000 | 800 ms |
| L3 | 困难 | 5 | ✓ | ✓ | ✓ | ✓ | 24 000 | 1 900 ms |

两个预算的分工（这是"能复现"和"不超时"同时成立的唯一办法）：

- **节点上限是主约束**：算够这么多局面就收手，与机器快慢无关 → 同一局面两次跑结果**完全一样**（论文 Q3）。
- **时间阀是保险丝**：只在比本机慢 20% 以上的机器上才会先触发，牺牲该步的可复现性换"绝不超 2 秒"（论文 Q1）。

---

## 3. 三档实测对照表（6 个固定局面 × 每档 3 次，摘要）

| 档位 | 平均深度 | 平均节点数 | 平均耗时 | 最慢一步 | 静态搜索节点 |
| --- | --- | --- | --- | --- | --- |
| L1 | 2.0 | 924 | 25 ms | 66 ms | 0 |
| L2 | 3.0 | 1 368 | 47 ms | 129 ms | 0 |
| L3 | 4.0 | 20 362 | 1 033 ms | **1 825 ms** | 12 789 |

- 可复现性自检：6 个局面 × 3 档 × 2 遍，着法 + 分数 + 节点数**全部一致** ✅
- 论文 Q1（困难档 ≤ 2 s）：最慢一步 1 825 ms ✅
- 逐局面明细见 `docs/C_三档实测表.md`，CSV 见 `experiments/results/level_benchmark.csv`

> 注意：上表的评估函数是 `material_eval`（D 的 `evaluate.py` 还没交付时的兜底）。
> D 交文件后重跑 `python tools/bench_levels.py`，表会自动刷新——`engine.describe()` 里能看到当前用的是谁。

**强度方向自检**（小样本，只证明"没写反"）：

| 对局 | 结果 |
| --- | --- |
| L3 vs L2（4 局，换手） | L3 得分 3.0 / 4，胜率 75% |
| L2 vs L1（6 局，换手） | L2 得分 5.0 / 6，胜率 83% |

样本只有个位数，不能写进论文当结论；论文的 G1/G2 要用 F 的 `experiment.py` 各跑 20 局。

---

## 4. 为什么这样能省时间（200 字）

三档共用一套 negamax，省时间靠三步。一是**剪枝**：Alpha-Beta 维护 α/β 上下界，砍掉不影响结果的分支，理想排序下有效分支因子从 b 降到约 √b，同样时间能多看近一倍层数。二是**少算**：MVV-LVA 先搜"用小子吃大子"，让截断尽早发生；置换表把经不同路径到达的同一局面只算一次；迭代加深从浅到深，预算用完就交上一层结果，永远有棋可走。三是**算准**：静态搜索只延伸吃子，避免"换子换到一半"就评估造成的误判。三者都不改变同一深度的答案，只减少节点数——所以节点数、耗时、剪枝率本身就是论文里的证据。

---

## 5. 怎么用（给 A / B / E / F）

```python
from src.engine import build_engine, build_engines, LEVEL_LABELS

engine = build_engine("L2")          # 也认 "中等" / "medium"；"MCTS" 等 D 的 mcts.py
result = engine.choose(board)        # time_limit=None → 用 config.yaml 的预算
# {"move": "e2e4", "score": 35, "depth": 3, "nodes": 12000, "ms": 820}
```

- **B（game.py）**：直接调 `choose()`，五个字段都是你要的；`move` 是 UCI 四字符，`move is None` 表示这方已经没有合法走法。
- **E（界面）**：下拉框用 `LEVEL_LABELS`（简单 / 中等 / 困难 / 自创）；AI 一定放后台线程，算完再回主线程。
- **F（experiment.py）**：`build_engines()` 一次拿三档；每组实验想固定耗时就把 `time_limit` 传死，想复现就别传（用节点上限）。
- **A（main.py）**：`config.yaml` 的数值归你改，键名归 C 维护，加新键先说一声。

---

## 6. 论文第 3 章可直接改用的段落（英文草稿）

> All three difficulty levels are produced by a single negamax framework with alpha–beta
> pruning; they differ only in which enhancements are enabled. L1 runs the unpruned,
> full-width tree and is therefore mathematically equivalent to Minimax — we verify this
> equivalence by unit test, comparing the negamax score against an independent MAX/MIN
> implementation on three positions. L2 adds alpha–beta pruning together with MVV-LVA move
> ordering, which raises the pruning rate without changing the score returned at a fixed
> depth. L3 additionally enables a transposition table keyed on the position's Zobrist
> signature, quiescence search restricted to captures and promotions, and iterative
> deepening bounded by an explicit node budget. The node budget, rather than wall-clock
> time, is the primary stopping criterion, which makes every reported game reproducible;
> a wall-clock limit is kept only as a safety valve for the 2-second-per-move requirement.

配图建议（F 排版时用）：一张"同一局面三档的 深度-节点数-耗时"柱状图，数据直接用
`experiments/results/level_benchmark.csv`。

---

## 7. 还没接上的两块（等 D）

| 模块 | 现在怎么办 | D 交付后 |
| --- | --- | --- |
| `src/evaluate.py` | 自动退回 `search.material_eval`（子力 + 位置表），`describe()` 里能看到 `fallback(material)` | 什么都不用改：`engine.py` 下次启动自动改用它，重跑 bench 刷新实测表 |
| `src/mcts.py` | `build_engine("MCTS")` 会**明确报错**，不会静默降级成 L3 去污染 G3 组数据 | `mcts.py` 里放 `class MCTS`（可接受 `simulations` / `time_limit_ms`）或一个 `choose(board, time_limit=None)` 都能被装进来 |

---

## 8. 已知取舍（答辩可能被问）

1. **L3 的"5 层"是上限不是常态**：中局 2 秒内通常到 3–4 层，残局才到 5 层。表里写的是**实测深度**，不是标称深度——这样老师问起来有数可查。
2. **节点上限会让 L3 的着法依赖预算**：改 `node_limit` 会改变同一局面的选择。论文数据必须用**同一份 config.yaml** 跑完 100 局，中途不要调参（这也是 01 §13 "evaluate.py 别针对个别局面调参"的同一条纪律）。
3. **兜底评估很弱**：现在 L3 中局只到 3–4 层，很大程度是被 `material_eval` 的粗糙拖累；D 的评估到位后同样的节点数能看更深，实测表要重跑。
4. **不吃子就不排序**（安静走法没有 killer/history 启发）：再加一层会更快，但当前 2 秒红线已经守住，工作量留给后面。

---

## 9. 复跑命令

```bash
cd chessbot
pip install chess                      # 只要这一个第三方库
pytest tests/ -q                       # 27 条自检
python tools/bench_levels.py           # 刷新 docs/C_三档实测表.md 与 CSV
python tools/selfplay_check.py --white L3 --black L2 --games 4   # 强度方向冒烟
```
