"""Cross-process stable wire-structure fingerprints for msgspec types.

Given a msgspec-compatible type annotation and a set of encoding options,
:func:`wire_fingerprint` computes a deterministic digest of the *wire
structure* produced by the JSON or MessagePack encoders.

The fingerprint is purely structural:

* Equivalent declarations (two separately defined classes with identical
  fields, aliases, tags, constraints and options) fingerprint equal.
* Reordering the members of a union does not change the fingerprint; union
  members are canonicalized by their structural hashes.
* Field aliases, constraints, struct tags, ``omit_defaults`` and array/object
  layout all participate in the fingerprint, so changing any of them changes
  the digest.
* Recursive types, including parameterized recursive generics, terminate:
  class-backed nodes form a finite graph whose bisimulation partition is
  refined to a fixed point, so cycles converge instead of looping.
* Anything the library can only describe through user supplied callables
  (``CustomType`` values handled by ``enc_hook``, callable ``decimal_format``,
  ``msgpack.Ext`` encoded to JSON, ...) is reported explicitly via
  :class:`WireFingerprintUndecidable` rather than guessed.

The digest itself is ``blake2b`` over a canonical JSON rendering of the type
graph, and therefore stable across processes, Python hash seed randomization
and interpreter restarts.
"""

from __future__ import annotations

import base64
import enum
import hashlib
import json as _json
import math
from typing import Any, Final

from . import inspect as mi
from ._core import NODEFAULT, MsgspecError  # type: ignore

__all__ = (
    "wire_fingerprint",
    "wire_canonical",
    "WireFingerprintUndecidable",
)

_VERSION: Final = 1
_DIGEST_NAME: Final = "blake2b256"
_PROTOCOLS: Final = ("json", "msgpack")
_JSON_UUID_FORMATS: Final = ("canonical", "hex")
_MSGPACK_UUID_FORMATS: Final = ("canonical", "hex", "bytes")
_DECIMAL_FORMATS: Final = ("string", "number")


class WireFingerprintUndecidable(MsgspecError):
    """Raised when a wire fingerprint cannot be computed statically.

    This happens for type tree nodes whose wire representation is determined
    by user supplied callables that cannot be introspected (custom types going
    through ``enc_hook``/``dec_hook``, a callable ``decimal_format``,
    ``msgpack.Ext`` encoded as JSON, unrepresentable default values, ...).

    Attributes
    ----------
    reason: str
        Why the fingerprint is undecidable.
    typ: Any
        The type or value that could not be described.
    path: tuple[str, ...]
        The field path from the root type to the offending node.
    """

    def __init__(self, reason: str, typ: Any = None, path: tuple[str, ...] = ()):
        self.reason = reason
        self.typ = typ
        self.path = tuple(path)
        location = ".".join(self.path) if self.path else "<root>"
        name = getattr(typ, "__name__", None) or repr(typ)
        super().__init__(
            f"wire fingerprint undecidable at {location}: {reason} (type: {name})"
        )


class _Ref:
    """A back-reference to a class-backed node by variable index."""

    __slots__ = ("idx",)

    def __init__(self, idx: int):
        self.idx = idx


class _Unset:
    """Sentinel for options that were not explicitly provided."""


_UNSET = _Unset()


def _digest(obj: Any) -> str:
    """Hash a JSON-able canonical structure into a stable hex digest."""
    payload = _json.dumps(
        obj, separators=(",", ":"), ensure_ascii=False, allow_nan=False
    ).encode("utf-8")
    return hashlib.blake2b(payload, digest_size=32).hexdigest()


def _canon_float(value: float) -> str:
    if math.isnan(value):
        return "NaN"
    if math.isinf(value):
        return "Infinity" if value > 0 else "-Infinity"
    return value  # type: ignore[return-value]


def _canon_value(value: Any, path: tuple[str, ...]) -> Any:
    """Canonicalize a static Python value (literal or a field default)."""
    if value is None:
        return ["none"]
    if isinstance(value, bool):
        return ["bool", value]
    if isinstance(value, int):
        return ["int", value]
    if isinstance(value, float):
        return ["float", _canon_float(value)]
    if isinstance(value, str):
        return ["str", value]
    if isinstance(value, (bytes, bytearray)):
        return ["bytes", base64.b64encode(bytes(value)).decode("ascii")]
    if isinstance(value, enum.Enum):
        return ["enum", type(value).__name__, _canon_value(value.value, path)]
    if isinstance(value, (list, tuple)):
        return ["list", [_canon_value(v, path) for v in value]]
    if isinstance(value, (set, frozenset)):
        members = sorted(
            _json.dumps(
                _canon_value(v, path),
                separators=(",", ":"),
                ensure_ascii=False,
                allow_nan=False,
            )
            for v in value
        )
        return ["set", members]
    if isinstance(value, dict):
        items = sorted(
            (
                _json.dumps(
                    _canon_value(k, path),
                    separators=(",", ":"),
                    ensure_ascii=False,
                    allow_nan=False,
                ),
                _canon_value(v, path),
            )
            for k, v in value.items()
        )
        return ["dict", items]
    raise WireFingerprintUndecidable(
        "default/literal value requires runtime evaluation and cannot be "
        "described statically",
        value,
        path,
    )


def _default_marker(field: mi.Field, path: tuple[str, ...]) -> list[Any]:
    if field.default_factory is not NODEFAULT:
        return ["factory"]
    if field.default is NODEFAULT:
        return ["nodefault"]
    return ["value", _canon_value(field.default, path)]


class _GraphBuilder:
    """Builds a finite, cycle-safe template graph from a ``msgspec.inspect`` tree.

    Class-backed nodes (structs, TypedDicts, dataclasses, named tuples) become
    indexed variables; every other node is inlined. Recursive references turn
    into :class:`_Ref` markers, guaranteeing termination on recursive types.
    """

    def __init__(
        self,
        protocol: str,
        decimal_format: str,
        decimal_hook: bool,
        uuid_format: str,
    ):
        self.protocol = protocol
        self.decimal_format = decimal_format
        self.decimal_hook = decimal_hook
        self.uuid_format = uuid_format
        self.var_by_cls: dict[Any, int] = {}
        self.variables: list[tuple[Any, list[Any]]] = []
        self.path: list[str] = []

    def _undecidable(self, reason: str, typ: Any) -> WireFingerprintUndecidable:
        return WireFingerprintUndecidable(reason, typ, tuple(self.path))

    def build(self, t: mi.Type) -> Any:
        # Metadata only carries json-schema/user extras; neither affects the
        # wire structure, so unwrap it. Constraints are already folded into
        # the wrapped leaf type by ``msgspec.inspect``.
        if isinstance(t, mi.Metadata):
            return self.build(t.type)
        if isinstance(t, mi.AnyType):
            return ["any"]
        if isinstance(t, mi.NoneType):
            return ["none"]
        if isinstance(t, mi.BoolType):
            return ["bool"]
        if isinstance(t, mi.IntType):
            return ["int", t.ge, t.gt, t.le, t.lt, t.multiple_of]
        if isinstance(t, mi.FloatType):
            return ["float", t.ge, t.gt, t.le, t.lt, t.multiple_of]
        if isinstance(t, mi.StrType):
            return ["str", t.min_length, t.max_length, t.pattern]
        if isinstance(t, mi.BytesType):
            return ["bytes", t.min_length, t.max_length]
        if isinstance(t, mi.ByteArrayType):
            return ["bytearray", t.min_length, t.max_length]
        if isinstance(t, mi.MemoryViewType):
            return ["memoryview", t.min_length, t.max_length]
        if isinstance(t, mi.DateTimeType):
            return ["datetime", t.tz]
        if isinstance(t, mi.TimeType):
            return ["time", t.tz]
        if isinstance(t, mi.DateType):
            return ["date"]
        if isinstance(t, mi.TimeDeltaType):
            return ["timedelta"]
        if isinstance(t, mi.UUIDType):
            return ["uuid", self.uuid_format]
        if isinstance(t, mi.DecimalType):
            if self.decimal_hook:
                raise self._undecidable(
                    "decimal_format is a user supplied callable; Decimal wire "
                    "output is determined by the hook",
                    t,
                )
            return ["decimal", self.decimal_format]
        if isinstance(t, mi.RawType):
            return ["raw", self.protocol]
        if isinstance(t, mi.ExtType):
            if self.protocol == "json":
                raise self._undecidable(
                    "msgspec.msgpack.Ext cannot be JSON encoded without an enc_hook",
                    t,
                )
            return ["ext"]
        if isinstance(t, mi.LiteralType):
            return [
                "literal",
                sorted(
                    [_canon_value(v, tuple(self.path)) for v in t.values],
                    key=lambda x: _json.dumps(
                        x, separators=(",", ":"), ensure_ascii=False
                    ),
                ),
            ]
        if isinstance(t, mi.EnumType):
            # Only enum values reach the wire; member names do not.
            members = sorted(
                _json.dumps(
                    _canon_value(m.value, tuple(self.path)),
                    separators=(",", ":"),
                    ensure_ascii=False,
                    allow_nan=False,
                )
                for m in t.cls
            )
            return ["enum", members]
        if isinstance(t, mi.CustomType):
            raise self._undecidable(
                "type is not natively supported and is handled by user "
                "supplied enc_hook/dec_hook callables",
                t.cls,
            )
        if isinstance(t, mi.UnionType):
            return ["union", [self.build(m) for m in t.types]]
        if isinstance(t, mi.ListType):
            return ["list", self.build(t.item_type), t.min_length, t.max_length]
        if isinstance(t, mi.SetType):
            return ["set", self.build(t.item_type), t.min_length, t.max_length]
        if isinstance(t, mi.FrozenSetType):
            return [
                "frozenset",
                self.build(t.item_type),
                t.min_length,
                t.max_length,
            ]
        if isinstance(t, mi.VarTupleType):
            return [
                "vartuple",
                self.build(t.item_type),
                t.min_length,
                t.max_length,
            ]
        if isinstance(t, mi.TupleType):
            return ["tuple", [self.build(a) for a in t.item_types]]
        if isinstance(t, mi.DictType):
            return [
                "dict",
                self.build(t.key_type),
                self.build(t.value_type),
                t.min_length,
                t.max_length,
            ]
        if isinstance(t, mi.FrozenDictType):
            return [
                "frozendict",
                self.build(t.key_type),
                self.build(t.value_type),
                t.min_length,
                t.max_length,
            ]
        if isinstance(
            t, (mi.StructType, mi.TypedDictType, mi.DataclassType, mi.NamedTupleType)
        ):
            return self._build_variable(t)
        raise self._undecidable(f"unsupported inspect node {type(t).__name__}", t)

    def _build_variable(
        self, t: mi.StructType | mi.TypedDictType | mi.DataclassType | mi.NamedTupleType
    ) -> _Ref:
        cls = t.cls
        existing = self.var_by_cls.get(cls)
        if existing is not None:
            return _Ref(existing)
        idx = len(self.variables)
        self.var_by_cls[cls] = idx
        # Reserve the slot before filling it so recursive back-references
        # resolve to this same index.
        self.variables.append((cls, []))
        template = self._build_class(t)
        self.variables[idx] = (cls, template)
        return _Ref(idx)

    def _build_class(
        self, t: mi.StructType | mi.TypedDictType | mi.DataclassType | mi.NamedTupleType
    ) -> list[Any]:
        if isinstance(t, mi.StructType):
            # For parameterized generics ``t.cls`` is a generic alias; the
            # concrete origin class holds the struct configuration.
            origin = getattr(t.cls, "__origin__", t.cls)
            config = origin.__struct_config__
            fields = []
            for f in t.fields:
                self.path.append(f.encode_name)
                try:
                    fields.append(
                        [
                            f.encode_name,
                            f.required,
                            _default_marker(f, tuple(self.path)),
                            self.build(f.type),
                        ]
                    )
                finally:
                    self.path.pop()
            return [
                "struct",
                t.array_like,
                t.tag_field,
                None if t.tag is None else _canon_value(t.tag, tuple(self.path)),
                config.omit_defaults,
                t.forbid_unknown_fields,
                fields,
            ]

        kind = {
            mi.TypedDictType: "typeddict",
            mi.DataclassType: "dataclass",
            mi.NamedTupleType: "namedtuple",
        }[type(t)]
        fields = []
        for f in t.fields:
            self.path.append(f.encode_name)
            try:
                if isinstance(t, mi.TypedDictType):
                    fields.append([f.encode_name, f.required, self.build(f.type)])
                else:
                    fields.append(
                        [
                            f.encode_name,
                            f.required,
                            _default_marker(f, tuple(self.path)),
                            self.build(f.type),
                        ]
                    )
            finally:
                self.path.pop()
        return [kind, fields]


def _dump(obj: Any) -> str:
    return _json.dumps(obj, separators=(",", ":"), ensure_ascii=False, allow_nan=False)


def _render_signature(template: Any, labels: list[int], memo: dict[int, Any]) -> Any:
    """Render a template against current partition labels.

    ``_Ref`` nodes become the partition label of the variable they point at.
    Union members are rendered, deduplicated and sorted by their canonical
    JSON form, making unions order- and duplicate-insensitive.
    """
    if isinstance(template, _Ref):
        return labels[template.idx]
    if not isinstance(template, list):
        return template
    key = id(template)
    cached = memo.get(key)
    if cached is not None:
        return cached
    if template and template[0] == "union":
        members = {_dump(_render_signature(m, labels, memo)) for m in template[1]}
        out = ["union", sorted(members)]
    else:
        out = [_render_signature(part, labels, memo) for part in template]
    memo[key] = out
    return out


def _partition_labels(builder: _GraphBuilder) -> tuple[list[int], list[str]]:
    """Bisimulation partition refinement over the variable graph.

    All variables start in one partition; each round re-derives every
    variable's structural signature from the current labels and re-groups.
    Partitions only refine, so a finite variable graph converges in at most
    ``n`` rounds and recursive/self-referential types terminate.
    """
    n = len(builder.variables)
    labels = [0] * n
    signatures = [""] * n
    # A partition can be split at most n-1 times; headroom guards regressions.
    for _ in range(n + 2):
        memo: dict[int, Any] = {}
        signatures = [
            _dump(_render_signature(template, labels, memo))
            for _, template in builder.variables
        ]
        unique = sorted(set(signatures))
        new_labels = [unique.index(signature) for signature in signatures]
        if new_labels == labels:
            break
        labels = new_labels
    else:  # pragma: no cover - safety net, finite partitions always converge
        raise RuntimeError("wire fingerprint partition refinement did not converge")
    return labels, signatures


def _resolve_options(
    protocol: Any,
    decimal_format: Any,
    uuid_format: Any,
    encoder: Any,
) -> tuple[str, str, bool, str]:
    if encoder is not None:
        from .json import Encoder as _JsonEncoder
        from .msgpack import Encoder as _MsgpackEncoder

        if isinstance(encoder, _MsgpackEncoder):
            encoder_protocol = "msgpack"
        elif isinstance(encoder, _JsonEncoder):
            encoder_protocol = "json"
        else:
            raise TypeError(
                "encoder must be a msgspec.json.Encoder or msgspec.msgpack.Encoder"
            )
        if protocol is _UNSET:
            protocol = encoder_protocol
        elif protocol != encoder_protocol:
            raise ValueError(
                f"protocol={protocol!r} does not match the supplied "
                f"{encoder_protocol} encoder"
            )
        if decimal_format is _UNSET:
            decimal_format = encoder.decimal_format
        if uuid_format is _UNSET:
            uuid_format = encoder.uuid_format
    else:
        if protocol is _UNSET:
            protocol = "json"
        if decimal_format is _UNSET:
            decimal_format = "string"
        if uuid_format is _UNSET:
            uuid_format = "canonical"

    if protocol not in _PROTOCOLS:
        raise ValueError(f"protocol must be one of {_PROTOCOLS!r}, got {protocol!r}")

    decimal_hook = callable(decimal_format)
    if not decimal_hook and decimal_format not in _DECIMAL_FORMATS:
        raise ValueError(
            "decimal_format must be 'string', 'number', or a callable, got "
            f"{decimal_format!r}"
        )
    decimal_label = "hook" if decimal_hook else decimal_format

    allowed_uuid = (
        _MSGPACK_UUID_FORMATS if protocol == "msgpack" else _JSON_UUID_FORMATS
    )
    if uuid_format not in allowed_uuid:
        raise ValueError(
            f"uuid_format for protocol {protocol!r} must be one of "
            f"{allowed_uuid!r}, got {uuid_format!r}"
        )

    return protocol, decimal_label, decimal_hook, uuid_format


def _build_graph(
    typ: Any,
    protocol: str,
    decimal_label: str,
    decimal_hook: bool,
    uuid_format: str,
) -> tuple[_GraphBuilder, Any]:
    # ``type_info`` validates the annotation against a real decoder and gives
    # us a cycle-safe introspection tree.
    root_info = mi.type_info(typ)
    builder = _GraphBuilder(
        protocol=protocol,
        decimal_format=decimal_label,
        decimal_hook=decimal_hook,
        uuid_format=uuid_format,
    )
    root_template = builder.build(root_info)
    return builder, root_template


def _render_with_hashes(
    template: Any, var_hashes: list[str], memo: dict[int, Any]
) -> Any:
    """Render a template substituting variable refs with content hashes.

    Called once after partition refinement has converged, so no iterative
    re-hashing happens here.
    """
    if isinstance(template, _Ref):
        return var_hashes[template.idx]
    if not isinstance(template, list):
        return template
    key = id(template)
    cached = memo.get(key)
    if cached is not None:
        return cached
    if template and template[0] == "union":
        members = {_dump(_render_with_hashes(m, var_hashes, memo)) for m in template[1]}
        out = ["union", sorted(members)]
    else:
        out = [_render_with_hashes(part, var_hashes, memo) for part in template]
    memo[key] = out
    return out


def _root_digest(
    builder: _GraphBuilder,
    root_template: Any,
    labels: list[int],
    signatures: list[str],
) -> tuple[list[str], str]:
    # At convergence a variable's signature fully describes its bisimulation
    # class, so hashing it yields a stable, content-based variable identity.
    var_hashes = [
        _digest(["node", labels[i], signatures[i]])
        for i in range(len(builder.variables))
    ]
    rendered = _render_with_hashes(root_template, var_hashes, {})
    return var_hashes, _digest(["root", rendered])


def _render(template: Any, id_map: dict[int, str]) -> Any:
    if isinstance(template, _Ref):
        return {"$ref": id_map[template.idx]}
    if isinstance(template, list):
        return [_render(part, id_map) for part in template]
    return template


def wire_canonical(
    typ: Any,
    *,
    protocol: Any = _UNSET,
    decimal_format: Any = _UNSET,
    uuid_format: Any = _UNSET,
    encoder: Any = None,
) -> dict[str, Any]:
    """Build the canonical, JSON-able description behind a wire fingerprint.

    The returned mapping is stable across processes and useful for debugging
    why two types fingerprint equal or differently. It contains the resolved
    options, the rendered root type and a ``nodes`` section listing every
    class-backed node (structs, TypedDicts, dataclasses, named tuples) with
    ``$ref`` back-references used for recursive types.

    Parameters
    ----------
    typ: type
        A msgspec-compatible type annotation.
    protocol: {"json", "msgpack"}, optional
        The wire protocol to fingerprint for. Defaults to ``"json"``.
    decimal_format: {"string", "number"} or callable, optional
        The encoder ``decimal_format`` option. A callable makes any
        :class:`decimal.Decimal` node undecidable.
    uuid_format: {"canonical", "hex", "bytes"}, optional
        The encoder ``uuid_format`` option (``"bytes"`` is msgpack-only).
    encoder: msgspec.json.Encoder or msgspec.msgpack.Encoder, optional
        An encoder instance to derive the protocol and format options from.
        Explicit keyword arguments take precedence.

    Raises
    ------
    WireFingerprintUndecidable
        If part of the type tree can only be described through introspectable
        user callables.
    """
    protocol, decimal_label, decimal_hook, uuid_format = _resolve_options(
        protocol, decimal_format, uuid_format, encoder
    )
    builder, root_template = _build_graph(
        typ, protocol, decimal_label, decimal_hook, uuid_format
    )
    labels, signatures = _partition_labels(builder)
    var_hashes, root_hash = _root_digest(builder, root_template, labels, signatures)

    # Assign deterministic variable ids from final partition labels, so the
    # rendered document does not depend on declaration traversal order.
    order = sorted(
        range(len(builder.variables)),
        key=lambda i: (labels[i], _qualname(builder.variables[i][0])),
    )
    id_map = {old: f"v{i}" for i, old in enumerate(order)}

    options = {
        "protocol": protocol,
        "decimal_format": decimal_label,
        "uuid_format": uuid_format,
    }
    document = {
        "version": _VERSION,
        "algorithm": _DIGEST_NAME,
        "options": options,
        "root": _render(root_template, id_map),
        "nodes": [
            {
                "id": id_map[i],
                "name": _qualname(builder.variables[i][0]),
                "hash": var_hashes[i],
                "shape": _render(builder.variables[i][1], id_map),
            }
            for i in order
        ],
    }
    document["fingerprint"] = _digest(["msgspec-wire", _VERSION, options, root_hash])
    return document


def _qualname(obj: Any) -> str:
    return getattr(obj, "__qualname__", None) or repr(obj)


def wire_fingerprint(
    typ: Any,
    *,
    protocol: Any = _UNSET,
    decimal_format: Any = _UNSET,
    uuid_format: Any = _UNSET,
    encoder: Any = None,
) -> str:
    """Compute a cross-process stable wire-structure fingerprint.

    See :func:`wire_canonical` for the parameters and the undecidable cases.

    Returns
    -------
    str
        A ``"blake2b256:<hex>"`` digest. Equal digests mean identical wire
        structure under the given encoding options; different digests mean
        the type contracts differ in some represented aspect.
    """
    document = wire_canonical(
        typ,
        protocol=protocol,
        decimal_format=decimal_format,
        uuid_format=uuid_format,
        encoder=encoder,
    )
    return f"{_DIGEST_NAME}:{document['fingerprint']}"
