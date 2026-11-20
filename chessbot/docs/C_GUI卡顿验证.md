# GUI 卡顿验证（C ↔ E）

- 生成时间：2026-11-20 12:02:23
- 方法：每档自己走 8 步，记录每次 `engine.choose()` 的墙钟阻塞时长
- 单步最坏阻塞：**1358 ms**（论文 Q1 红线 2000 ms）

## 结论（给 E）

1. **三档都不能在主线程调用。** 最慢一步 1358 ms，相当于 84 帧画面停住；
   必须放后台线程，主线程只用 `after()` 轮询结果（下面有现成代码）。
2. **首步最慢**（评估缓存是冷的），之后会明显变快 —— 所以「AI 思考中…」的提示
要在点下棋的瞬间就出现，别等 200ms。
3. 机机对战/实验面板是连续调用，一样要放后台线程 + 进度回调，否则界面假死。

## 实测

| 档位 | 步数 | 首步 (ms) | 中位 (ms) | p95 (ms) | 最慢 (ms) | 热缓存中位 (ms) |
| --- | --- | --- | --- | --- | --- | --- |
| L1 | 8 | 86 | 201 | 264 | 324 | 205 |
| L2 | 8 | 249 | 429 | 590 | 854 | 472 |
| L3 | 8 | 915 | 914 | 995 | 1358 | 912 |

## E 的界面请照这个写

```python
# E 的界面里请这样调（后台线程 + 主线程轮询，界面全程不卡）
import queue, threading

self._queue = queue.Queue()

def think_async(self, engine, board):
    def work():
        result = engine.choose(board.copy())   # 重活在后台
        self._queue.put(result)
    threading.Thread(target=work, daemon=True).start()

def poll(self):
    try:
        result = self._queue.get_nowait()
        self.apply_move(result["move"])        # 主线程只负责画
    except queue.Empty:
        pass
    self.root.after(50, self.poll)             # 每 50ms 看一眼
```

要点：

- `engine.choose(board.copy())` —— 传副本，别让后台线程和界面同时动同一个 board；
- 后台线程**只**往 `queue.Queue` 放结果，绝不碰任何 Tk 控件；
- 主线程用 `root.after(50, poll)` 取结果，再 `apply_move()` 画棋盘；
- 想显示「AI 思考中」，在开线程之前就把状态改掉。

## 判定

- 单步最坏 1358 ms ≤ 2000 ms 红线
- 与 60fps 一帧（16 ms）比：远超，必须开线程

