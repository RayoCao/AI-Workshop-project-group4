"""三个页面的骨架。内容由 E 写，这里只保证程序能跑起来。

约定（E 不要改）：
  · 三个类名 HomePage / BoardPage / LabPage
  · 构造参数 (master, app)
  · 切页统一调用 app.show("home" | "board" | "lab")
"""
import tkinter as tk

BG = "#1e1e24"
FG = "#e6e6e6"
DIM = "#8a8a92"
ACCENT = "#3a6ea5"


class BasePage(tk.Frame):
    """三页共用：顶部一条「返回 + 标题」，下面留一块自留地 self.body。"""

    title = "页面"
    has_back = True

    def __init__(self, master, app):
        super().__init__(master, bg=BG)
        self.app = app

        bar = tk.Frame(self, bg=BG)
        bar.pack(fill="x", padx=16, pady=(12, 4))
        if self.has_back:
            tk.Button(bar, text="← 返回", command=lambda: app.show("home"),
                      bg="#2b2b33", fg=FG, relief="flat",
                      font=("Microsoft YaHei UI", 10)).pack(side="left")
        tk.Label(bar, text=self.title, bg=BG, fg=FG,
                 font=("Microsoft YaHei UI", 13, "bold")).pack(side="left", padx=12)

        self.body = tk.Frame(self, bg=BG)
        self.body.pack(fill="both", expand=True, padx=16, pady=12)


class HomePage(BasePage):
    """启动页：三个入口。样式和布局由 E 重写，只要保留这三条跳转。"""

    title = "启动页"
    has_back = False

    def __init__(self, master, app):
        super().__init__(master, app)
        box = tk.Frame(self.body, bg=BG)
        box.pack(expand=True)
        for text, target in (("人机对战", "board"),
                             ("机机对战", "board"),
                             ("实验面板", "lab")):
            tk.Button(box, text=text, width=16, height=2,
                      command=lambda t=target: app.show(t),
                      bg=ACCENT, fg="white", relief="flat",
                      font=("Microsoft YaHei UI", 12)).pack(pady=8)


class BoardPage(BasePage):
    title = "对局页"

    def __init__(self, master, app):
        super().__init__(master, app)
        tk.Label(self.body, text="[棋盘画在这里 —— E 负责]", bg=BG, fg=DIM,
                 font=("Microsoft YaHei UI", 12)).pack(expand=True)


class LabPage(BasePage):
    title = "实验页"

    def __init__(self, master, app):
        super().__init__(master, app)
        tk.Label(self.body, text="[组别、局数、进度条放这里 —— E + F 负责]", bg=BG, fg=DIM,
                 font=("Microsoft YaHei UI", 12)).pack(expand=True)
