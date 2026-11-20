# B × C：2026-11-20 搜索层交付审查与协作说明

## 差异范围
- `src/engine.py`: 新增局面评分缓存、预加载权重的评估快速路径、配置开关。
- `src/search.py`: 引入 `q_depth`；默认不传时等同旧版深度4。
- `config.yaml`: 新预算 L1=2500/1200ms，L2=4000/1200ms，L3=10000/1900ms、`q_depth=2`；MCTS 的 c=1.41；评估器开关与 D 的权重摘要。
- `tests/test_evaluate_integration.py`: C 的新集成测试；其余为说明、基准 CSV 和测量工具。

## 验收责任（B）
1. 在 Mac Jupyter 的 `chessbot/` 下运行完整 pytest；对照之前 180 passed, 1 skipped，增加 C 的新测试。
2. 检查 `build_engine` L1/L2/L3/MCTS 走法合法并返回五字段。
3. 先用 C 的 `tools/g4_ablation.py --depth 3 --positions 2` 复核 G4，后续可再跑全部4个固定局面。**不要**以现有 `ExperimentRunner('G4')` 的限时限节点数据推导 Alpha-Beta 的计算节省比例。
4. E 收到 `docs/C_GUI卡顿验证.md`：AI `choose()` 在后台线程，主线程 `after` 轮询 Queue，并显式显示 AI 思考状态。
5. F 收到 `docs/C_集成与性能报告.md` 和 `experiments/results/*.csv`，注意节点数不同于模型训练次数。

## 兼容性保护：五十步和重复局面

在本次整合审查中，发现 C 的新快速评估最初没有覆盖 D 的 `claim_draw=True` 语义，且缓存仅以 `_transposition_key()` 为键，容易在历史依赖型和棋中复用非和棋分数。

因此本包在 **`src/engine.py` 另外做了 B 的最小兼容修正**：当某一局面可申请和棋时，不复用缓存，快速评分返回 0；并在 `tests/test_evaluate_integration.py` 增加 **五十步和三次重复** 两项回归测试。这不是 C 原始交付的内容，合并前请 C 复核。

注意：边界检测可能增加性能成本，**C 原报告中的耗时数据不能直接作为修正后版本的实测成绩**。请在 Mac 上重跑 `tools/bench_levels.py --repeats 2`、`tools/gui_latency.py`，确认仍符合项目的每步 2 秒目标后，再决定是否调整新的节点预算。

## 文件管理
这份 ZIP 只含 C 的新增/修改和以上审查说明。D 的原版 `D_Evaluate_and_MCTS` 不在补丁中，原代码不会被覆盖。
