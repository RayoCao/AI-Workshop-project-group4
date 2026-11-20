# C · 配置说明（config.yaml 怎么读、怎么改）

> 这份文档回答一件事：`chessbot/config.yaml` 里每个数字是从哪来的、改它会怎样。
> 2026-11-20 更新：接上 D 的 `evaluate.py` 之后，所有预算重新标定过。

---

## 1. 现在的三档参数

| 档位 | 界面显示 | depth | 剪枝 | 排序 | 置换表 | 静态搜索 | q_depth | node_limit | time_limit_ms |
| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |
| L1 | 简单 | 2 | ✗ | ✗ | ✗ | ✗ | — | 2 500 | 1 200 |
| L2 | 中等 | 3 | ✓ | ✓ | ✗ | ✗ | — | 4 000 | 1 200 |
| L3 | 困难 | 5 | ✓ | ✓ | ✓ | ✓ | 2 | 10 000 | 1 900 |

- `depth`：搜索深度上限（迭代加深逐层往上跑，到上限停）。
- `node_limit`：**主约束**，算够这么多局面就收手。它与机器快慢无关，所以同一局面两次跑结果完全一致（论文 Q3）。
- `time_limit_ms`：**安全阀**，只在比本机更慢的机器上先触发，用来守 2 秒红线（论文 Q1）。
- `q_depth`：静态搜索最多再往下延伸几层。评估很贵的时候调小它，把节点预算让给主搜索——L3 从 4 改成 2 之后，主搜索深度从 2 层回到 3–4 层。

---

## 2. 这些数字是怎么定的（不是拍脑袋）

标定方法：6 个固定局面（开局 / 意大利中局 / Kiwipete / 封闭兵型 / 中局混战 / 残局），
**每个局面先把评估缓存清空**（模拟界面第一手棋的冷启动），再量"算到多少节点 / 花多少毫秒"。

| 档位 | 冷启动最慢一步 | 实测深度 | 是否节点限先到（可复现） |
| --- | --- | --- | --- |
| L1 | 618 ms | 2 | 是 |
| L2 | 574 ms | 3 | 是 |
| L3 | 1 545 ms | 3–4（残局 4 层） | 是 |

关键事实：**D 的评估一次约 0.27 ms**（不含缓存命中），比 C 早期用的兜底评估（约 0.005 ms）慢 50 倍。
所以节点预算必须按 `毫秒 ÷ 0.27ms` 估，不能照搬"没有评估成本"时的数字。
上一版的 24 000 节点预算是按兜底评估定的，接上 D 的评估后直接变成 6 秒——这批数字就是这样重算出来的。

---

## 3. 改哪个键会怎样（想调难度就看这张表）

| 改这个 | 立刻发生的效果 | 风险 |
| --- | --- | --- |
| `depth` | 加减一层；每加一层节点数涨 3–10 倍（剪枝后） | 加一层很容易顶破 2 秒 |
| `node_limit` | 最直接的"强度↔时间"旋钮，且保持可复现 | 调小了 L3 会退化成"深一点的 L2" |
| `time_limit_ms` | 只在慢机器上生效；一旦生效，该步结果不再可复现 | 别设到 2 000 以下太近，留 10% 余量 |
| `use_pruning` | L1→L2 的本质区别；关掉后节点数涨 5–7 倍 | 关掉 L1 就别再给它大 node_limit，会超时 |
| `use_ordering` | 只影响速度，不影响答案（G4 之外的另一半） | 关掉后剪枝效率大幅下降 |
| `use_cache` | L3 的置换表；省重复计算 | 纯 Python 字典，别把 node_limit 设太大 |
| `use_quiescence` | 战术准确度明显提升，但节点消耗大 | 配上 `q_depth` 一起调 |
| `q_depth` | 评估贵时的救命旋钮 | 调太小（如 1）会漏掉连续吃子 |

**改难度只该改这三样**：`depth`、`node_limit`、`time_limit_ms`。开关（剪枝/排序/置换表/静态搜索）是"算法身份"，动了就等于换了另一档，论文里的归因会失效。

---

## 4. 评估权重不在 config.yaml 里

真正生效的是 **`configs/eval_weights.json`**（D 的 `load_weights()` 读这个文件）：

```json
{ "material": 1.0, "pst": 1.0, "mobility": 2.0 }
```

`config.yaml` 的 `evaluation.weights` 只是一份抄本，方便查；**改权重请改 json**，否则会和 D 的实现不一致（这个坑我在文档里标了，别踩第二次）。

---

## 5. 评估是怎么接进来的（C 的适配层）

```
configs/eval_weights.json ──┐
                            ├─► src/evaluate.py: evaluate_breakdown(board, weights)
src/evaluate.py ────────────┘            │
                                         ▼
                     src/engine.py: evaluate_white()  ← 把"走子方视角"翻成"白方视角"
                                         │            + 预载权重（免每次读 JSON）
                                         │            + 结果缓存（同一局面只算一次）
                                         ▼
                     src/search.py: negamax 的叶子评估（白方视角）
```

三处必须记住：

1. **符号**：D 的 `evaluate()` 是 `board.turn` 视角，项目约定（02 §2.4 约定二）是白方视角。
   适配层在黑方走时取负；漏了这一步，搜索会主动帮对手走棋（棋力直接塌，但单元测试看不出来）。
   本仓库里 B 已经加了 `evaluate_white()`，C 的引擎优先用它。
2. **性能**：`evaluate_white → evaluate → evaluate_breakdown(weights=None)` 每次都要重新 open + json.load
   一遍权重文件，占单次评估约 30%。C 在适配层改成"预载权重 + 缓存"（`fast_path: true`），
   与 `evaluate_white` **逐分数等价**（200 个局面 0 处不同，有单测），冷启动吞吐提升约 1.7 倍。
   想严格只走 `evaluate_white`，把 `evaluation.fast_path` 设成 false。
3. **口径**：终局（将死/逼和/子力不足）由适配层手工补齐，与 D 的 `evaluate()` 一致。

---

## 6. 建议 D 做的三项优化（做完可以恢复更深的搜索）

用 cProfile 量的（400 次 `evaluate()`，中局局面）：

| 开销 | 占比 | 建议 |
| --- | --- | --- |
| `load_weights()` 每次重新 open + json.load | ~30% | 模块级缓存一次；或让调用方传 weights（C 已经在传了） |
| `_count_mobility()`：两次完整合法走法生成 | ~44% | 只算一次（当前走子方），或做成可选分项 `if weights["mobility"]` |
| `evaluate()` 里的 `is_checkmate()/is_stalemate()/is_insufficient_material()` | ~10% | 搜索层已经判终局，评估里可以去掉；留着也行，但别在热路径上重复做两次走法生成 |

预估三项做完：**268 µs → 60–100 µs**，L3 同预算能多看 1–2 层。

---

## 7. 校验配置是否生效

```bat
cd /d "...\chessbot"
python -c "from src.engine import build_engines;[print(n, e.describe()) for n,e in build_engines().items()]"
python tools\verify_all.py            REM 9 项体检，含"困难档 ≤ 2 秒"
python tools\bench_levels.py --repeats 2   REM 重出三档实测表
```

`describe()` 里会打印每一档实际生效的 `depth / node_limit / time_limit_ms / 评估函数来源`；
评估来源必须是 `src.evaluate...`，如果显示 `fallback(material)` 说明没找到 D 的文件（路径或导入出错）。
