"""C · 引擎层：把三档搜索（和 D 的 MCTS）装配成同一套 choose() 接口。

界面和批量脚本只认这一个东西：

    from src.engine import build_engine

    engine = build_engine("L2")                 # "L1" / "L2" / "L3" / "MCTS"
    result = engine.choose(board, time_limit=None)
    # result == {"move": "e2e4", "score": 35, "depth": 3, "nodes": 12000, "ms": 820}

五个字段一个都不能少、也不能改名（02 §2.4）。想加字段先找 A 统一改调用方。

这个文件只做"装配"：
  · 搜索本体在 src/search.py（C）
  · 评估函数在 src/evaluate.py（D）——没交付时自动退回 search.material_eval 兜底
  · 自创算法在 src/mcts.py（D）——没交付时 build_engine("MCTS") 会明确报错，不静默降级
这里不写任何棋类规则，也不写任何界面代码。
"""

from __future__ import annotations

import os

from .config_loader import level_config, load_config
from .search import material_eval, search_best

# 界面下拉框里显示什么，和引擎名怎么对应（E 直接拿这个填下拉框）
LEVEL_LABELS = {
    "L1": "简单",
    "L2": "中等",
    "L3": "困难",
    "MCTS": "自创（MCTS）",
}

# 让界面/命令行可以传中文或英文
_ALIASES = {
    "L1": "L1", "简单": "L1", "EASY": "L1",
    "L2": "L2", "中等": "L2", "MEDIUM": "L2",
    "L3": "L3", "困难": "L3", "HARD": "L3",
    "MCTS": "MCTS", "自创": "MCTS", "MCTS自创": "MCTS",
}

FIELDS = ("move", "score", "depth", "nodes", "ms")


class EngineError(RuntimeError):
    """引擎装配失败（该交的模块还没交、配置不对、返回格式不合约定）。"""


def normalize_level(name):
    key = str(name).strip().upper()
    key = _ALIASES.get(key) or _ALIASES.get(str(name).strip()) or key
    if key not in LEVEL_LABELS:
        raise EngineError("未知难度：%r（可选：%s）" % (name, " / ".join(LEVEL_LABELS)))
    return key


def _load_evaluator():
    """D 的评估函数；取不到就用兜底实现，并记下来源（论文/调试要看）。"""
    for importer in (_import_from_package, _import_absolute):
        mod = importer("evaluate")
        if mod is None:
            continue
        for attr in ("evaluate_white", "evaluate", "evaluate_board", "score"):
            fn = getattr(mod, attr, None)
            if callable(fn):
                return fn, "src.evaluate.%s" % attr
    return material_eval, "fallback(material)  ← D 的 evaluate.py 交付后自动替换"


def _load_mcts():
    for importer in (_import_from_package, _import_absolute):
        mod = importer("mcts")
        if mod is not None:
            return mod
    return None


def _import_from_package(name):
    if not __package__:
        return None
    try:
        return __import__("%s.%s" % (__package__, name), fromlist=[name])
    except Exception:
        return None


def _import_absolute(name):
    try:
        return __import__("src.%s" % name, fromlist=[name])
    except Exception:
        return None


class Engine:
    """一档搜索的对外门面：只暴露 choose()。"""

    def __init__(self, name, cfg, evaluator=None, evaluator_source="", config_path=None):
        self.name = normalize_level(name)
        self.label = LEVEL_LABELS[self.name]
        self.config_path = config_path
        self.cfg = level_config(cfg or {}, self.name)
        self.evaluator = evaluator or material_eval
        self.evaluator_source = evaluator_source or "fallback(material)"
        self._last_stats = {}

    # ---- 02 §2.4 约定 ------------------------------------------------------ #
    def choose(self, board, time_limit=None):
        result = search_best(board, self.cfg, self.evaluator,
                             time_limit=time_limit, stats=self._last_stats)
        _check_contract(result, self.name)
        return result

    # ---- 调试/论文用（不属于对外契约） -------------------------------------- #
    def describe(self):
        cfg = self.cfg
        return {
            "engine": self.name,
            "label": self.label,
            "depth": cfg.get("depth"),
            "pruning": bool(cfg.get("use_pruning")),
            "ordering": bool(cfg.get("use_ordering")),
            "cache": bool(cfg.get("use_cache")),
            "quiescence": bool(cfg.get("use_quiescence")),
            "node_limit": cfg.get("node_limit"),
            "time_limit_ms": cfg.get("time_limit_ms"),
            "evaluator": self.evaluator_source,
        }

    @property
    def last_stats(self):
        return dict(self._last_stats)

    def __repr__(self):
        return "<Engine %s %s>" % (self.name, self.label)


class MCTSEngine:
    """D 的 mcts.py 的包装层：一样满足 choose() 五字段约定。"""

    def __init__(self, module, cfg):
        self.name = "MCTS"
        self.label = LEVEL_LABELS["MCTS"]
        self._mod = module
        self.cfg = dict(cfg or {})
        self.evaluator_source = "src.mcts"
        self._impl = self._build(module)

    def _build(self, mod):
        cls = getattr(mod, "MCTS", None)
        if isinstance(cls, type):
            for kwargs in (self.cfg, {}):
                try:
                    return cls(**kwargs)
                except TypeError:
                    continue
            try:
                return cls()
            except Exception as exc:
                raise EngineError("src/mcts.py 的 MCTS 类实例化失败：%s" % exc)
        for attr in ("choose", "search_best", "mcts_choose"):
            fn = getattr(mod, attr, None)
            if callable(fn):
                return fn
        raise EngineError("src/mcts.py 里既没有 MCTS 类，也没有 choose()/search_best() 函数")

    def choose(self, board, time_limit=None):
        impl = self._impl
        if hasattr(impl, "choose"):
            result = impl.choose(board, time_limit=time_limit)
        else:
            try:
                result = impl(board, time_limit=time_limit)
            except TypeError:
                result = impl(board)
        _check_contract(result, self.name)
        return result

    def describe(self):
        return {"engine": "MCTS", "label": self.label,
                "evaluator": self.evaluator_source}

    def __repr__(self):
        return "<Engine MCTS>"


def _check_contract(result, name):
    """五个字段缺一个，就在装配阶段炸掉，而不是等批量实验跑到一半才发现。"""
    if not isinstance(result, dict):
        raise EngineError("%s 的 choose() 必须返回 dict，实际是 %r" % (name, type(result)))
    missing = [f for f in FIELDS if f not in result]
    if missing:
        raise EngineError("%s 的 choose() 少了字段：%s（02 §2.4 约定五字段不许改名）"
                          % (name, missing))
    return result


def build_engine(level, config_path=None, cfg=None, evaluator=None):
    """按难度名造一个引擎。cfg 不传就从 config.yaml 读。"""
    name = normalize_level(level)
    if cfg is None:
        cfg = load_config(config_path or _default_config_path())

    if name == "MCTS":
        mod = _load_mcts()
        if mod is None:
            raise EngineError(
                "MCTS 需要 src/mcts.py（D 负责），现在还没交付；"
                "先用 build_engine('L3') 占位，等 D 交文件后再跑 G3 组实验。")
        return MCTSEngine(mod, cfg.get("mcts") or {})

    ev, source = (evaluator, "injected") if evaluator is not None else _load_evaluator()
    return Engine(name, cfg, evaluator=ev, evaluator_source=source, config_path=config_path)


def build_engines(config_path=None):
    """一次造三档，给自检脚本和实验页用。MCTS 单独按需造（D 可能还没交付）。"""
    cfg = load_config(config_path or _default_config_path())
    ev, source = _load_evaluator()
    return {name: Engine(name, cfg, ev, source, config_path) for name in ("L1", "L2", "L3")}


def _default_config_path():
    return os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
                        "config.yaml")
