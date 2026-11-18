"""启动器：只负责开窗口 + 在三个页面之间切换。

页面里画什么，全部在 src/ui_tk.py 里，归 E 负责。
这个文件写完就不再改；要加第四个页面，才需要动它。
"""
import tkinter as tk

from src.ui_tk import HomePage, BoardPage, LabPage

BG = "#1e1e24"


class App(tk.Tk):
    def __init__(self):
        super().__init__()
        self.title("AI Chess Bot")
        self.geometry("1280x800")
        self.minsize(1024, 700)
        self.configure(bg=BG)

        container = tk.Frame(self, bg=BG)
        container.pack(fill="both", expand=True)

        self.pages = {}
        for name, cls in (("home", HomePage), ("board", BoardPage), ("lab", LabPage)):
            page = cls(container, self)
            page.place(relx=0, rely=0, relwidth=1, relheight=1)
            self.pages[name] = page

        self.show("home")

    def show(self, name):
        """切页：把某一页提到最上层。"""
        self.pages[name].tkraise()


if __name__ == "__main__":
    App().mainloop()
