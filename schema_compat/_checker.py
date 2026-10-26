"""跨版本 msgspec 消息定义兼容性静态检查器。

比较同一消息的「旧定义」与「新定义」（``msgspec.inspect.Type``），对四个交换方向
分别给出结论：

- ``old_to_new``：旧版本编码器产出的数据，交给新版本解码器；
- ``new_to_old``：新版本编码器产出的数据，交给旧版本解码器；

每个方向分别判断 JSON 与 MessagePack 两种线格式。

结论等级（严重度从低到高）：

- ``SAFE``    ：保证可解码且不丢数据；
- ``LOSSY``   ：保证不报错，但存在字段被静默忽略 / 回退默认值的数据丢失；
- ``UNSAFE``  ：存在合法数据会被对端拒绝（解码报错或根本无法编码）；
- ``UNKNOWN`` ：依赖 ``enc_hook`` / ``dec_hook`` 或 MessagePack 扩展类型码，
  仅凭类型注解无法判断。

每条原因（`Issue`）都带：

- ``code``    ：稳定的机器可读原因码（见 ``ISSUE_CODES``）；
- ``path``    ：稳定、可定位的节点路径（基于 Python 字段名，与线名解耦）；
- ``cells``   ：该原因对四个「方向 × 协议」格子的影响；
- ``old``/``new``/``message``：可读细节。

入口：`check_compat(old_type, new_type)`。
"""

from __future__ import annotations

import enum
from dataclasses import dataclass, field as dc_field
from typing import Any, Union

from msgspec import NODEFAULT
from msgspec import inspect as mi

__all__ = [
    "Severity",
    "Issue",
    "CompatReport",
    "check_compat",
    "format_report",
    "report_to_jsonish",
    "ISSUE_CODES",
]


# --------------------------------------------------------------------------- #
# 结论模型
# --------------------------------------------------------------------------- #

class Severity:
    SAFE = "SAFE"
    LOSSY = "LOSSY"
    UNSAFE = "UNSAFE"
    UNKNOWN = "UNKNOWN"


_ORDER = {
    Severity.SAFE: 0,
    Severity.LOSSY: 1,
    Severity.UNSAFE: 2,
    Severity.UNKNOWN: 3,
}

OLD_TO_NEW = "old_to_new"
NEW_TO_OLD = "new_to_old"
JSON = "json"
MSGPACK = "msgpack"
DIRECTIONS = (OLD_TO_NEW, NEW_TO_OLD)
PROTOCOLS = (JSON, MSGPACK)

# 稳定原因码清单（code -> 说明）。保持只增不改。
ISSUE_CODES = {
    # 结构 / 字段
    "struct.array_like.changed": "结构体在 object 与 array 线格式之间切换",
    "field.added.required": "新增必填字段：旧数据缺少该字段",
    "field.added.optional": "新增可选字段：对端按未知字段忽略，值丢失",
    "field.removed.required": "删除的字段在对端仍为必填：对端数据缺少该字段",
    "field.removed.optional": "删除的字段在对端仍存在（可选）：回退默认值",
    "field.wire_name.changed": "字段的线名（别名/rename）改变：同一字段换了键名",
    "field.became_required": "字段由可选变为必填：旧编码方可能省略该字段",
    "field.positional.inserted": "array/位置式结构中间插入字段：后续位置整体错位",
    "field.positional.removed": "array/位置式结构中间删除字段：后续位置整体错位",
    "field.positional.reordered": "array/位置式结构字段顺序改变",
    "field.positional.too_short": "对端数据元素个数少于必填位置数",
    "field.positional.too_long": "NamedTuple 位置数量超出对端允许的最大长度",
    "field.positional.trailing_dropped": "尾部新增字段被旧 array 解码器忽略",
    # 类型
    "type.kind.changed": "线类型不兼容的类型种类变化（如 int -> str、object -> array）",
    "type.narrowed_from_any": "Any/Raw 收窄为具体类型：旧数据可以是任意值",
    "constraint.tightened": "约束收紧：旧的合法值可能被新解码器拒绝",
    "constraint.loosened": "约束放宽：新的合法值可能被旧解码器拒绝",
    "constraint.changed": "约束变化且无法判定包含关系（如正则、tz 策略互换）",
    "tuple.arity.changed": "定长 tuple 元素个数改变",
    "dict.key_type.changed": "dict 键类型变化（MessagePack 键标记严格区分）",
    # 枚举 / 字面量
    "enum.value.removed": "枚举删除了旧版本仍会发出的取值",
    "enum.value.added": "枚举新增了旧解码器不认识的取值",
    "enum.value_type.changed": "枚举值的线类型改变（数字 <-> 字符串）",
    "literal.value.removed": "Literal 删除了旧版本仍会发出的取值",
    "literal.value.added": "Literal 新增了旧解码器不认识的取值",
    # 联合 / 标签
    "union.tag_field.changed": "标签联合的 tag_field（判别键名）改变",
    "union.tag.changed": "联合成员的标签值改变",
    "union.member.removed": "标签/普通联合删除了旧数据仍可能使用的成员",
    "union.member.added": "标签/普通联合新增了旧解码器不认识的成员",
    # 扩展 / 钩子
    "ext.json.unsupported": "msgspec.msgpack.Ext 无法编码为 JSON",
    "ext.msgpack.unverifiable": "MessagePack Ext 的 type code/载荷约定不在类型注解中，"
    "只能靠扩展实现保证",
    "hook.required": "出现 msgspec 原生不支持的自定义类型，编解码依赖 enc_hook/dec_hook",
}


@dataclass(frozen=True)
class Issue:
    code: str
    path: str
    message: str
    #: cells[(direction, protocol)] -> severity
    cells: dict[t.Any, str]
    old: str | None = None
    new: str | None = None

    def directions_for(self, protocol: str) -> dict[str, str]:
        return {d: self.cells.get((d, protocol), Severity.SAFE) for d in DIRECTIONS}


@dataclass
class CompatReport:
    old_root: str
    new_root: str
    issues: list[Issue] = dc_field(default_factory=list)

    def verdict(self, direction: str, protocol: str) -> str:
        worst = Severity.SAFE
        for iss in self.issues:
            sev = iss.cells.get((direction, protocol), Severity.SAFE)
            if _ORDER[sev] > _ORDER[worst]:
                worst = sev
        return worst

    @property
    def matrix(self) -> dict[str, dict[str, str]]:
        return {
            d: {p: self.verdict(d, p) for p in PROTOCOLS} for d in DIRECTIONS
        }


# --------------------------------------------------------------------------- #
# 小工具
# --------------------------------------------------------------------------- #

def _qname(cls: Any) -> str:
    qn = getattr(cls, "__qualname__", None) or getattr(cls, "__name__", None)
    return qn or str(cls)


def _type_name(t: mi.Type) -> str:
    """去掉约束参数后的短类型名，用于 old/new 展示。"""
    if isinstance(t, mi.Metadata):
        return _type_name(t.type)
    name = type(t).__name__
    if isinstance(t, mi.StructType):
        return f"{name}({_qname(t.cls)})"
    if isinstance(t, (mi.EnumType, mi.CustomType)):
        return f"{name}({_qname(t.cls)})"
    return name


def _short(t: mi.Type | None) -> str | None:
    if t is None:
        return None
    if isinstance(t, mi.Metadata):
        return _short(t.type)
    extras = []
    if isinstance(t, mi.StructType):
        extras.append(_qname(t.cls))
        if t.array_like:
            extras.append("array_like")
        if t.tag is not None:
            extras.append(f"tag={t.tag!r}")
            extras.append(f"tag_field={t.tag_field or 'type'!r}")
        if t.forbid_unknown_fields:
            extras.append("forbid_unknown_fields")
    elif isinstance(t, (mi.EnumType, mi.CustomType)):
        extras.append(_qname(t.cls))
    for attr in ("gt", "ge", "lt", "le", "multiple_of", "min_length",
                 "max_length", "pattern", "tz"):
        val = getattr(t, attr, None)
        if val is not None:
            extras.append(f"{attr}={val!r}")
    if isinstance(t, mi.LiteralType):
        extras.append(f"values={t.values!r}")
    base = type(t).__name__
    return f"{base}({', '.join(extras)})" if extras else base


def _uniform_cells(o2n: str, n2o: str) -> dict[tuple[str, str], str]:
    """两种协议结论一致时的便捷构造。"""
    return {
        (OLD_TO_NEW, JSON): o2n,
        (OLD_TO_NEW, MSGPACK): o2n,
        (NEW_TO_OLD, JSON): n2o,
        (NEW_TO_OLD, MSGPACK): n2o,
    }


def _cells(o2n_json: str, o2n_mp: str, n2o_json: str, n2o_mp: str):
    return {
        (OLD_TO_NEW, JSON): o2n_json,
        (OLD_TO_NEW, MSGPACK): o2n_mp,
        (NEW_TO_OLD, JSON): n2o_json,
        (NEW_TO_OLD, MSGPACK): n2o_mp,
    }


_S = Severity


# --------------------------------------------------------------------------- #
# 主比较器
# --------------------------------------------------------------------------- #

def check_compat(old_type: Any, new_type: Any) -> CompatReport:
    """比较两个 msgspec 兼容类型（类型注解或 ``inspect.Type``）。"""
    if not isinstance(old_type, mi.Type):
        old_type = mi.type_info(old_type)
    if not isinstance(new_type, mi.Type):
        new_type = mi.type_info(new_type)

    root_old = _top_name(old_type)
    root_new = _top_name(new_type)
    report = CompatReport(root_old, root_new)
    state = _State(report)
    state.compare(old_type, new_type, "$", in_union=False)
    return report


def _top_name(t: mi.Type) -> str:
    t = t.type if isinstance(t, mi.Metadata) else t
    if isinstance(t, (mi.StructType, mi.EnumType, mi.CustomType,
                      mi.DataclassType, mi.TypedDictType, mi.NamedTupleType)):
        return _qname(t.cls)
    return type(t).__name__


class _State:
    def __init__(self, report: CompatReport):
        self.report = report

    def add(self, code: str, path: str, message: str,
            cells: dict[tuple[str, str], str],
            old: mi.Type | None = None, new: mi.Type | None = None):
        self.report.issues.append(
            Issue(
                code=code,
                path=path,
                message=message,
                cells=dict(cells),
                old=_short(old),
                new=_short(new),
            )
        )

    # -- 入口 -- #
    def compare(self, o: mi.Type, n: mi.Type, path: str, *, in_union: bool):
        o = o.type if isinstance(o, mi.Metadata) else o
        n = n.type if isinstance(n, mi.Metadata) else n

        # 钩子 / 自定义类型：无法判断
        if isinstance(o, mi.CustomType) or isinstance(n, mi.CustomType):
            self.add(
                "hook.required", path,
                f"涉及 msgspec 原生不支持的自定义类型"
                f"（{_short(o)} -> {_short(n)}）；其线格式完全由 enc_hook/dec_hook "
                f"决定，静态分析无法判断交换是否安全。",
                _uniform_cells(_S.UNKNOWN, _S.UNKNOWN), o, n,
            )
            return

        # Any / Raw：线格式不透明
        if isinstance(o, (mi.AnyType, mi.RawType)) or isinstance(
            n, (mi.AnyType, mi.RawType)
        ):
            self._compare_any(o, n, path)
            return

        # Ext：JSON 根本不支持；MessagePack 取决于 type code 约定
        if isinstance(o, mi.ExtType) or isinstance(n, mi.ExtType):
            self.add(
                "ext.json.unsupported", path,
                "字段线格式包含 msgspec.msgpack.Ext；Ext 无法编码到 JSON，"
                "两个方向的 JSON 交换都不可能成功。",
                {
                    (OLD_TO_NEW, JSON): _S.UNSAFE,
                    (NEW_TO_OLD, JSON): _S.UNSAFE,
                }, o, n,
            )
            self.add(
                "ext.msgpack.unverifiable", path,
                "MessagePack 下 Ext 的 type code 与载荷结构是值级约定，"
                "类型注解（ExtType）看不到 type code；需要人工核对扩展实现，"
                "静态分析无法判断。",
                {
                    (OLD_TO_NEW, MSGPACK): _S.UNKNOWN,
                    (NEW_TO_OLD, MSGPACK): _S.UNKNOWN,
                }, o, n,
            )
            return

        # 一侧是联合、另一侧是普通类型：把普通类型提升为单成员联合，
        # 复用成员增删规则（如 int -> int|str）。
        if isinstance(o, mi.UnionType) != isinstance(n, mi.UnionType):
            if isinstance(o, mi.UnionType):
                self._compare_union(o, mi.UnionType((n,)), path)
            else:
                self._compare_union(mi.UnionType((o,)), n, path)
            return

        # 同类，递归到专属比较
        same = type(o) is type(n)
        if same and isinstance(o, mi.StructType):
            self._compare_struct(o, n, path, in_union=in_union)
            return
        if same and isinstance(o, (mi.DataclassType, mi.TypedDictType)):
            self._compare_object_like(o, n, path, forbid_unknown=False)
            return
        if same and isinstance(o, mi.NamedTupleType):
            self._compare_positional(o, n, path, bounded=True)
            return
        if same and isinstance(
            o, (mi.ListType, mi.SetType, mi.FrozenSetType, mi.VarTupleType)
        ):
            self._compare_collection(o, n, path)
            return
        if same and isinstance(o, mi.TupleType):
            self._compare_fixed_tuple(o, n, path)
            return
        if same and isinstance(o, mi.DictType):
            self._compare_dict(o, n, path)
            return
        if same and isinstance(o, mi.UnionType):
            self._compare_union(o, n, path)
            return
        if same and isinstance(o, mi.EnumType):
            self._compare_enum(o, n, path)
            return
        if same and isinstance(o, mi.LiteralType):
            self._compare_literal(o, n, path)
            return
        if same:
            self._compare_primitive(o, n, path)
            return

        # 不同种类：按线格式兼容性矩阵判断
        self._cross_kind(o, n, path)

    # -- Any / Raw -- #
    def _compare_any(self, o: mi.Type, n: mi.Type, path: str):
        o_opaque = isinstance(o, (mi.AnyType, mi.RawType))
        n_opaque = isinstance(n, (mi.AnyType, mi.RawType))
        if o_opaque and n_opaque:
            return  # 双方都不透明，线字节原样传递，不产生拒绝
        if o_opaque:
            self.add(
                "type.narrowed_from_any", path,
                f"旧定义为 {_short(o)}，线上可以是任意值；新定义收窄为 "
                f"{_short(n)}，旧数据中不符合新类型的值会被拒绝。",
                _uniform_cells(_S.UNSAFE, _S.SAFE), o, n,
            )
        else:
            self.add(
                "type.narrowed_from_any", path,
                f"新定义为 {_short(n)}，线上可以是任意值；旧定义为 "
                f"{_short(o)}，新数据中不符合旧类型的值会被拒绝。",
                _uniform_cells(_S.SAFE, _S.UNSAFE), o, n,
            )

    # -- 结构体 -- #
    def _compare_struct(self, o: mi.StructType, n: mi.StructType, path: str,
                        *, in_union: bool):
        # array_like 翻转：object <-> array，线形状彻底不同
        if o.array_like != n.array_like:
            self.add(
                "struct.array_like.changed", path,
                f"结构体线格式发生切换：旧定义 array_like={o.array_like}，"
                f"新定义 array_like={n.array_like}；object 与 array 无法互相解码。",
                _uniform_cells(_S.UNSAFE, _S.UNSAFE), o, n,
            )
            return

        # 标签配置（仅结构体自身带 tag 时有意义）
        self._compare_struct_tag(o, n, path, in_union=in_union)

        if o.array_like:
            self._compare_positional(o, n, path, bounded=False)
        else:
            self._compare_object_like(
                o, n, path,
                forbid_unknown=True,  # Struct 支持 forbid_unknown_fields
            )

    def _compare_struct_tag(self, o: mi.StructType, n: mi.StructType,
                            path: str, *, in_union: bool):
        if o.tag is None and n.tag is None:
            return
        if o.tag is None or n.tag is None:
            # 一侧带标签一侧不带：线格式多/少一个判别键（array 时多/少首元素）
            if o.array_like:
                cells = _uniform_cells(_S.UNSAFE, _S.UNSAFE)
                msg = ("结构体在 array 线格式下是否带标签发生变化：标签是数组首元素，"
                       "增删标签会令所有字段位置错位。")
            else:
                # object：多一个未知键（可忽略）/少一个键（具体类型解码不强制 tag），
                # 一般可解码但标签语义丢失；forbid_unknown 时报错，由字段规则覆盖，
                # 这里给 LOSSY。
                cells = _uniform_cells(_S.LOSSY, _S.LOSSY)
                msg = ("结构体一侧带标签、另一侧不带：object 线格式下通常仍可解码，"
                       "但判别标签被静默忽略。")
            self.add("union.tag.changed", path, msg, cells, o, n)
            return

        # tag 值
        if o.tag != n.tag:
            self.add(
                "union.tag.changed", path,
                f"标签值改变：{o.tag!r} -> {n.tag!r}；标签在线上必须与解码器匹配，"
                f"两个方向都会因标签不被接受而报错（具体类型位置下标签存在也会校验）。",
                _uniform_cells(_S.UNSAFE, _S.UNSAFE), o, n,
            )
        # tag_field（仅 object 线格式）
        if not o.array_like:
            otf = o.tag_field or "type"
            ntf = n.tag_field or "type"
            if otf != ntf:
                if in_union:
                    # 联合分发：找不到判别键即报错
                    cells = _uniform_cells(_S.UNSAFE, _S.UNSAFE)
                    msg = (f"标签联合的判别键名改变：{otf!r} -> {ntf!r}；"
                           f"联合分发依赖该键定位成员，两个方向都无法分派。")
                else:
                    # 具体类型位置：旧键被当未知字段忽略、新键缺失被容忍，
                    # 仅当解码器 forbid_unknown_fields 时报错。
                    o2n = _S.UNSAFE if n.forbid_unknown_fields else _S.LOSSY
                    n2o = _S.UNSAFE if o.forbid_unknown_fields else _S.LOSSY
                    cells = _uniform_cells(o2n, n2o)
                    msg = (f"标签判别键名改变：{otf!r} -> {ntf!r}；具体类型位置下"
                           f"旧判别键会被当作未知字段"
                           f"（解码器开启 forbid_unknown_fields 时报错，否则静默丢弃）。")
                self.add("union.tag_field.changed", path, msg, cells, o, n)

    # -- object 线格式字段比较（Struct / dataclass / TypedDict）-- #
    def _compare_object_like(self, o: Any, n: Any, path: str,
                             *, forbid_unknown: bool):
        o_fields = {f.name: f for f in o.fields}
        n_fields = {f.name: f for f in n.fields}
        o_forbid = bool(getattr(o, "forbid_unknown_fields", False))
        n_forbid = bool(getattr(n, "forbid_unknown_fields", False))

        # 共有字段
        for name in sorted(set(o_fields) & set(n_fields)):
            of, nf = o_fields[name], n_fields[name]
            fpath = f"{path}.{name}"
            if of.encode_name != nf.encode_name:
                self._wire_name_change(of, nf, fpath, o_forbid, n_forbid)
            # 必填性
            if not of.required and nf.required:
                self.add(
                    "field.became_required", fpath,
                    f"字段 {name!r} 由可选变为必填：旧编码方（尤其在 omit_defaults "
                    f"时）可能完全省略该键，新解码器会报缺少必填字段。",
                    _uniform_cells(_S.UNSAFE, _S.SAFE),
                    of.type, nf.type,
                )
            # 类型递归
            self.compare(of.type, nf.type, fpath, in_union=False)

        # 新增字段（只在新定义）
        for name in sorted(set(n_fields) - set(o_fields)):
            nf = n_fields[name]
            fpath = f"{path}.{name}"
            self._added_field_object(name, nf, fpath, o_forbid)

        # 删除字段（只在旧定义）
        for name in sorted(set(o_fields) - set(n_fields)):
            of = o_fields[name]
            fpath = f"{path}.{name}"
            self._removed_field_object(name, of, fpath, n_forbid)

    def _added_field_object(self, name: str, nf: mi.Field, path: str,
                            old_forbid: bool):
        wire = nf.encode_name
        if nf.required:
            self.add(
                "field.added.required", path,
                f"新增必填字段 {name!r}（线名 {wire!r}）：旧数据不含该键，"
                f"新解码器报「缺少必填字段」。",
                _uniform_cells(_S.UNSAFE,
                               _S.UNSAFE if old_forbid else _S.LOSSY),
                None, nf.type,
            )
        else:
            n2o = _S.UNSAFE if old_forbid else _S.LOSSY
            self.add(
                "field.added.optional", path,
                f"新增可选字段 {name!r}（线名 {wire!r}）：旧解码器能正常解码，"
                + ("但旧解码器开启 forbid_unknown_fields，会拒绝该未知键。"
                   if old_forbid else
                   "但该键会被旧解码器当作未知字段忽略，值丢失。"),
                _uniform_cells(_S.SAFE, n2o),
                None, nf.type,
            )

    def _removed_field_object(self, name: str, of: mi.Field, path: str,
                              new_forbid: bool):
        wire = of.encode_name
        if of.required:
            self.add(
                "field.removed.required", path,
                f"字段 {name!r}（线名 {wire!r}）在新定义中被删除，但旧解码器仍要求"
                f"该必填字段：新数据不含该键，旧解码器报错。",
                _uniform_cells(_S.UNSAFE if new_forbid else _S.LOSSY,
                               _S.UNSAFE),
                of.type, None,
            )
        else:
            o2n = _S.UNSAFE if new_forbid else _S.LOSSY
            self.add(
                "field.removed.optional", path,
                f"字段 {name!r}（线名 {wire!r}）在新定义中被删除：旧数据仍携带该键，"
                + ("会被开启 forbid_unknown_fields 的新解码器拒绝（旧→新）。"
                   if new_forbid else
                   "会被新解码器当作未知字段忽略（旧→新，值丢失）。")
                + "反方向新编码方已不再发送该字段，旧解码器回退默认值，"
                  "不发生值丢失（新→旧安全）。",
                _uniform_cells(o2n, _S.SAFE),
                of.type, None,
            )

    def _wire_name_change(self, of: mi.Field, nf: mi.Field, path: str,
                          o_forbid: bool, n_forbid: bool):
        # 键名变化等价于「旧键被忽略 + 新键缺失」。
        o2n_parts, n2o_parts = [], []
        # O2N：新解码器找不到新键
        o2n = _S.SAFE
        if nf.required:
            o2n = _S.UNSAFE
            o2n_parts.append("新解码器找不到新键名且该字段必填，报缺少字段")
        else:
            o2n_parts.append("新解码器找不到新键名，回退默认值")
        # 旧键在新解码器侧是未知键
        if n_forbid:
            o2n = _S.UNSAFE
            o2n_parts.append("且新解码器开启 forbid_unknown_fields，旧键本身即被拒绝")
        elif o2n != _S.UNSAFE:
            o2n = _S.LOSSY
        # N2O：对称
        n2o = _S.SAFE
        if of.required:
            n2o = _S.UNSAFE
            n2o_parts.append("旧解码器找不到旧键名且该字段必填，报缺少字段")
        else:
            n2o_parts.append("旧解码器找不到旧键名，回退默认值")
        if o_forbid:
            n2o = _S.UNSAFE
            n2o_parts.append("且旧解码器开启 forbid_unknown_fields，新键本身即被拒绝")
        elif n2o != _S.UNSAFE:
            n2o = _S.LOSSY
        self.add(
            "field.wire_name.changed", path,
            f"字段 {of.name!r} 的线名（别名）由 {of.encode_name!r} 改为 "
            f"{nf.encode_name!r}。旧→新：{ '；'.join(o2n_parts) }。"
            f"新→旧：{ '；'.join(n2o_parts) }。",
            _uniform_cells(o2n, n2o), of.type, nf.type,
        )

    # -- array 线格式位置比较（array_like Struct / NamedTuple）-- #
    def _compare_positional(self, o: Any, n: Any, path: str, *, bounded: bool):
        ofields = list(o.fields)
        nfields = list(n.fields)
        o_req = sum(1 for f in o.fields if f.required)
        n_req = sum(1 for f in n.fields if f.required)
        o_names = {f.name: i for i, f in enumerate(ofields)}
        n_names = {f.name: i for i, f in enumerate(nfields)}

        common = sorted(set(o_names) & set(n_names))
        # 错位 / 重排
        for name in common:
            oi, ni = o_names[name], n_names[name]
            if oi != ni:
                self.add(
                    "field.positional.reordered", f"{path}.{name}",
                    f"位置式结构中字段 {name!r} 的位置由 {oi} 移到 {ni}；"
                    f"按位置解码会令值绑定到错误字段（类型相同也会语义错位）。",
                    _uniform_cells(_S.UNSAFE, _S.UNSAFE),
                    ofields[oi].type, nfields[ni].type,
                )
            else:
                self.compare(ofields[oi].type, nfields[ni].type,
                             f"{path}[{ni}]", in_union=False)

        inserted = sorted(set(n_names) - set(o_names),
                          key=lambda x: n_names[x])
        removed = sorted(set(o_names) - set(n_names),
                         key=lambda x: o_names[x])

        mid_insert = [name for name in inserted if n_names[name] < len(ofields)]
        mid_remove = [name for name in removed if o_names[name] < len(nfields)]

        for name in mid_insert:
            self.add(
                "field.positional.inserted", f"{path}.{name}",
                f"新定义在位置 {n_names[name]} 插入字段 {name!r}：其后所有字段"
                f"位置平移，旧数据按新位置解码全部错位。",
                _uniform_cells(_S.UNSAFE, _S.UNSAFE),
            )
        for name in mid_remove:
            self.add(
                "field.positional.removed", f"{path}.{name}",
                f"旧定义位置 {o_names[name]} 的字段 {name!r} 被删除：其后字段"
                f"位置平移，新数据按旧位置解码全部错位。",
                _uniform_cells(_S.UNSAFE, _S.UNSAFE),
            )

        # 尾部追加（array_like Struct 允许；NamedTuple 长度有上界）
        appended = [name for name in inserted
                    if n_names[name] >= len(ofields)
                    and name not in mid_insert]
        for name in appended:
            nf = nfields[n_names[name]]
            fpath = f"{path}.{name}"
            if nf.required:
                self.add(
                    "field.added.required", fpath,
                    f"位置式结构尾部新增必填字段 {name!r}（位置 {n_names[name]}）："
                    f"旧数据元素个数不足，新解码器报错。",
                    _uniform_cells(_S.UNSAFE,
                                   _S.UNSAFE if bounded else _S.LOSSY),
                    None, nf.type,
                )
            else:
                n2o = _S.UNSAFE if bounded else _S.LOSSY
                extra_note = ("NamedTuple 要求长度不超过声明字段数，多出的尾部元素"
                              "会被拒绝。" if bounded else
                              "旧 array 解码器会忽略多出的尾部元素，值丢失。")
                self.add(
                    "field.positional.trailing_dropped" if not bounded
                    else "field.positional.too_long", fpath,
                    f"位置式结构尾部新增可选字段 {name!r}（位置 {n_names[name]}）："
                    f"旧→新可补默认值；新→旧方向{extra_note}",
                    _uniform_cells(_S.SAFE, n2o),
                    None, nf.type,
                )

        # 尾部删除：新数据比旧定义短
        trailing_removed = [name for name in removed
                            if o_names[name] >= len(nfields)
                            and name not in mid_remove]
        for name in trailing_removed:
            of = ofields[o_names[name]]
            fpath = f"{path}.{name}"
            if of.required:
                self.add(
                    "field.removed.required", fpath,
                    f"旧定义尾部必填字段 {name!r}（位置 {o_names[name]}）被删除："
                    f"新数据长度不足，旧解码器缺少必填位置。",
                    _uniform_cells(
                        _S.UNSAFE if bounded else _S.LOSSY, _S.UNSAFE),
                    of.type, None,
                )
            else:
                self.add(
                    "field.removed.optional", fpath,
                    f"旧定义尾部可选字段 {name!r}（位置 {o_names[name]}）被删除："
                    f"旧解码器对缺失位置回退默认值。",
                    _uniform_cells(
                        _S.UNSAFE if bounded else _S.LOSSY, _S.LOSSY),
                    of.type, None,
                )

        # 长度边界（覆盖未按名称配对的整块增删）
        lo, ln = len(ofields), len(nfields)
        # O2N：旧数据长度 lo，新解码器要求 >= n_req（bounded 时还要求 <= 新字段数）
        if lo < n_req and not (mid_insert or mid_remove):
            self.add(
                "field.positional.too_short", path,
                f"新定义有 {n_req} 个必填位置，旧数据最多提供 {lo} 个元素。",
                _uniform_cells(_S.UNSAFE, _S.SAFE),
            )
        if bounded and lo > ln and not (mid_insert or mid_remove):
            self.add(
                "field.positional.too_long", path,
                f"NamedTuple 新定义仅接受至多 {ln} 个元素，旧数据有 {lo} 个。",
                _uniform_cells(_S.UNSAFE, _S.SAFE),
            )
        # N2O：新数据长度 ln，旧解码器要求 >= o_req（bounded 时 <= lo）
        if ln < o_req and not (mid_insert or mid_remove):
            self.add(
                "field.positional.too_short", path,
                f"旧定义有 {o_req} 个必填位置，新数据最多提供 {ln} 个元素。",
                _uniform_cells(_S.SAFE, _S.UNSAFE),
            )
        if bounded and ln > lo and not appended:
            self.add(
                "field.positional.too_long", path,
                f"NamedTuple 旧定义仅接受至多 {lo} 个元素，新数据有 {ln} 个。",
                _uniform_cells(_S.SAFE, _S.UNSAFE),
            )

    # -- 集合容器 -- #
    def _compare_collection(self, o: mi.CollectionType, n: mi.CollectionType,
                            path: str):
        # list/set/frozenset/var-tuple 线格式都是 array，元素递归
        self.compare(o.item_type, n.item_type, f"{path}[]", in_union=False)
        _range_constraints(self, path, o, n, "集合长度")

    def _compare_fixed_tuple(self, o: mi.TupleType, n: mi.TupleType,
                             path: str):
        if len(o.item_types) != len(n.item_types):
            self.add(
                "tuple.arity.changed", path,
                f"定长 tuple 长度由 {len(o.item_types)} 变为 "
                f"{len(n.item_types)}：解码器按精确长度校验，两个方向都会报错。",
                _uniform_cells(_S.UNSAFE, _S.UNSAFE), o, n,
            )
        for i, (a, b) in enumerate(zip(o.item_types, n.item_types)):
            self.compare(a, b, f"{path}[{i}]", in_union=False)

    # -- dict -- #
    def _compare_dict(self, o: mi.DictType, n: mi.DictType, path: str):
        self.compare(o.value_type, n.value_type, f"{path}{{}}", in_union=False)
        if type(o.key_type) is not type(n.key_type) or not _same_key_kind(
            o.key_type, n.key_type
        ):
            # JSON 的 object 键总是字符串：int 键 -> str 键无损；
            # str 键 -> int 键要求键可解析为整数，否则报错。
            # MessagePack 严格区分 int/str 等键标记，两个方向都拒绝。
            o_key = _key_family(o.key_type)
            n_key = _key_family(n.key_type)
            o2n_json = _S.SAFE if (o_key == "int" and n_key == "str") \
                else _S.UNSAFE
            n2o_json = _S.SAFE if (n_key == "int" and o_key == "str") \
                else _S.UNSAFE
            self.add(
                "dict.key_type.changed", f"{path}{{}}key",
                f"dict 键类型由 {_short(o.key_type)} 变为 {_short(n.key_type)}："
                f"JSON 对象键统一为字符串，int 键 -> str 键无损、反向要求键可"
                f"解析为整数；MessagePack 严格区分键标记，两个方向都拒绝。",
                _cells(o2n_json, _S.UNSAFE, n2o_json, _S.UNSAFE),
                o.key_type, n.key_type,
            )
        else:
            self.compare(o.key_type, n.key_type, f"{path}{{}}key",
                         in_union=False)
        _range_constraints(self, path, o, n, "映射大小")

    # -- 联合 -- #
    def _compare_union(self, o: mi.UnionType, n: mi.UnionType, path: str):
        o_tagged = [t for t in o.types if isinstance(t, mi.StructType)
                    and t.tag is not None]
        n_tagged = [t for t in n.types if isinstance(t, mi.StructType)
                    and t.tag is not None]
        o_other = [t for t in o.types if not (
            isinstance(t, mi.StructType) and t.tag is not None)]
        n_other = [t for t in n.types if not (
            isinstance(t, mi.StructType) and t.tag is not None)]

        if o_tagged or n_tagged:
            self._compare_tagged_members(
                o_tagged, n_tagged, path,
                array_like=any(t.array_like for t in o_tagged + n_tagged),
            )
        if o_other or n_other:
            self._compare_untagged_members(o_other, n_other, path)

    def _compare_tagged_members(self, o_members, n_members, path: str,
                                *, array_like: bool):
        # tag_field 集合（object 线格式才需要）
        if not array_like:
            otf = {t.tag_field or "type" for t in o_members} or {"type"}
            ntf = {t.tag_field or "type" for t in n_members} or {"type"}
            if otf != ntf:
                self.add(
                    "union.tag_field.changed", path,
                    f"标签联合的判别键名集合改变：{sorted(otf)} -> "
                    f"{sorted(ntf)}；多成员联合按该键分派，键名不匹配时两个方向"
                    f"都因缺少判别键而无法解码。",
                    _uniform_cells(_S.UNSAFE, _S.UNSAFE),
                )

        o_by_cls = {_qname(t.cls): t for t in o_members}
        n_by_cls = {_qname(t.cls): t for t in n_members}

        # 1) 按类名配对（同成员演进），可检出 tag 值变化
        paired: list[tuple[mi.StructType, mi.StructType]] = []
        for qn in sorted(set(o_by_cls) & set(n_by_cls)):
            ot, nt = o_by_cls[qn], n_by_cls[qn]
            mpath = f"{path}[{_member_label(nt)}]"
            if ot.tag != nt.tag:
                self.add(
                    "union.tag.changed", mpath,
                    f"成员 {qn} 的标签值由 {ot.tag!r} 变为 {nt.tag!r}："
                    f"旧数据携带旧标签，新联合不接受（反之亦然），两个方向报错。",
                    _uniform_cells(_S.UNSAFE, _S.UNSAFE), ot, nt,
                )
            if not array_like:
                otf = ot.tag_field or "type"
                ntf = nt.tag_field or "type"
                if otf != ntf:
                    # 已在联合级别记录 tag_field 变化，这里不重复
                    pass
            paired.append((ot, nt))

        o_left = [t for qn, t in o_by_cls.items()
                  if qn not in n_by_cls]
        n_left = [t for qn, t in n_by_cls.items()
                  if qn not in o_by_cls]

        # 2) 剩余成员按 tag 值配对（类改名但标签保留）
        n_left_by_tag = {}
        for t in list(n_left):
            n_left_by_tag.setdefault(("str" if isinstance(t.tag, str)
                                      else "int", t.tag), []).append(t)
        tag_paired = []
        for ot in list(o_left):
            key = ("str" if isinstance(ot.tag, str) else "int", ot.tag)
            if n_left_by_tag.get(key):
                nt = n_left_by_tag[key].pop(0)
                tag_paired.append((ot, nt))
                n_left.remove(nt)
                o_left.remove(ot)
        paired.extend(tag_paired)

        # 3) 删除 / 新增
        for ot in o_left:
            self.add(
                "union.member.removed", f"{path}[{_member_label(ot)}]",
                f"标签联合删除了成员 {_qname(ot.cls)}（标签 {ot.tag!r}）："
                f"旧数据仍可能携带该标签，新联合无法分派，旧→新报错。",
                _uniform_cells(_S.UNSAFE, _S.SAFE), ot, None,
            )
        for nt in n_left:
            self.add(
                "union.member.added", f"{path}[{_member_label(nt)}]",
                f"标签联合新增了成员 {_qname(nt.cls)}（标签 {nt.tag!r}）："
                f"新数据可能携带旧联合不认识的标签，新→旧报错。",
                _uniform_cells(_S.SAFE, _S.UNSAFE), None, nt,
            )

        # 4) 配对成员：递归比较字段（标签视为已处理）
        for ot, nt in paired:
            mpath = f"{path}[{_member_label(nt)}]"
            if ot.array_like or nt.array_like:
                if ot.array_like != nt.array_like:
                    self.add(
                        "struct.array_like.changed", mpath,
                        f"联合成员 {_qname(nt.cls)} 的 array_like 发生切换。",
                        _uniform_cells(_S.UNSAFE, _S.UNSAFE), ot, nt,
                    )
                    continue
                self._compare_positional(ot, nt, mpath, bounded=False)
            else:
                self._compare_object_like(
                    ot, nt, mpath, forbid_unknown=True)

    def _compare_untagged_members(self, o_members, n_members, path: str):
        o_left = list(o_members)
        n_left = list(n_members)
        pairs = []
        # 优先按类身份配对
        for ot in list(o_left):
            for nt in list(n_left):
                if _member_identity(ot) == _member_identity(nt):
                    pairs.append((ot, nt))
                    n_left.remove(nt)
                    o_left.remove(ot)
                    break
        # 再按形状键配对
        for ot in list(o_left):
            for nt in list(n_left):
                if _shape_key(ot) == _shape_key(nt):
                    pairs.append((ot, nt))
                    n_left.remove(nt)
                    o_left.remove(ot)
                    break
        for ot, nt in pairs:
            label = _member_label(nt)
            self.compare(ot, nt, f"{path}[{label}]", in_union=False)
        for ot in o_left:
            self.add(
                "union.member.removed", f"{path}[{_member_label(ot)}]",
                f"联合删除了成员 {_short(ot)}：旧数据若为该形状，新联合无法匹配，"
                f"旧→新报错。",
                _uniform_cells(_S.UNSAFE, _S.SAFE), ot, None,
            )
        for nt in n_left:
            self.add(
                "union.member.added", f"{path}[{_member_label(nt)}]",
                f"联合新增了成员 {_short(nt)}：新数据若为该形状，旧联合无法匹配，"
                f"新→旧报错。",
                _uniform_cells(_S.SAFE, _S.UNSAFE), None, nt,
            )

    # -- 枚举 -- #
    def _compare_enum(self, o: mi.EnumType, n: mi.EnumType, path: str):
        o_canon, o_all = _enum_values(o.cls)
        n_canon, n_all = _enum_values(n.cls)
        o_vt = {type(v).__name__ for v in o_all}
        n_vt = {type(v).__name__ for v in n_all}
        if o_vt != n_vt:
            self.add(
                "enum.value_type.changed", path,
                f"枚举值的线类型改变：{sorted(o_vt)} -> {sorted(n_vt)}"
                f"（如 IntEnum 发数字、StrEnum 发字符串），两个方向都无法解码。",
                _uniform_cells(_S.UNSAFE, _S.UNSAFE), o, n,
            )
            return
        # 旧会发出、但新解码器不接受的值
        gone = sorted(v for v in o_canon if v not in n_all)
        if gone:
            self.add(
                "enum.value.removed", path,
                f"枚举删除了仍会被旧版本发出的取值 {gone!r}：旧→新解码会因"
                f"非法枚举值报错。",
                _uniform_cells(_S.UNSAFE, _S.SAFE), o, n,
            )
        added = sorted(v for v in n_canon if v not in o_all)
        if added:
            self.add(
                "enum.value.added", path,
                f"枚举新增了旧解码器不认识的取值 {added!r}：新→旧解码会因"
                f"非法枚举值报错。",
                _uniform_cells(_S.SAFE, _S.UNSAFE), o, n,
            )

    # -- Literal -- #
    def _compare_literal(self, o: mi.LiteralType, n: mi.LiteralType,
                         path: str):
        o_vals = set(o.values)
        n_vals = set(n.values)
        if {type(v).__name__ for v in o_vals} != {
            type(v).__name__ for v in n_vals
        }:
            self.add(
                "type.kind.changed", path,
                f"Literal 取值的线类型改变：{o.values!r} -> {n.values!r}。",
                _uniform_cells(_S.UNSAFE, _S.UNSAFE), o, n,
            )
            return
        gone = sorted(v for v in o_vals - n_vals if v is not None)
        added = sorted(v for v in n_vals - o_vals if v is not None)
        # None 增删交给联合成员规则更直观；这里仍保留判定
        if None in (o_vals - n_vals):
            gone = gone + [None]
        if None in (n_vals - o_vals):
            added = added + [None]
        if gone:
            self.add(
                "literal.value.removed", path,
                f"Literal 删除了旧版本仍会发出的取值 {gone!r}：旧→新被拒绝。",
                _uniform_cells(_S.UNSAFE, _S.SAFE), o, n,
            )
        if added:
            self.add(
                "literal.value.added", path,
                f"Literal 新增了旧解码器不接受的取值 {added!r}：新→旧被拒绝。",
                _uniform_cells(_S.SAFE, _S.UNSAFE), o, n,
            )

    # -- 原始类型 + 约束 -- #
    def _compare_primitive(self, o: mi.Type, n: mi.Type, path: str):
        # 数值上下界
        if isinstance(o, (mi.IntType, mi.FloatType)):
            _numeric_constraints(self, path, o, n)
            return
        # 长度约束（str/bytes/bytearray/memoryview 与容器已在别处处理）
        if isinstance(o, (mi.StrType, mi.BytesType, mi.ByteArrayType,
                          mi.MemoryViewType)):
            _range_constraints(self, path, o, n, "长度")
            if isinstance(o, mi.StrType):
                op = getattr(o, "pattern", None)
                np = getattr(n, "pattern", None)
                if op != np:
                    self.add(
                        "constraint.changed", path,
                        f"正则约束 pattern 由 {op!r} 变为 {np!r}：正则之间"
                        f"一般无法判定包含关系，两个方向都存在被拒绝的合法值。",
                        _uniform_cells(_S.UNSAFE, _S.UNSAFE), o, n,
                    )
            return
        if isinstance(o, (mi.DateTimeType, mi.TimeType)):
            otz, ntz = o.tz, n.tz
            if otz != ntz:
                # None(都接受) -> True/False：收紧；True<->False：互不接受
                if ntz is None:
                    self.add(
                        "constraint.loosened", path,
                        f"时区要求由 tz={otz} 放宽为 tz=None：新数据可能携带"
                        f"旧要求之外的取值，新→旧被拒绝。",
                        _uniform_cells(_S.SAFE, _S.UNSAFE), o, n,
                    )
                elif otz is None:
                    self.add(
                        "constraint.tightened", path,
                        f"时区要求由 tz=None 收紧为 tz={ntz}：旧数据中的"
                        f"另一类（naive/aware）值会被新解码器拒绝。",
                        _uniform_cells(_S.UNSAFE, _S.SAFE), o, n,
                    )
                else:
                    self.add(
                        "constraint.changed", path,
                        f"时区要求 tz={otz} -> tz={ntz}：naive 与 aware"
                        f"互不接受，两个方向都报错。",
                        _uniform_cells(_S.UNSAFE, _S.UNSAFE), o, n,
                    )
            return
        # 其余原始类型（bool/None/date/timedelta/uuid/decimal 等）无约束，
        # 同种类即线格式一致。

    # -- 异种类：线格式矩阵 -- #
    def _cross_kind(self, o: mi.Type, n: mi.Type, path: str):
        # 先处理「富类型 <-> 原始类型 / 近似线格式」的非对称兼容
        if _richness(o, n, path, self) is not None:
            return

        distinct = [
            p for p in PROTOCOLS
            if _wire_groups(o, p).isdisjoint(_wire_groups(n, p))
        ]
        note = ""
        if distinct:
            note = (f"；其中 {'、'.join(distinct)} 下线标记完全不同"
                    f"（{_group_desc(o)} vs {_group_desc(n)}）")
        self.add(
            "type.kind.changed", path,
            f"类型种类改变：{_short(o)} -> {_short(n)}{note}；"
            f"不同种类间无法保证取值域互相包含，两个方向都判为不安全。",
            _uniform_cells(_S.UNSAFE, _S.UNSAFE), o, n,
        )


# --------------------------------------------------------------------------- #
# 约束比较辅助
# --------------------------------------------------------------------------- #

def _numeric_constraints(st: _State, path, o, n):
    o_low = _lower_bound(o)
    n_low = _lower_bound(n)
    if o_low != n_low:
        # 收紧：新下界拒绝旧下界允许的值；放宽：旧下界拒绝新下界允许的值
        tighter = _low_tighter(n_low, o_low)
        looser = _low_tighter(o_low, n_low)
        if tighter and not looser:
            st.add("constraint.tightened", path,
                   f"数值下界约束收紧：{_bounds_repr(o)} -> {_bounds_repr(n)}；"
                   f"旧数据可能低于新下界（含边界值开闭变化），旧→新被拒绝。",
                   _uniform_cells(_S.UNSAFE, _S.SAFE), o, n)
        elif looser and not tighter:
            st.add("constraint.loosened", path,
                   f"数值下界约束放宽：{_bounds_repr(o)} -> {_bounds_repr(n)}；"
                   f"新数据可能低于旧下界，新→旧被拒绝。",
                   _uniform_cells(_S.SAFE, _S.UNSAFE), o, n)
        elif tighter and looser:
            st.add("constraint.changed", path,
                   f"数值下界约束改变且互不包含：{_bounds_repr(o)} -> "
                   f"{_bounds_repr(n)}，两个方向都存在被拒绝的合法值。",
                   _uniform_cells(_S.UNSAFE, _S.UNSAFE), o, n)
    o_up = _upper_bound(o)
    n_up = _upper_bound(n)
    if o_up != n_up:
        tighter = _up_tighter(n_up, o_up)
        looser = _up_tighter(o_up, n_up)
        if tighter and not looser:
            st.add("constraint.tightened", path,
                   f"数值上界约束收紧：{_bounds_repr(o)} -> {_bounds_repr(n)}；"
                   f"旧数据可能高于新上界（含边界值开闭变化），旧→新被拒绝。",
                   _uniform_cells(_S.UNSAFE, _S.SAFE), o, n)
        elif looser and not tighter:
            st.add("constraint.loosened", path,
                   f"数值上界约束放宽：{_bounds_repr(o)} -> {_bounds_repr(n)}；"
                   f"新数据可能高于旧上界，新→旧被拒绝。",
                   _uniform_cells(_S.SAFE, _S.UNSAFE), o, n)
        else:
            st.add("constraint.changed", path,
                   f"数值上界约束改变且互不包含：{_bounds_repr(o)} -> "
                   f"{_bounds_repr(n)}，两个方向都存在被拒绝的合法值。",
                   _uniform_cells(_S.UNSAFE, _S.UNSAFE), o, n)
    if o.multiple_of != n.multiple_of:
        st.add("constraint.changed", path,
               f"倍数约束 multiple_of 由 {o.multiple_of!r} 变为 "
               f"{n.multiple_of!r}：无法一般地判定倍数包含关系，两个方向都可能拒绝。",
               _uniform_cells(_S.UNSAFE, _S.UNSAFE), o, n)


def _lower_bound(t):
    """下界 (value, strict)：strict=True 表示 gt（开区间）。"""
    if t.ge is not None:
        return (t.ge, False)
    if t.gt is not None:
        return (t.gt, True)
    return None


def _upper_bound(t):
    """上界 (value, strict)：strict=True 表示 lt（开区间）。"""
    if t.le is not None:
        return (t.le, False)
    if t.lt is not None:
        return (t.lt, True)
    return None


def _low_tighter(new_b, old_b) -> bool:
    """新下界是否拒绝某些旧下界允许的值。"""
    if new_b is None:
        return False
    if old_b is None:
        return True
    if new_b[0] > old_b[0]:
        return True
    if new_b[0] == old_b[0] and new_b[1] and not old_b[1]:
        return True  # ge -> gt：边界值被排除
    return False


def _up_tighter(new_b, old_b) -> bool:
    """新上界是否拒绝某些旧上界允许的值。"""
    if new_b is None:
        return False
    if old_b is None:
        return True
    if new_b[0] < old_b[0]:
        return True
    if new_b[0] == old_b[0] and new_b[1] and not old_b[1]:
        return True  # le -> lt：边界值被排除
    return False


def _bounds_repr(t):
    return f"gt={t.gt!r}, ge={t.ge!r}, lt={t.lt!r}, le={t.le!r}"


def _range_constraints(st: _State, path, o, n, what: str):
    omin, omax = o.min_length, o.max_length
    nmin, nmax = n.min_length, n.max_length
    if omin != nmin:
        if nmin is None or (omin is not None and nmin < omin):
            st.add("constraint.loosened", path,
                   f"{what}下界 min_length 放宽：{omin!r} -> {nmin!r}；"
                   f"新数据可能短于旧下界，新→旧被拒绝。",
                   _uniform_cells(_S.SAFE, _S.UNSAFE), o, n)
        else:
            st.add("constraint.tightened", path,
                   f"{what}下界 min_length 收紧：{omin!r} -> {nmin!r}；"
                   f"旧数据可能短于新下界，旧→新被拒绝。",
                   _uniform_cells(_S.UNSAFE, _S.SAFE), o, n)
    if omax != nmax:
        if nmax is None or (omax is not None and nmax > omax):
            st.add("constraint.loosened", path,
                   f"{what}上界 max_length 放宽：{omax!r} -> {nmax!r}；"
                   f"新数据可能长于旧上界，新→旧被拒绝。",
                   _uniform_cells(_S.SAFE, _S.UNSAFE), o, n)
        else:
            st.add("constraint.tightened", path,
                   f"{what}上界 max_length 收紧：{omax!r} -> {nmax!r}；"
                   f"旧数据可能长于新上界，旧→新被拒绝。",
                   _uniform_cells(_S.UNSAFE, _S.SAFE), o, n)


# --------------------------------------------------------------------------- #
# 线格式分组与富类型规则
# --------------------------------------------------------------------------- #

def _enum_values(cls):
    """返回 (规范成员值集合（编码端可能发出）, 全部可接受值集合)。"""
    canonical = set()
    all_values = set()
    for member in cls:
        canonical.add(member.value)
        all_values.add(member.value)
    # 别名（同值多名）的值也可被解码接受
    try:
        all_values |= set(cls._value2member_map_.keys())
    except AttributeError:
        pass
    return canonical, all_values


def _member_identity(t: mi.Type) -> tuple[str, str] | None:
    if isinstance(t, (mi.StructType, mi.EnumType, mi.CustomType,
                      mi.DataclassType, mi.TypedDictType, mi.NamedTupleType)):
        return (type(t).__name__, _qname(t.cls))
    return None


def _shape_key(t: mi.Type) -> str:
    if isinstance(t, mi.CollectionType):
        return f"{type(t).__name__}[{_shape_key(t.item_type)}]"
    if isinstance(t, mi.TupleType):
        return "Tuple[" + ",".join(_shape_key(x) for x in t.item_types) + "]"
    if isinstance(t, mi.DictType):
        return f"Dict[{_shape_key(t.key_type)},{_shape_key(t.value_type)}]"
    if isinstance(t, mi.LiteralType):
        return f"Literal{sorted(type(v).__name__ for v in t.values)}"
    if isinstance(t, (mi.EnumType,)):
        return f"Enum({_qname(t.cls)})"
    return type(t).__name__


def _member_label(t: mi.Type) -> str:
    if isinstance(t, mi.StructType):
        if t.tag is not None:
            return f"tag={t.tag!r}"
        return _qname(t.cls)
    return _short(t)


def _same_key_kind(a: mi.Type, b: mi.Type) -> bool:
    return _wire_groups(a, MSGPACK) == _wire_groups(b, MSGPACK)


def _key_family(t: mi.Type) -> str:
    t = t.type if isinstance(t, mi.Metadata) else t
    if isinstance(t, mi.IntType):
        return "int"
    if isinstance(t, mi.StrType):
        return "str"
    if isinstance(t, mi.BoolType):
        return "bool"
    if isinstance(t, mi.FloatType):
        return "float"
    if isinstance(t, mi.EnumType):
        vts = {type(v).__name__ for v in t.cls._value2member_map_.keys()}
        return "int" if vts == {"int"} else "str"
    return "other"


def _group_desc(t: mi.Type) -> str:
    return "/".join(sorted(set().union(
        *[_wire_groups(t, p) for p in PROTOCOLS]
    )))


# 粗线标记：bool/int/float/str/bin/null/array/map/ext/opaque
def _wire_groups(t: mi.Type, proto: str) -> frozenset[str]:
    t = t.type if isinstance(t, mi.Metadata) else t
    g = _GROUPS.get(type(t))
    if g is not None:
        return g
    if isinstance(t, mi.EnumType):
        vts = {type(v).__name__ for v in t.cls._value2member_map_.keys()}
        out = set()
        if "str" in vts:
            out.add("str")
        if "int" in vts:
            out.add("int")
        return frozenset(out) or frozenset({"str"})
    if isinstance(t, mi.LiteralType):
        out = set()
        for v in t.values:
            if isinstance(v, bool):
                out.add("bool")
            elif isinstance(v, int):
                out.add("int")
            elif isinstance(v, str):
                out.add("str")
            elif v is None:
                out.add("null")
        return frozenset(out)
    return frozenset({"opaque"})


_GROUPS = {
    mi.BoolType: frozenset({"bool"}),
    mi.IntType: frozenset({"int"}),
    mi.FloatType: frozenset({"float"}),
    mi.NoneType: frozenset({"null"}),
    mi.StrType: frozenset({"str"}),
    mi.BytesType: frozenset({"bin"}),
    mi.ByteArrayType: frozenset({"bin"}),
    mi.MemoryViewType: frozenset({"bin"}),
    mi.DateType: frozenset({"str"}),
    mi.TimeType: frozenset({"str"}),
    mi.TimeDeltaType: frozenset({"str"}),
    mi.UUIDType: frozenset({"str"}),
    mi.DecimalType: frozenset({"str"}),
    mi.ListType: frozenset({"array"}),
    mi.SetType: frozenset({"array"}),
    mi.FrozenSetType: frozenset({"array"}),
    mi.VarTupleType: frozenset({"array"}),
    mi.TupleType: frozenset({"array"}),
    mi.DictType: frozenset({"map"}),
    mi.NamedTupleType: frozenset({"array"}),
    mi.DataclassType: frozenset({"map"}),
    mi.TypedDictType: frozenset({"map"}),
}


def _groups_datetime(proto: str):
    # JSON：始终字符串。MessagePack：naive 发字符串、aware 发 timestamp ext(-1)，
    # 未限定 tz 时两种标记都可能出现。
    if proto == JSON:
        return frozenset({"str"})
    return frozenset({"str", "ext"})


# 修正 DateTimeType 的协议相关分组（msspgec 下可能为 ext）
_orig_wire_groups = _wire_groups


def _wire_groups(t: mi.Type, proto: str) -> frozenset[str]:  # noqa: F811
    t = t.type if isinstance(t, mi.Metadata) else t
    if isinstance(t, mi.DateTimeType):
        if proto == JSON:
            return frozenset({"str"})
        if t.tz is True:
            return frozenset({"ext"})
        if t.tz is False:
            return frozenset({"str"})
        return frozenset({"str", "ext"})
    if isinstance(t, mi.StructType):
        return frozenset({"array"} if t.array_like else {"map"})
    return _orig_wire_groups(t, proto)


# 富类型（枚举/字面量/时间/uuid/decimal/bytes-json）相对原始标量的非对称规则
_RICH_STR = (mi.DateType, mi.TimeType, mi.DateTimeType, mi.TimeDeltaType,
             mi.UUIDType, mi.DecimalType)


def _richness(o: mi.Type, n: mi.Type, path: str, st: _State):
    """处理「同大类、但一侧是取值受限的富类型」的跨种类变化。

    返回 True 表示已处理；None 表示不适用。
    """
    # int/float 特例：int -> float 两个协议都安全；float -> int 不安全
    if isinstance(o, mi.IntType) and isinstance(n, mi.FloatType):
        st.add("type.kind.changed", path,
               "int -> float：整数总能按浮点数解码，旧→新安全；（反向"
               "float -> int 会被拒绝）。",
               _uniform_cells(_S.SAFE, _S.UNSAFE), o, n)
        return True
    if isinstance(o, mi.FloatType) and isinstance(n, mi.IntType):
        st.add("type.kind.changed", path,
               "float -> int：浮点标记（即便值为 1.0）不会被 int 字段接受，"
               "两个方向都不安全。",
               _uniform_cells(_S.UNSAFE, _S.SAFE), o, n)
        return True

    # 枚举/字面量 <-> 标量
    base_o = _scalar_base(o)
    base_n = _scalar_base(n)
    if isinstance(o, (mi.EnumType, mi.LiteralType)) and base_n is not None:
        st.add("type.kind.changed", path,
               f"{_short(o)} -> {_short(n)}：取值受限的枚举/字面量放宽为原始类型，"
               f"其线上取值都是合法 {base_n}，旧→新安全；反向任意 {base_n} "
               f"不一定是合法枚举/字面量，新→旧不安全。",
               _uniform_cells(_S.SAFE, _S.UNSAFE), o, n)
        return True
    if base_o is not None and isinstance(n, (mi.EnumType, mi.LiteralType)):
        st.add("type.kind.changed", path,
               f"{_short(o)} -> {_short(n)}：原始类型收窄为枚举/字面量，"
               f"旧数据的任意 {base_o} 取值可能不合法，旧→新不安全。",
               _uniform_cells(_S.UNSAFE, _S.SAFE), o, n)
        return True

    # JSON 下 bytes(str 标记, base64) <-> str
    if isinstance(o, mi.BytesType) and isinstance(n, mi.StrType):
        st.add("type.kind.changed", path,
               "bytes -> str：JSON 中 bytes 发 base64 文本，按 str 解码文本"
               "无损（旧端不再有二进制语义，但值保留）；MessagePack 中 bin/str "
               "标记不同，双向拒绝。反方向任意 str 不一定是合法 base64。",
               _cells(_S.SAFE, _S.UNSAFE, _S.UNSAFE, _S.UNSAFE), o, n)
        return True
    if isinstance(o, mi.StrType) and isinstance(n, mi.BytesType):
        st.add("type.kind.changed", path,
               "str -> bytes：JSON 中要求字符串是合法 base64，任意旧字符串"
               "会被拒绝（旧→新不安全）；反方向 base64 文本按 str 解码无损。"
               "MessagePack 中 str/bin 标记不同，双向拒绝。",
               _cells(_S.UNSAFE, _S.UNSAFE, _S.SAFE, _S.UNSAFE), o, n)
        return True

    # 时间/uuid/decimal 等（字符串线格式） <-> 裸 str
    if isinstance(o, _RICH_STR) and isinstance(n, mi.StrType):
        # JSON：文本无损；msgpack：date/time/uuid/decimal 同样是 str 标记，
        # 唯有 datetime 可能为 aware（timestamp ext），str 解码器拒绝 ext。
        mp_o2n = _S.UNSAFE if isinstance(
            o, mi.DateTimeType) and o.tz is not False else _S.SAFE
        st.add("type.kind.changed", path,
               f"{_short(o)} -> str：编码端发出的标准格式文本按 str 解码无损"
               f"（旧端仅失去格式语义/校验）；MessagePack 下若旧值可能是 "
               f"aware datetime，则为 timestamp ext 标记、无法按 str 解码。"
               f"反方向任意字符串无法保证符合该类型格式。",
               _cells(_S.SAFE, mp_o2n, _S.UNSAFE, _S.UNSAFE), o, n)
        return True
    if isinstance(o, mi.StrType) and isinstance(n, _RICH_STR):
        mp_n2o = _S.UNSAFE if isinstance(
            n, mi.DateTimeType) and n.tz is not False else _S.SAFE
        st.add("type.kind.changed", path,
               f"str -> {_short(n)}：只有符合该类型格式要求的字符串才能解码，"
               f"旧的任意字符串无法保证合法（旧→新不安全）；反方向标准文本按 "
               f"str 解码无损，MessagePack 下 aware datetime 例外。",
               _cells(_S.UNSAFE, _S.UNSAFE, _S.SAFE, mp_n2o), o, n)
        return True

    # 定长 tuple（精确长度）<-> 普通 array 容器
    if isinstance(o, mi.TupleType) and isinstance(
        n, (mi.ListType, mi.SetType, mi.FrozenSetType, mi.VarTupleType)
    ):
        for i, it in enumerate(o.item_types):
            st.compare(it, n.item_type, f"{path}[{i}]", in_union=False)
        st.add("type.kind.changed", path,
               "定长 tuple -> 变长容器：旧数据长度固定，新容器总能接受；"
               "反向变长数据长度任意、定长 tuple 精确校验长度，新→旧不安全。",
               _uniform_cells(_S.SAFE, _S.UNSAFE), o, n)
        return True
    if isinstance(n, mi.TupleType) and isinstance(
        o, (mi.ListType, mi.SetType, mi.FrozenSetType, mi.VarTupleType)
    ):
        for i, it in enumerate(n.item_types):
            st.compare(o.item_type, it, f"{path}[{i}]", in_union=False)
        st.add("type.kind.changed", path,
               "变长容器 -> 定长 tuple：旧的变长数据长度任意，新 tuple 精确"
               "校验长度，旧→新不安全；反向固定长度数据容器可接受。",
               _uniform_cells(_S.UNSAFE, _S.SAFE), o, n)
        return True

    # 同类 array 容器跨种类（list/set/frozenset/var-tuple）：线格式一致
    array_kinds = (mi.ListType, mi.SetType, mi.FrozenSetType, mi.VarTupleType)
    if isinstance(o, array_kinds) and isinstance(n, array_kinds):
        st.compare(o.item_type, n.item_type, f"{path}[]", in_union=False)
        _range_constraints(st, path, o, n, "集合长度")
        return True

    return None


def _scalar_base(t: mi.Type) -> str | None:
    if isinstance(t, mi.IntType):
        return "int"
    if isinstance(t, mi.FloatType):
        return "float"
    if isinstance(t, mi.StrType):
        return "str"
    if isinstance(t, mi.BoolType):
        return "bool"
    if isinstance(t, (mi.BytesType, mi.ByteArrayType, mi.MemoryViewType)):
        return "bytes"
    return None
