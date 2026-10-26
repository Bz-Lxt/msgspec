"""支付事件消息 —— 新版本定义（v2）。"""

from __future__ import annotations

import enum
from typing import Annotated, Union

import msgspec
from msgspec import Meta, Struct, field


class Currency(enum.StrEnum):
    EUR = "EUR"
    USD = "USD"
    GBP = "GBP"  # 新增；CNY 被移除


class Address(Struct):
    country: str
    city: str = "-"
    zip_code: str | None = None  # 新增可选字段


class Payer(Struct, tag="individual"):  # 标签值 payer -> individual
    name: str
    email: str | None = None
    phone: str | None = None         # 新增可选字段


class Merchant(Struct, tag="merchant"):
    name: str
    tax_id: str = field(name="taxId")
    settled: bool                    # 新增必填字段


class Payment(Struct):
    id: str
    # 线名（别名）改变 + 下界约束收紧
    amount: Annotated[int, Meta(gt=0)] = field(name="amountCents")
    currency: Currency
    payee: Union[Payer, Merchant]
    address: Address | None = None
    # remark 被删除
    tags: list[str] = []
    trace_id: str = field(name="traceId", default="")  # 新增可选
