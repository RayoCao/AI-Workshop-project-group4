# D 部分：评估函数与自创算法 MCTS

负责人：D；对接人：B（集成）、C（搜索）、F（论文）。

## 接口说明

- `from src.evaluate import evaluate`
  - `evaluate(board) -> int`：从**当前走子方**视角打分；正数对当前走子方有利，负数不利，单位厘兵。
  - 将死返回 `-100000`；和棋或不可继续决出的局面返回 `0`。
- `from src.evaluate import evaluate_white`
  - 集成版补充接口：固定白方视角，正数表示白方有利。
- `from src.mcts import choose_move`
  - `choose_move(board, time_limit=3.0, rollout_limit=20) -> chess.Move`
  - 不修改传入棋盘；最终按 `visits` 最大选择着法。

## 配置口径

集成运行时只由 `chessbot/configs/eval_weights.json` 读取评估权重：

- `material: 1.0`
- `pst: 1.0`
- `mobility: 2.0`

`chessbot/config.yaml` 中的 `evaluation.weights` 是文档摘要，必须与 JSON 保持同步；`mcts` 节实际控制模拟次数、时间、rollout 深度和 UCB1 的 `c`。

## MCTS复核

- 节点保存完整走法历史（`copy(stack=True)`），可识别重复局面和五十步规则。
- 终局和截断分数先换算为根方 `[-1, 1]`，回溯时再按刚走棋方换算为 `[0,1]` 奖励，符合 UCB1。
- 搜索以时间预算或配置的模拟上限终止；rollout 随机走棋，并在截断深度使用 `evaluate()`。

## G3 / G5

- G3 使用集成版 `src/mcts.py` 的 `MCTS` 类。
- G5 的 `POSITION` 分支直接调用 D 的 `evaluate()`，并转换为白方视角；`MATERIAL` 分支仅使用纯子力基线。
