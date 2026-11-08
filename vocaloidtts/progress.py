"""协作式进度上报与取消。

生成流程跑在后台线程里，而 Tk 控件只能在主线程更新。热循环（逐字符解析、
逐音节算曲线）如果每次都回调，十万字符的文本会把 Tk 事件队列刷爆，所以这里
用一个限流的 :class:`Reporter`：调用方照常频繁调用 ``report()`` / ``check()``，
只有「阶段变了」「百分比变了且间隔够了」才真正回调。

取消走协作式：调用方在安全的检查点调用 :meth:`Reporter.check`，命中时抛
:class:`Cancelled`，由上层决定怎么收尾（生成流程会丢弃半成品，不写文件）。
"""
from __future__ import annotations

import time
from typing import Callable

#: ``(stage, fraction)`` —— stage 是给用户看的阶段名，fraction 是 0..1 的总进度。
ProgressCallback = Callable[[str, float], None]

#: 返回 True 表示「请停下」。
CancelCheck = Callable[[], bool]


class Cancelled(Exception):
    """调用方要求停止当前任务。"""


class Reporter:
    """把热循环里的进度和取消请求收敛成低频回调。

    参数：
        on_progress: 进度回调；为 ``None`` 时 :meth:`report` 直接返回，
                     热循环不需要为此加分支。
        should_cancel: 取消检查；为 ``None`` 时 :meth:`check` 永不抛异常。
        interval: 两次回调的最小间隔（秒），默认 50 ms。
    """

    def __init__(self, on_progress: ProgressCallback | None = None,
                 should_cancel: CancelCheck | None = None,
                 interval: float = 0.05) -> None:
        self._on_progress = on_progress
        self._should_cancel = should_cancel
        self._interval = max(0.0, float(interval))
        self._last_emit = 0.0
        self._last_stage = ""
        self._last_pct = -1
        self._parent: Reporter | None = None
        self._span = (0.0, 1.0)

    def child(self, start: float, end: float) -> Reporter:
        """返回只覆盖 ``[start, end]`` 区间的视图。

        子视图把内部 0..1 的进度映射到父视图的区间，节流与取消都委托给父视图，
        所以嵌套调用不会各自限流、也不会漏掉取消请求。
        """
        child = Reporter(interval=self._interval)
        child._parent = self
        child._span = (float(start), float(end))
        return child

    def check(self) -> None:
        """取消检查点；命中时抛 :class:`Cancelled`。"""
        if self._parent is not None:
            self._parent.check()
            return
        if self._should_cancel is not None and self._should_cancel():
            raise Cancelled()

    def report(self, stage: str, fraction: float,
               force: bool = False) -> None:
        """上报总进度。

        ``force=True`` 用于阶段切换等必须让用户看到的时刻。其余情况下，
        百分比没变、或距上次回调不足 ``interval``，都会静默跳过。
        """
        if self._parent is not None:
            start, end = self._span
            if fraction < 0.0:
                fraction = 0.0
            elif fraction > 1.0:
                fraction = 1.0
            self._parent.report(stage, start + (end - start) * fraction, force)
            return
        if self._on_progress is None:
            return
        if fraction < 0.0:
            fraction = 0.0
        elif fraction > 1.0:
            fraction = 1.0
        pct = int(fraction * 100)
        if not force:
            if stage == self._last_stage:
                if pct == self._last_pct:
                    return
                if time.monotonic() - self._last_emit < self._interval:
                    return
        self._last_emit = time.monotonic()
        self._last_stage = stage
        self._last_pct = pct
        self._on_progress(stage, fraction)

    def stage(self, stage: str, fraction: float) -> None:
        """进入一个新阶段：立即上报，不受节流限制。"""
        self.report(stage, fraction, force=True)

    def tick(self, stage: str, done: int, total: int,
             start: float = 0.0, end: float = 1.0) -> None:
        """把「第 done/total 个」折算到 ``[start, end]`` 区间内的总进度。"""
        frac = done / total if total > 0 else 1.0
        self.report(stage, start + (end - start) * frac)
