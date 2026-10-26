"""array_like 遥测采样 —— 旧版本（v1），位置式线格式。"""

from __future__ import annotations

from typing import Annotated

from msgspec import Meta, Struct


class Sample(Struct, array_like=True):
    # [timestamp, metric, value, qualities...]
    timestamp: int
    metric: str
    value: float
    qualities: Annotated[list[str], Meta(max_length=4)] = []
