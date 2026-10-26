"""依赖钩子的类型 —— 旧版本。GeoPoint 需要 enc_hook/dec_hook 才能编解码。"""

from __future__ import annotations

import msgspec
from msgspec import Struct


class GeoPoint:
    """msgspec 原生不支持的自定义类型（inspect 中表现为 CustomType）。"""

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
