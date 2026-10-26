"""array_like 遥测采样 —— 新版本（v2）。"""

from __future__ import annotations

from typing import Annotated

from msgspec import Meta, Struct


class Sample(Struct, array_like=True):
    # 新定义把 metric 与 value 的顺序对调，并在尾部追加 source
    timestamp: int
    value: float
    metric: str
    qualities: Annotated[list[str], Meta(max_length=8)] = []
    source: str = "default"
