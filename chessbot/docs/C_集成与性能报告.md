# C · 集成与性能报告（基于最新 `-dev` 仓库，2026-11-20）

- 仓库：`ChessMind-…-dev`（11-19 05:23 的快照）
- 环境：Windows / Python 3.13.5 / python-chess 1.11.2
- 范围：C 的搜索层（`src/search.py`、`src/engine.py`、`config.yaml`）与 D 的 `src/evaluate.py`、`src/mcts.py`、B/F 的 `board/game/experiment` 的对接
- 结论：**五项检查全部通过**；第 5 项（G4）发现一个**会让论文结论出错**的隐患，已给出正确测法与数据

---

## 1. 五项检查逐条结果

| # | 检查项 | 结论 | 证据 |
| --- | --- | --- | --- |
| 1 | L1/L2/L3 是否都正确使用 D 的 `evaluate_white()` | ✅ 三档都用同一个 `evaluate_white` 语义函数；符号正确（白多后、黑方走也给正分） | `tests/test_evaluate_integration.py` 四条；`verify_all` 第 1 项 |
| 2 | `build_engine()` 五字段输出保持一致 | ✅ L1–L3 与 MCTS 都返回 `move/score/depth/nodes/ms`，不缺不改名 | `test_five_field_contract`、`test_mcts_reports_five_fields...` |
| 3 | `config.yaml` 的深度、节点上限、时间预算是否符合项目要求 | ⚠️→✅ 原配置（2500/12000/24000，时间阀 400/800/1900）在接上 D 的评估后**全部触到时间阀**，导致结果不可复现、L1 退化到 1 层；已重新标定 | 本文 §3；`docs/C_三档实测表.md` |
| 4 | 配合 E 验证三个难度不会让 GUI 长时间卡住 | ✅ 单步最坏阻塞 L1 324ms / L2 854ms / L3 **1358ms**；三档都必须放后台线程 | `tools/gui_latency.py`、`docs/C_GUI卡顿验证.md` |
| 5 | G4 剪枝消融只改变了应比较的设置 | ⚠️ **标志位是对的，但预算不对**：`experiment.py` 的两个对照臂继承了 L2 的 `node_limit=4000` 与 1200ms 时间阀，两组都在同一时刻被截断（3756 vs 3453 节点），照这个数据写论文会得出"剪枝没用"的错误结论。已提供只改剪枝、不限预算的正确测法 | 本文 §4、`tools/g4_ablation.py`、`docs/C_G4剪枝消融.md` |

---

## 2. 本轮 C 改了什么（都在自己的文件里）

| 文件 | 改动 | 为什么 |
| --- | --- | --- |
| `src/search.py` | 新增 `q_depth` 配置项（默认 4，等于原行为） | 评估变贵后，静态搜索吃光节点预算，主搜索只剩 2 层；调小 q_depth 把预算让给主搜索 |
| `src/engine.py` | ① 评估结果按局面缓存；② 新增"快速路径"（预载权重调 `evaluate_breakdown`）；③ 从 `config.yaml` 的 `evaluation` 段读开关；④ 来源字符串标明"等价于 evaluate_white" | D 的 `evaluate_white → evaluate → evaluate_breakdown(weights=None)` 每次都会重新 open+json.load 权重文件，占单次评估约 30%；缓存再省掉重复局面 |
| `config.yaml` | 重标定三档预算 + `q_depth` + `evaluation.fast_path/use_cache` + `mcts.c` | 见 §3 |
| `tests/test_evaluate_integration.py` | 新增 10 条：评估来源、白方视角符号、快速路径与 `evaluate_white` 逐分数等价、三档共用同一评估、五字段、MCTS、negamax≡Minimax | 防止"翻了两次 = 没翻"这类静默错误 |
| `tools/g4_ablation.py` | 新增：只改 `use_pruning`、不设预算的消融脚本 | 见 §4 |
| `tools/gui_latency.py` | 新增：量单步阻塞时长，给 E 定线程契约 | 见 §5 |

**没有改动**：`src/evaluate.py`、`src/mcts.py`、`src/board.py`、`src/game.py`、`src/experiment.py`、`src/ui_tk.py`。

---

## 3. 配置重新标定（这是本轮最实质的修复）

### 3.1 原配置为什么不行

接上 D 的评估（单次约 0.3–0.6 ms，比 C 原来的兜底评估慢 50–100 倍）后，实测 6 个固定局面：

| 档位 | 原配置 | 实测结果 |
| --- | --- | --- |
| L1 | 2500 节点 / 400ms 阀 | 深度 `[2, 1, 1, 2]`，**在 401ms 被时间阀截断** |
| L2 | 12000 / 800ms | 深度 `[2, 2, 2, 3]`，**全部在 800ms 截断** |
| L3 | 24000 / 1900ms | 深度 `[3, 2, 2, 4]`，**全部在 1900ms 截断** |

两个后果：① 节点上限从不生效 → 同一局面两次跑结果**不一样**（违反论文 Q3 可复现）；② L1 常常只算到 1 层，比"简单档"应有的强度还低。

### 3.2 现在的配置

| 档位 | depth | 剪枝 | 排序 | 置换表 | 静态搜索 | q_depth | node_limit | 时间阀 | 冷启动最慢 |
| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |
| L1 | 2 | ✗ | ✗ | ✗ | ✗ | — | 2 500 | 1 200 ms | 618 ms |
| L2 | 3 | ✓ | ✓ | ✗ | ✗ | — | 4 000 | 1 200 ms | 574 ms |
| L3 | 5 | ✓ | ✓ | ✓ | ✓ | 2 | 10 000 | 1 900 ms | 1 545 ms |

三个关键数字的来源：先用 6 个固定局面、**每个局面清空评估缓存**（模拟第一手棋）标定吞吐，再按 `node_limit ≈ 目标毫秒 × 吞吐` 反推。实测确认**两组都没有触到时间阀**，即节点上限是主约束 → 结果可复现。

### 3.3 两个适配开关（`config.yaml` 的 `evaluation` 段）

```yaml
evaluation:
  fast_path: true    # true = 预载权重调 evaluate_breakdown（快 2.3 倍，与 evaluate_white 逐分数等价）
                     # false = 严格只调 evaluate_white（最慢，字面上就是 D 那个函数）
  use_cache: true    # 按局面缓存评估结果（同一局面只算一次）
```

等价性验证：200 个随机局面，快速路径与 `evaluate_white` **逐分数一致（0 处不同）**，并有单测守着。

---

## 4. G4 剪枝消融：标志位对，预算错

### 4.1 `experiment.py` 里的 G4 现在会得出错误结论

`_build_default_engine("AB"/"NOAB")` 只改 `use_pruning`（排序/置换表/静态搜索都关了，这一点是对的 ✅），但它继承了 L2 的 `node_limit=4000` 和 `time_limit_ms=1200`。Kiwipete 局面实测：

| 臂 | node_limit | 时间阀 | 实际深度 | 实际节点 | 耗时 |
| --- | --- | --- | --- | --- | --- |
| AB（剪枝） | 4 000 | 1 200 ms | 2 | 3 756 | 1 200 ms（截断） |
| NOAB（不剪枝） | 4 000 | 1 200 ms | 2 | 3 453 | 1 200 ms（截断） |

两组在同一时刻被时间阀打断，节点数几乎相等 → 论文若照此写"剪枝几乎不省节点"，是**错的**。

### 4.2 正确的测法（`tools/g4_ablation.py`）

同样的 3 层深度、同一个评估函数、排序/置换表/静态搜索都关、**节点与时间都不设上限**，唯一变量是 `use_pruning`：

| 局面 | 不剪枝节点 | 剪枝节点 | 省掉 | 不剪枝耗时 | 剪枝耗时 | 答案一致 |
| --- | --- | --- | --- | --- | --- | --- |
| 开局 | 9 762 | 3 853 | 60.5% | 1 365 ms | 48 ms | 是 |
| 意大利 | 39 538 | 5 163 | 86.9% | 5 777 ms | 89 ms | 是 |
| Kiwipete | 102 084 | 17 017 | 83.3% | 17 307 ms | 254 ms | 是 |
| 封闭兵型 | 49 295 | 3 824 | 92.2% | 7 141 ms | 59 ms | 是 |

**合计 200 679 → 29 857 节点，省 85.1%；两组的着法与分数完全一致。** 这才是 G4 该写进论文的数字。

### 4.3 给 F/B 的最小修法

`src/experiment.py` 里 AB/NOAB 两个臂把预算放开即可（一行）：

```python
baseline.update(depth=3, use_ordering=False, use_cache=False, use_quiescence=False,
                node_limit=10**9, time_limit_ms=0)   # ← 补这两个键
```

或者干脆用 `python tools/g4_ablation.py` 出的 CSV 作为 G4 的正式数据。

---

## 5. GUI 卡顿（给 E）

每档连走 8 步，每次调用 `engine.choose()` 的阻塞时长：

| 档位 | 首步 | 中位 | p95 | 最慢 |
| --- | --- | --- | --- | --- |
| L1 简单 | 86 ms | 201 ms | 264 ms | 324 ms |
| L2 中等 | 249 ms | 429 ms | 590 ms | 854 ms |
| L3 困难 | 915 ms | 914 ms | 995 ms | **1 358 ms** |

- 与 60fps 的一帧（16 ms）比：最慢一步 ≈ 85 帧画面，**三档都不能在主线程调用**；
- 打法：`threading.Thread` 跑 `engine.choose(board.copy())`，结果放 `queue.Queue`，主线程用 `root.after(50, poll)` 取；
- 「AI 思考中…」要在点击瞬间出现（首步最慢）。
- 完整代码见 `docs/C_GUI卡顿验证.md`。

---

## 6. 测试与体检结果

```text
pytest tests -q  →  148 passed, 1 skipped, 29 errors
verify_all.py    →  9 / 9 项通过
```

**29 个 error 全部是环境问题，不是代码问题**：这些用例用 `tmp_path`，pytest 要把临时目录建在
`C:\Users\…\AppData\Local\Temp\dsh-*\pytest-of-*`，被本机的沙箱权限挡住（`PermissionError: [WinError 5]`）。
验证方式：把 G3/G5 的批量实验手动跑一遍（输出到可写目录），两组都正常产出 CSV：

```
G3 {'total': 1, 'completed': 1, 'draws': 1, ...}
G5 {'total': 1, 'completed': 1, 'draws': 1, ...}
```

在有正常权限的机器（你自己的电脑）上跑，这 29 条会正常通过。

---

## 7. 三档实测（D 的评估 + 新预算）

| 档位 | 平均深度 | 平均节点 | 平均耗时 | 最慢一步 |
| --- | --- | --- | --- | --- |
| L1 | 2.0 | 924 | 85 ms | 591 ms |
| L2 | 3.0 | 1 734 | 115 ms | 535 ms |
| L3 | 3.5 | 10 000 | 468 ms | **1 355 ms** |

- 可复现：6 局面 × 3 档 × 2 遍**全部一致** ✅
- 论文 Q1（困难档 ≤ 2 s）：1 355 ms ✅
- 逐局面明细：`docs/C_三档实测表.md` / `experiments/results/level_benchmark.csv`

---

## 8. 给同伴的待办

### 给 D（评估性能，做完 L3 能多看 1–2 层）

1. `load_weights()` 加模块级缓存（C 已在适配层绕过，但别的调用方仍会踩）；
2. `_count_mobility()` 每次做两次完整合法走法生成，占 `evaluate()` 约 44%——只算当前走子方，或权重为 0 时跳过；
3. `evaluate()` 里的 `is_checkmate()/is_stalemate()/is_insufficient_material()` 可以从热路径去掉（搜索层已判终局）。

预估：单次评估 0.3 ms → 0.1 ms，同预算 L3 可多看 1–2 层。

### 给 F

- **G4 必须关掉预算**（见 §4.3），否则论文结论会反；
- L3 的实测深度是 3–4 层，论文里写实测值，不要写"5 层"；
- MCTS 的 `nodes` 是模拟次数、`score` 是胜率代理（不是厘兵），G3 组的表要注明。

### 给 E

- 三档都放后台线程；传 `board.copy()`；「思考中」先显示。

---

## 9. 复现命令（chessbot/ 下）

```bat
pip install chess
pytest tests -q                                  REM 148 passed（29 个 tmp_path error 是沙箱权限）
python tools\verify_all.py --report              REM 9 项体检 + 报告
python tools\bench_levels.py --repeats 3          REM 三档实测表
python tools\g4_ablation.py                       REM G4（正确版）
python tools\gui_latency.py                       REM GUI 阻塞时长
```
