# C · 本轮交付清单（2026-11-20，基于最新 `-dev` 仓库）

> 你给的三条交付要求：**更新后的配置说明 / 算法测试结果 / 性能报告**。
> 本包只含 C 改过或新增的文件；D 的 `evaluate.py`、`mcts.py` 与 B/F 的 `board/game/experiment` 不在包内（已在仓库里）。

---

## 一、三条交付要求 → 对应文件

| 要求 | 文件 | 一句话 |
| --- | --- | --- |
| **更新后的配置说明** | `docs/C_配置说明.md` + `config.yaml` | 每个预算数字从哪来、改它会怎样；三档新参数：2 500 / 4 000 / 10 000 节点，阀 1 200 / 1 200 / 1 900 ms |
| **算法测试结果** | `tests/test_evaluate_integration.py`（新增 10 条）+ `reports/C_验收报告_20261120_1202.md` | 148 passed / 1 skipped / 9 项体检全过；评估符号、三档共用同一评估、五字段、negamax≡Minimax |
| **性能报告** | `docs/C_集成与性能报告.md` + `docs/C_三档实测表.md` + 三个 CSV | 三档深度/节点/耗时、GUI 阻塞时长、G4 消融、评估成本分析 |

## 二、逐文件说明

### 代码（C 的文件）

| 文件 | 改了什么 |
| --- | --- |
| `src/search.py` | 新增 `q_depth` 配置项（默认 4 = 原行为），评估贵时把吃子延展的节点让给主搜索 |
| `src/engine.py` | 评估结果缓存 + 快速路径（预载权重调 `evaluate_breakdown`）+ 从 config 读开关；来源字符串标明"等价于 evaluate_white" |
| `config.yaml` | 三档预算重标定 + `q_depth: 2` + `evaluation.fast_path/use_cache` + `mcts.c` |
| `tests/test_evaluate_integration.py` | 新增 10 条集成测试 |

### 文档

| 文件 | 用途 |
| --- | --- |
| `docs/C_配置说明.md` | 参数来源、调参后果、评估接入链路、给 D 的性能优化建议 |
| `docs/C_集成与性能报告.md` | **主报告**：五项检查结果、G4 隐患、性能数据、给 D/E/F 的待办 |
| `docs/C_G4剪枝消融.md` | G4 正确测法：200 679 → 29 857 节点，省 85.1%，答案不变 |
| `docs/C_GUI卡顿验证.md` | 三档阻塞时长 + 给 E 的后台线程代码 |
| `docs/C_三档实测表.md` | 6 局面 × 3 档 × 3 次的实测表（论文第 3 章数据源） |
| `docs/C_搜索层说明.md` | 搜索层总说明（含 200 字、论文第 3 章英文草稿） |
| `docs/C_验收清单.md` | 10 分钟人工验收步骤 |

### 数据与存档

| 文件 | 用途 |
| --- | --- |
| `experiments/results/level_benchmark.csv` | 三档实测原始数据 |
| `experiments/results/g4_ablation.csv` | G4 消融原始数据（**论文 G4 用这个，不要用 experiment.py 现跑的**） |
| `experiments/results/gui_latency.csv` | GUI 阻塞时长原始数据 |
| `reports/C_验收报告_20261120_1202.md` | 体检存档（9/9 通过） |

### 脚本（复查用）

`tools/verify_all.py`（9 项体检）、`tools/bench_levels.py`（重出实测表）、`tools/g4_ablation.py`（G4）、`tools/gui_latency.py`（GUI 延迟）、`tools/play_console.py`（命令行人机）、`tools/selfplay_check.py`（对打冒烟）

## 三、本轮最重要的两个结论（转述给组里）

1. **三档预算必须重标定**：原配置（2500/12000/24000）在接上 D 的评估后全部被时间阀截断，L1 会退到 1 层、同局面两次结果不同。现在 2 500 / 4 000 / 10 000，冷启动最慢 618 / 574 / 1 545 ms，节点上限生效 → 可复现。

2. **G4 现在跑出来的数据是错的**：`experiment.py` 的 AB/NOAB 继承了 L2 的 4000 节点 + 1200ms 阀，两臂同时被截断（3756 vs 3453 节点），会得出"剪枝没用"的反结论。正确数据是 200 679 → 29 857（省 85.1%）。修法见报告 §4.3 或直接用 `experiments/results/g4_ablation.csv`。

## 四、怎么复查（5 分钟）

```bat
REM 把本包内容覆盖到 <repo>\chessbot\ 后
pip install chess
python tools\verify_all.py            REM 期望 9/9
pytest tests -q                        REM 期望 148 passed（29 个 error 是本机沙箱 tmp 目录权限，非代码）
python tools\bench_levels.py --repeats 2
python tools\play_console.py --level 困难
```

## 五、包里没有的

- `src/evaluate.py`、`src/mcts.py`：D 的成果，仓库里已有，C 只做适配
- `src/board.py`、`src/game.py`、`src/experiment.py`、`src/ui_tk.py`：B/F/E 的文件，C 一行没改
- `__pycache__`、`.pytest_cache`：运行缓存
