"""支付事件消息 —— 旧版本定义（v1）。

与 `v2` 一起演示 schema_compat 的全部判定类别：
字段增删、线名（别名）变化、嵌套类型、约束、标签联合、枚举、钩子与扩展。
"""

from __future__ import annotations

import enum
from typing import Annotated, Union

import msgspec
from msgspec import Meta, Struct, field


class Currency(enum.StrEnum):
    EUR = "EUR"
    USD = "USD"
    CNY = "CNY"  # v2 中被移除


class Address(Struct):
    country: str
    city: str = "-"


class Payer(Struct, tag="payer"):
    """标签联合成员：v2 中标签值改为 'individual'。"""

    name: str
    email: str | None = None


class Merchant(Struct, tag="merchant"):
    name: str
    tax_id: str = field(name="taxId")


class Payment(Struct):
    id: str
    amount: Annotated[int, Meta(ge=0)]  # v2：改线名 amountCents 且收紧为 gt=0
    currency: Currency
    payee: Union[Payer, Merchant]
    address: Address | None = None
    remark: str = ""        # v2 中被删除
    tags: list[str] = []
