# C · 搜索层交付说明

> 对应 02 文档 §2.7 的【C · 搜索与引擎】任务书。四条交付物全部在这里能找到出处。
> 一句话：三档难度共用同一套 negamax 代码，靠 `config.yaml` 的开关分档，困难档 2 秒内出招，
> 对外只暴露一个 `choose()` 五字段接口。
>
> 2026-11-20 更新：已接入 D 的 `evaluate.py`（含白方视角适配层）与 `mcts.py`，
> 三档预算按新的评估成本重新标定过。详见 `docs/C_配置说明.md` 与 `docs/C_集成与性能报告.md`。

---

## 1. 交付清单

| 02 §2.7 要求 | 落在哪个文件 | 怎么验 |
| --- | --- | --- |
| ① `src/search.py`：三档共用同一套代码，靠 config.yaml 开关区分 | `src/search.py`（搜索）+ `config.yaml`（参数） | `pytest tests/ -q` 里"L1 等价 Minimax""剪枝不改答案"两组 |
| ② `src/engine.py`：把 search/evaluate/mcts 装配成统一 `choose()` | `src/engine.py` | `build_engine("L2").choose(board)` 返回五字段 |
| ③ 三档实测对照表（深度 / 节点数 / 耗时） | `docs/C_三档实测表.md`（自动生成）+ `experiments/results/level_benchmark.csv` | `python tools/bench_levels.py` |
| ④ "为什么这样能省时间"的 200 字说明 | 本文 §4 | — |

附带交付（不在任务书里，但没有它们交接会卡）：

- `config.yaml`：三档参数 + MCTS 参数（A 原计划交，C 先落好，A 后续改数值即可）
- `src/config_loader.py`：读 yaml；队友没装 PyYAML 时自动退回内置小解析器（两条路径结果一致，有测试）
- `tests/`：本仓库共 148 条自检（C 新增 `test_evaluate_integration.py` 10 条，覆盖评估符号、三档共用同一评估、五字段、negamax≡Minimax）
- `tools/bench_levels.py`：出三档实测表
- `tools/g4_ablation.py`：G4 剪枝消融（只改剪枝一个变量）
- `tools/gui_latency.py`：量单步阻塞时长，给 E 的界面定线程契约
- `tools/selfplay_check.py`：两档对打冒烟（**不是论文数据**，论文数据由 F 跑 G1–G5）
- `requirements.txt`：只依赖 `chess`

---

## 2. 三档参数表（`config.yaml`）

| 档位 | 界面显示 | 深度上限 | Alpha-Beta | 走法排序 | 置换表 | 静态搜索 | q_depth | 节点上限 | 时间阀 |
| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |
| L1 | 简单 | 2 | ✗ | ✗ | ✗ | ✗ | — | 2 500 | 1 200 ms |
| L2 | 中等 | 3 | ✓ | ✓ | ✗ | ✗ | — | 4 000 | 1 200 ms |
| L3 | 困难 | 5 | ✓ | ✓ | ✓ | ✓ | 2 | 10 000 | 1 900 ms |

两个预算的分工（这是"能复现"和"不超时"同时成立的唯一办法）：

- **节点上限是主约束**：算够这么多局面就收手，与机器快慢无关 → 同一局面两次跑结果**完全一样**（论文 Q3）。
- **时间阀是保险丝**：只在比本机慢的机器上才会先触发，牺牲该步的可复现性换"绝不超 2 秒"（论文 Q1）。

> 为什么比上一版的数字小了：D 的评估一次约 0.27 ms，是原先兜底评估的 50 倍。
> 预算只能按真实评估成本重算（见 `docs/C_配置说明.md` §2），否则困难档一步要 6 秒。

---

## 3. 三档实测对照表（6 个固定局面 × 每档 3 次，摘要）

| 档位 | 平均深度 | 平均节点数 | 平均耗时 | 最慢一步 | 说明 |
| --- | --- | --- | --- | --- | --- |
| L1 | 2.0 | 924 | 85 ms | 591 ms | 全宽 Minimax，无剪枝 |
| L2 | 3.0 | 1 734 | 115 ms | 535 ms | + Alpha-Beta + 排序 |
| L3 | 3.5 | 10 000 | 468 ms | **1 355 ms** | + 置换表 + 静态搜索（q_depth=2） |

- 可复现性自检：6 个局面 × 3 档 × 2 遍，着法 + 分数 + 节点数**全部一致** ✅
- 论文 Q1（困难档 ≤ 2 s）：最慢一步 1 355 ms ✅
- 逐局面明细见 `docs/C_三档实测表.md`，CSV 见 `experiments/results/level_benchmark.csv`

> 上表用的评估函数是 **D 的 `evaluate`**（经 C 的白方视角适配层 + 预载权重 + 缓存），
> `engine.describe()` 里会打印实际来源。

**强度方向自检**（小样本，只证明"没写反"）：

| 对局 | 结果 |
| --- | --- |
| L3 vs L2（4 局，换手） | 见 `docs/C_集成与性能报告.md` §5 |
| L2 vs L1（4 局，换手） | 同上 |

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

## 7. D 的模块已接上（2026-11-20）

| 模块 | 状态 | 说明 |
| --- | --- | --- |
| `src/evaluate.py` | 已接入 | 但 D 给的是**走子方视角**的 `evaluate()`，项目约定是**白方视角**；C 在 `engine.py` 加了适配层 `evaluate_white_from()`，并改用 `evaluate_breakdown(board, 预载权重)` 省掉每次读 JSON（609 µs → 268 µs，结果逐局面一致） |
| `src/mcts.py` | 已接入 | D 的 `choose_move()` 只返回 `chess.Move`，`engine.py` 的 `MCTSEngine` 补齐五字段：`depth=0`、`nodes=0`（D 的接口不暴露访问次数）、`score` 用同一个白方视角评估函数打 |
| `configs/eval_weights.json` | 已放置 | 权重真正生效的文件是它，`config.yaml` 里那份只是抄本 |

> `build_engine("MCTS")` 现在能正常返回引擎，不再报错；G3 组（困难 vs MCTS）可以直接跑。

---

## 8. 已知取舍（答辩可能被问）

1. **L3 的"5 层"是上限不是常态**：中局 2 秒内通常到 3–4 层，残局才到 4–5 层。表里写的是**实测深度**，不是标称深度——这样老师问起来有数可查。
2. **节点上限会让 L3 的着法依赖预算**：改 `node_limit` 会改变同一局面的选择。论文数据必须用**同一份 config.yaml** 跑完 100 局，中途不要调参（这也是 01 §13 "evaluate.py 别针对个别局面调参"的同一条纪律）。
3. **评估成本是现在的天花板**：D 的 `evaluate()` 一次约 0.27 ms（mobility 项要做两次合法走法生成），所以 L3 的节点预算只能给到 1 万。按 `docs/C_配置说明.md` §6 给 D 的三条优化做完，同预算能多看 1–2 层。
4. **不吃子就不排序**（安静走法没有 killer/history 启发）：再加一层会更快，但当前 2 秒红线已经守住，工作量留给后面。

---

## 9. 复跑命令

```bash
cd chessbot
pip install chess                      # 只要这一个第三方库
pytest tests -q                        # 148 条自检（含 D 的评估/MCTS 与集成测试）
python tools/bench_levels.py           # 刷新 docs/C_三档实测表.md 与 CSV
python tools/g4_ablation.py            # G4 剪枝消融：只改剪枝一个变量
python tools/gui_latency.py            # 量单步阻塞时长（给 E）
python tools/verify_all.py             # 9 项一体检
python tools/selfplay_check.py --white L3 --black L2 --games 4   # 强度方向冒烟
```
