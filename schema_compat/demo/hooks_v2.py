"""依赖钩子的类型 —— 新版本（定义未变，演示检查器对此类节点一律判 UNKNOWN）。"""

from __future__ import annotations

import msgspec
from msgspec import Struct


class GeoPoint:
    def __init__(self, lat: float, lon: float):
        self.lat = lat
        self.lon = lon

    def __eq__(self, other):
        return (
            isinstance(other, GeoPoint)
            and self.lat == other.lat
            and self.lon == other.lon
        )

    def __repr__(self):
        return f"GeoPoint({self.lat}, {self.lon})"


class Envelope(Struct):
    point: GeoPoint
    ext: msgspec.msgpack.Ext
