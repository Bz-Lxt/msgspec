from __future__ import annotations

import datetime
import decimal
import enum
import math
import sys
import uuid
from collections.abc import Callable, Iterable
from types import UnionType as _types_UnionType
from typing import Any, Final, Literal, NoReturn, Protocol, TypeVar, Union

try:
    from typing import TypeAliasType as _TypeAliasType  # type: ignore
except Exception:
    _TypeAliasType = type("TypeAliasType", (), {})  # type: ignore

import msgspec
from msgspec import NODEFAULT, UNSET, UnsetType as _UnsetType

from ._core import (  # type: ignore
    Factory as _Factory,
    to_builtins as _to_builtins,
)
from ._typing_utils import is_struct, is_struct_type
from ._utils import (  # type: ignore
    _CONCRETE_TYPES,
    _AnnotatedAlias,
    _is_typeddict,
    get_class_annotations as _get_class_annotations,
    get_dataclass_info as _get_dataclass_info,
    get_typeddict_info as _get_typeddict_info,
)

__all__ = (
    "type_info",
    "multi_type_info",
    "Type",
    "Metadata",
    "AnyType",
    "NoneType",
    "BoolType",
    "IntType",
    "FloatType",
    "StrType",
    "BytesType",
    "ByteArrayType",
    "MemoryViewType",
    "DateTimeType",
    "TimeType",
    "DateType",
    "TimeDeltaType",
    "UUIDType",
    "DecimalType",
    "ExtType",
    "RawType",
    "EnumType",
    "LiteralType",
    "CustomType",
    "UnionType",
    "CollectionType",
    "ListType",
    "SetType",
    "FrozenSetType",
    "VarTupleType",
    "TupleType",
    "DictType",
    "Field",
    "TypedDictType",
    "NamedTupleType",
    "DataclassType",
    "StructType",
    "is_struct",
    "is_struct_type",
    "FrozenDictType",
    "UnboundedTypeError",
    "max_json_encoded_size",
    "max_msgpack_encoded_size",
)

_PY315_PLUS = sys.version_info >= (3, 15)


def __dir__():
    return __all__


class Type(msgspec.Struct):
    """The base Type."""


class Metadata(Type):
    """A type wrapping a subtype with additional metadata.

    Parameters
    ----------
    type: Type
        The subtype.
    extra_json_schema: dict, optional
        A dict of extra fields to set for the subtype when generating a
        json-schema.
    extra: dict, optional
        A dict of extra user-defined metadata attached to the subtype.
    """

    type: Type
    extra_json_schema: dict | None = None
    extra: dict | None = None


class AnyType(Type):
    """A type corresponding to `typing.Any`."""


class NoneType(Type):
    """A type corresponding to `None`."""


class BoolType(Type):
    """A type corresponding to `bool`."""


class IntType(Type):
    """A type corresponding to `int`.

    Parameters
    ----------
    gt: int, optional
        If set, an instance of this type must be greater than ``gt``.
    ge: int, optional
        If set, an instance of this type must be greater than or equal to ``ge``.
    lt: int, optional
        If set, an instance of this type must be less than to ``lt``.
    le: int, optional
        If set, an instance of this type must be less than or equal to ``le``.
    multiple_of: int, optional
        If set, an instance of this type must be a multiple of ``multiple_of``.
    """

    gt: int | None = None
    ge: int | None = None
    lt: int | None = None
    le: int | None = None
    multiple_of: int | None = None


class FloatType(Type):
    """A type corresponding to `float`.

    Parameters
    ----------
    gt: float, optional
        If set, an instance of this type must be greater than ``gt``.
    ge: float, optional
        If set, an instance of this type must be greater than or equal to ``ge``.
    lt: float, optional
        If set, an instance of this type must be less than to ``lt``.
    le: float, optional
        If set, an instance of this type must be less than or equal to ``le``.
    multiple_of: float, optional
        If set, an instance of this type must be a multiple of ``multiple_of``.
    """

    gt: float | None = None
    ge: float | None = None
    lt: float | None = None
    le: float | None = None
    multiple_of: float | None = None


class StrType(Type):
    """A type corresponding to `str`.

    Parameters
    ----------
    min_length: int, optional
        If set, an instance of this type must have length greater than or equal
        to ``min_length``.
    max_length: int, optional
        If set, an instance of this type must have length less than or equal
        to ``max_length``.
    pattern: str, optional
        If set, an instance of this type must match against this regex pattern.
        Note that the pattern is treated as **unanchored**.
    """

    min_length: int | None = None
    max_length: int | None = None
    pattern: str | None = None


class BytesType(Type):
    """A type corresponding to `bytes`.

    Parameters
    ----------
    min_length: int, optional
        If set, an instance of this type must have length greater than or equal
        to ``min_length``.
    max_length: int, optional
        If set, an instance of this type must have length less than or equal
        to ``max_length``.
    """

    min_length: int | None = None
    max_length: int | None = None


class ByteArrayType(Type):
    """A type corresponding to `bytearray`.

    Parameters
    ----------
    min_length: int, optional
        If set, an instance of this type must have length greater than or equal
        to ``min_length``.
    max_length: int, optional
        If set, an instance of this type must have length less than or equal
        to ``max_length``.
    """

    min_length: int | None = None
    max_length: int | None = None


class MemoryViewType(Type):
    """A type corresponding to `memoryview`.

    Parameters
    ----------
    min_length: int, optional
        If set, an instance of this type must have length greater than or equal
        to ``min_length``.
    max_length: int, optional
        If set, an instance of this type must have length less than or equal
        to ``max_length``.
    """

    min_length: int | None = None
    max_length: int | None = None


class DateTimeType(Type):
    """A type corresponding to `datetime.datetime`.

    Parameters
    ----------
    tz: bool
        The timezone-requirements for an instance of this type. ``True``
        indicates a timezone-aware value is required, ``False`` indicates a
        timezone-naive value is required. The default is ``None``, which
        accepts either timezone-aware or timezone-naive values.
    """

    tz: bool | None = None


class TimeType(Type):
    """A type corresponding to `datetime.time`.

    Parameters
    ----------
    tz: bool
        The timezone-requirements for an instance of this type. ``True``
        indicates a timezone-aware value is required, ``False`` indicates a
        timezone-aware value is required. The default is ``None``, which
        accepts either timezone-aware or timezone-naive values.
    """

    tz: bool | None = None


class DateType(Type):
    """A type corresponding to `datetime.date`."""


class TimeDeltaType(Type):
    """A type corresponding to `datetime.timedelta`."""


class UUIDType(Type):
    """A type corresponding to `uuid.UUID`."""


class DecimalType(Type):
    """A type corresponding to `decimal.Decimal`."""


class ExtType(Type):
    """A type corresponding to `msgspec.msgpack.Ext`."""


class RawType(Type):
    """A type corresponding to `msgspec.Raw`."""


class EnumType(Type):
    """A type corresponding to an `enum.Enum` type.

    Parameters
    ----------
    cls: type
        The corresponding `enum.Enum` type.
    """

    cls: type[enum.Enum]


class LiteralType(Type):
    """A type corresponding to a `typing.Literal` type.

    Parameters
    ----------
    values: tuple
        A tuple of possible values for this literal instance. Only `bool`,
        `str`, `int`, or `None` literals are supported, and a single literal
        may mix these types (e.g. ``Literal[1, None]``).
    """

    values: tuple[bool | str | int | None, ...]


class CustomType(Type):
    """A custom type.

    Parameters
    ----------
    cls: type
        The corresponding custom type.
    """

    cls: type


class UnionType(Type):
    """A union type.

    Parameters
    ----------
    types: tuple[type, ...]
        A tuple of possible types for this union.
    """

    types: tuple[Type, ...]

    @property
    def includes_none(self) -> bool:
        """A helper for checking whether ``None`` is included in this union."""
        return any(isinstance(t, NoneType) for t in self.types)


class CollectionType(Type):
    """A collection type.

    This is the base type shared by collection types like `ListType`,
    `SetType`, etc.

    Parameters
    ----------
    item_type: Type
        The item type.
    min_length: int, optional
        If set, an instance of this type must have length greater than or equal
        to ``min_length``.
    max_length: int, optional
        If set, an instance of this type must have length less than or equal
        to ``max_length``.
    """

    item_type: Type
    min_length: int | None = None
    max_length: int | None = None


class ListType(CollectionType):
    """A type corresponding to a `list`.

    Parameters
    ----------
    item_type: Type
        The item type.
    min_length: int, optional
        If set, an instance of this type must have length greater than or equal
        to ``min_length``.
    max_length: int, optional
        If set, an instance of this type must have length less than or equal
        to ``max_length``.
    """


class VarTupleType(CollectionType):
    """A type corresponding to a variadic `tuple`.

    Parameters
    ----------
    item_type: Type
        The item type.
    min_length: int, optional
        If set, an instance of this type must have length greater than or equal
        to ``min_length``.
    max_length: int, optional
        If set, an instance of this type must have length less than or equal
        to ``max_length``.
    """


class SetType(CollectionType):
    """A type corresponding to a `set`.

    Parameters
    ----------
    item_type: Type
        The item type.
    min_length: int, optional
        If set, an instance of this type must have length greater than or equal
        to ``min_length``.
    max_length: int, optional
        If set, an instance of this type must have length less than or equal
        to ``max_length``.
    """


class FrozenSetType(CollectionType):
    """A type corresponding to a `frozenset`.

    Parameters
    ----------
    item_type: Type
        The item type.
    min_length: int, optional
        If set, an instance of this type must have length greater than or equal
        to ``min_length``.
    max_length: int, optional
        If set, an instance of this type must have length less than or equal
        to ``max_length``.
    """


class TupleType(Type):
    """A type corresponding to `tuple`.

    Parameters
    ----------
    item_types: tuple[Type, ...]
        A tuple of types for each element in the tuple.
    """

    item_types: tuple[Type, ...]


class DictType(Type):
    """A type corresponding to `dict`.

    Parameters
    ----------
    key_type: Type
        The key type.
    value_type: Type
        The value type.
    min_length: int, optional
        If set, an instance of this type must have length greater than or equal
        to ``min_length``.
    max_length: int, optional
        If set, an instance of this type must have length less than or equal
        to ``max_length``.
    """

    key_type: Type
    value_type: Type
    min_length: int | None = None
    max_length: int | None = None


class FrozenDictType(Type):
    """A type corresponding to `frozendict`.

    Can only be emitted on Python 3.15+.

    Parameters
    ----------
    key_type: Type
        The key type.
    value_type: Type
        The value type.
    min_length: int, optional
        If set, an instance of this type must have length greater than or equal
        to ``min_length``.
    max_length: int, optional
        If set, an instance of this type must have length less than or equal
        to ``max_length``.
    """

    key_type: Type
    value_type: Type
    min_length: Union[int, None] = None
    max_length: Union[int, None] = None


class Field(msgspec.Struct):
    """A record describing a field in an object-like type.

    Parameters
    ----------
    name: str
        The field name as seen by Python code (e.g. ``field_one``).
    encode_name: str
        The name used when encoding/decoding the field. This may differ if
        the field is renamed (e.g. ``fieldOne``).
    type: Type
        The field type.
    required: bool, optional
        Whether the field is required. Note that if `required` is False doesn't
        necessarily mean that `default` or `default_factory` will be set -
        optional fields may exist with no default value.
    default: Any, optional
        A default value for the field. Will be `NODEFAULT` if no default value
        is set.
    default_factory: Any, optional
        A callable that creates a default value for the field. Will be
        `NODEFAULT` if no ``default_factory`` is set.
    """

    name: str
    encode_name: str
    type: Type
    required: bool = True
    default: Any = msgspec.field(default_factory=lambda: NODEFAULT)
    default_factory: Any = msgspec.field(default_factory=lambda: NODEFAULT)


class TypedDictType(Type):
    """A type corresponding to a `typing.TypedDict` type.

    Parameters
    ----------
    cls: type
        The corresponding TypedDict type.
    fields: tuple[Field, ...]
        A tuple of fields in the TypedDict.
    """

    cls: type
    fields: tuple[Field, ...]


class NamedTupleType(Type):
    """A type corresponding to a `typing.NamedTuple` type.

    Parameters
    ----------
    cls: type
        The corresponding NamedTuple type.
    fields: tuple[Field, ...]
        A tuple of fields in the NamedTuple.
    """

    cls: type
    fields: tuple[Field, ...]


class DataclassType(Type):
    """A type corresponding to a `dataclasses` or `attrs` type.

    Parameters
    ----------
    cls: type
        The corresponding dataclass type.
    fields: tuple[Field, ...]
        A tuple of fields in the dataclass.
    """

    cls: type
    fields: tuple[Field, ...]


class StructType(Type):
    """A type corresponding to a `msgspec.Struct` type.

    Parameters
    ----------
    cls: type
        The corresponding Struct type.
    fields: tuple[Field, ...]
        A tuple of fields in the Struct.
    tag_field: str or None, optional
        If set, the field name used for the tag in a tagged union.
    tag: str, int, or None, optional
        If set, the value used for the tag in a tagged union.
    array_like: bool, optional
        Whether the struct is encoded as an array rather than an object.
    forbid_unknown_fields: bool, optional
        If ``False`` (the default) unknown fields are ignored when decoding. If
        ``True`` any unknown fields will result in an error.
    """

    cls: type[msgspec.Struct]
    fields: tuple[Field, ...]
    tag_field: str | None = None
    tag: str | int | None = None
    array_like: bool = False
    forbid_unknown_fields: bool = False


def multi_type_info(types: Iterable[Any]) -> tuple[Type, ...]:
    """Get information about multiple msgspec-compatible types.

    Parameters
    ----------
    types: an iterable of types
        The types to get info about.

    Returns
    -------
    tuple[Type, ...]

    Examples
    --------
    >>> msgspec.inspect.multi_type_info([int, float, list[str]])  # doctest: +NORMALIZE_WHITESPACE
    (IntType(gt=None, ge=None, lt=None, le=None, multiple_of=None),
     FloatType(gt=None, ge=None, lt=None, le=None, multiple_of=None),
     ListType(item_type=StrType(min_length=None, max_length=None, pattern=None),
              min_length=None, max_length=None))
    """
    return _Translator(types).run()


def type_info(type: Any) -> Type:
    """Get information about a msgspec-compatible type.

    Note that if you need to inspect multiple types it's more efficient to call
    `multi_type_info` once with a sequence of types than calling `type_info`
    multiple times.

    Parameters
    ----------
    type: type
        The type to get info about.

    Returns
    -------
    Type

    Examples
    --------
    >>> msgspec.inspect.type_info(bool)
    BoolType()

    >>> msgspec.inspect.type_info(int)
    IntType(gt=None, ge=None, lt=None, le=None, multiple_of=None)

    >>> msgspec.inspect.type_info(list[int])  # doctest: +NORMALIZE_WHITESPACE
    ListType(item_type=IntType(gt=None, ge=None, lt=None, le=None, multiple_of=None),
             min_length=None, max_length=None)
    """
    return multi_type_info([type])[0]


# Implementation details
def _origin_args_metadata(t):
    # Strip wrappers (Annotated, NewType, Final) until we hit a concrete type
    metadata = []
    while True:
        try:
            origin = _CONCRETE_TYPES.get(t)
        except TypeError:
            # t is not hashable
            origin = None

        if origin is not None:
            args = None
            break

        origin = getattr(t, "__origin__", None)
        if origin is not None:
            if type(t) is _AnnotatedAlias:
                metadata.extend(m for m in t.__metadata__ if type(m) is msgspec.Meta)
                t = origin
            elif origin == Final:
                t = t.__args__[0]
            elif type(origin) is _TypeAliasType:
                t = origin.__value__[t.__args__]
            else:
                args = getattr(t, "__args__", None)
                origin = _CONCRETE_TYPES.get(origin, origin)
                break
        else:
            supertype = getattr(t, "__supertype__", None)
            if supertype is not None:
                t = supertype
            elif type(t) is _TypeAliasType:
                t = t.__value__
            else:
                origin = t
                args = None
                break

    if type(origin) is _types_UnionType:
        args = origin.__args__
        origin = Union
    return origin, args, tuple(metadata)


def _sort_literal_args(args):
    # `Literal` may mix value types (e.g. `Literal[1, None]`), which a plain
    # `sorted` can't order since Python 3 forbids comparing across types. Sort
    # by type name first so members of the same type stay ordered as before,
    # while mixed-type literals are grouped deterministically instead of
    # crashing.
    try:
        return tuple(sorted(args, key=lambda x: (type(x).__name__, x)))
    except TypeError:
        return tuple(args)


def _is_enum(t):
    return type(t) is enum.EnumMeta


def _is_dataclass(t):
    return hasattr(t, "__dataclass_fields__")


def _is_attrs(t):
    return hasattr(t, "__attrs_attrs__")


def _is_namedtuple(t):
    try:
        return issubclass(t, tuple) and hasattr(t, "_fields")
    except TypeError:
        return False


def _merge_json(a, b):
    if b:
        a = a.copy()
        for key, b_val in b.items():
            if key in a:
                a_val = a[key]
                if isinstance(a_val, dict) and isinstance(b_val, dict):
                    a[key] = _merge_json(a_val, b_val)
                elif isinstance(a_val, (list, tuple)) and isinstance(
                    b_val, (list, tuple)
                ):
                    a[key] = list(a_val) + list(b_val)
                else:
                    a[key] = b_val
            else:
                a[key] = b_val
    return a


class _Translator:
    def __init__(self, types):
        self.types = tuple(types)
        self.type_hints = {}
        self.cache = {}

    def _get_class_annotations(self, t):
        """A cached version of `get_class_annotations`"""
        try:
            return self.type_hints[t]
        except KeyError:
            out = self.type_hints[t] = _get_class_annotations(t)
            return out

    def run(self):
        # First construct a decoder to validate the types are valid
        from ._core import MsgpackDecoder

        MsgpackDecoder(tuple[self.types])
        return tuple(self.translate(t) for t in self.types)

    def translate(self, typ):
        t, args, metadata = _origin_args_metadata(typ)

        # Extract and merge components of any `Meta` annotations
        constrs = {}
        extra_json_schema = {}
        extra = {}
        for meta in metadata:
            for attr in (
                "ge",
                "gt",
                "le",
                "lt",
                "multiple_of",
                "pattern",
                "min_length",
                "max_length",
                "tz",
            ):
                if (val := getattr(meta, attr)) is not None:
                    constrs[attr] = val
            for attr in ("title", "description", "examples"):
                if (val := getattr(meta, attr)) is not None:
                    extra_json_schema[attr] = val
            if meta.extra_json_schema is not None:
                extra_json_schema = _merge_json(
                    extra_json_schema,
                    _to_builtins(meta.extra_json_schema, str_keys=True),
                )
            if meta.extra is not None:
                extra.update(meta.extra)

        out = self._translate_inner(t, args, **constrs)
        if extra_json_schema or extra:
            # If extra metadata is present, wrap the output type in a Metadata
            # wrapper object
            return Metadata(
                out, extra_json_schema=extra_json_schema or None, extra=extra or None
            )
        return out

    def _translate_inner(
        self,
        t,
        args,
        ge=None,
        gt=None,
        le=None,
        lt=None,
        multiple_of=None,
        pattern=None,
        min_length=None,
        max_length=None,
        tz=None,
    ):
        if t is Any:
            return AnyType()
        elif isinstance(t, TypeVar):
            if t.__bound__ is not None:
                return self.translate(t.__bound__)
            return AnyType()
        elif t is None or t is type(None):
            return NoneType()
        elif t is bool:
            return BoolType()
        elif t is int:
            return IntType(ge=ge, gt=gt, le=le, lt=lt, multiple_of=multiple_of)
        elif t is float:
            return FloatType(ge=ge, gt=gt, le=le, lt=lt, multiple_of=multiple_of)
        elif t is str:
            return StrType(
                min_length=min_length, max_length=max_length, pattern=pattern
            )
        elif t is bytes:
            return BytesType(min_length=min_length, max_length=max_length)
        elif t is bytearray:
            return ByteArrayType(min_length=min_length, max_length=max_length)
        elif t is memoryview:
            return MemoryViewType(min_length=min_length, max_length=max_length)
        elif t is datetime.datetime:
            return DateTimeType(tz=tz)
        elif t is datetime.time:
            return TimeType(tz=tz)
        elif t is datetime.date:
            return DateType()
        elif t is datetime.timedelta:
            return TimeDeltaType()
        elif t is uuid.UUID:
            return UUIDType()
        elif t is decimal.Decimal:
            return DecimalType()
        elif t is msgspec.Raw:
            return RawType()
        elif t is msgspec.msgpack.Ext:
            return ExtType()
        elif t is list:
            return ListType(
                self.translate(args[0]) if args else AnyType(),
                min_length=min_length,
                max_length=max_length,
            )
        elif t is set:
            return SetType(
                self.translate(args[0]) if args else AnyType(),
                min_length=min_length,
                max_length=max_length,
            )
        elif t is frozenset:
            return FrozenSetType(
                self.translate(args[0]) if args else AnyType(),
                min_length=min_length,
                max_length=max_length,
            )
        elif t is tuple:
            # Handle an annoying compatibility issue:
            # - Tuple[()] has args == ((),)
            # - tuple[()] has args == ()
            if args == ((),):
                args = ()
            if args is None:
                return VarTupleType(
                    AnyType(), min_length=min_length, max_length=max_length
                )
            elif len(args) == 2 and args[-1] is ...:
                return VarTupleType(
                    self.translate(args[0]),
                    min_length=min_length,
                    max_length=max_length,
                )
            else:
                return TupleType(tuple(self.translate(a) for a in args))
        elif t is dict:
            return DictType(
                self.translate(args[0]) if args else AnyType(),
                self.translate(args[1]) if args else AnyType(),
                min_length=min_length,
                max_length=max_length,
            )
        elif _PY315_PLUS and t is frozendict:  # noqa: F821
            return FrozenDictType(
                self.translate(args[0]) if args else AnyType(),
                self.translate(args[1]) if args else AnyType(),
                min_length=min_length,
                max_length=max_length,
            )
        elif t is Union:
            args = tuple(self.translate(a) for a in args if a is not _UnsetType)
            return args[0] if len(args) == 1 else UnionType(args)
        elif t is Literal:
            return LiteralType(_sort_literal_args(args))
        elif _is_enum(t):
            return EnumType(t)
        elif is_struct_type(t):
            cls = t[args] if args else t
            if cls in self.cache:
                return self.cache[cls]
            config = t.__struct_config__
            self.cache[cls] = out = StructType(
                cls,
                (),
                tag_field=config.tag_field,
                tag=config.tag,
                array_like=config.array_like,
                forbid_unknown_fields=config.forbid_unknown_fields,
            )

            hints = self._get_class_annotations(cls)
            npos = len(t.__struct_fields__) - len(t.__struct_defaults__)
            fields = []
            for name, encode_name, default_obj in zip(
                t.__struct_fields__,
                t.__struct_encode_fields__,
                (NODEFAULT,) * npos + t.__struct_defaults__,
            ):
                if default_obj is NODEFAULT:
                    required = True
                    default = default_factory = NODEFAULT
                elif isinstance(default_obj, _Factory):
                    required = False
                    default = NODEFAULT
                    default_factory = default_obj.factory
                else:
                    required = False
                    default = NODEFAULT if default_obj is UNSET else default_obj
                    default_factory = NODEFAULT

                field = Field(
                    name=name,
                    encode_name=encode_name,
                    type=self.translate(hints[name]),
                    required=required,
                    default=default,
                    default_factory=default_factory,
                )
                fields.append(field)

            out.fields = tuple(fields)
            return out
        elif _is_typeddict(t):
            cls = t[args] if args else t
            if cls in self.cache:
                return self.cache[cls]
            self.cache[cls] = out = TypedDictType(cls, ())
            hints, required = _get_typeddict_info(cls)
            out.fields = tuple(
                Field(
                    name=name,
                    encode_name=name,
                    type=self.translate(field_type),
                    required=name in required,
                )
                for name, field_type in sorted(hints.items())
            )
            return out
        elif _is_dataclass(t) or _is_attrs(t):
            cls = t[args] if args else t
            if cls in self.cache:
                return self.cache[cls]
            self.cache[cls] = out = DataclassType(cls, ())
            _, info, defaults, _, _ = _get_dataclass_info(cls)
            defaults = ((NODEFAULT,) * (len(info) - len(defaults))) + defaults
            fields = []
            for (name, typ, is_factory), default_obj in zip(info, defaults):
                if default_obj is NODEFAULT:
                    required = True
                    default = default_factory = NODEFAULT
                elif is_factory:
                    required = False
                    default = NODEFAULT
                    default_factory = default_obj
                else:
                    required = False
                    default = NODEFAULT if default_obj is UNSET else default_obj
                    default_factory = NODEFAULT

                fields.append(
                    Field(
                        name=name,
                        encode_name=name,
                        type=self.translate(typ),
                        required=required,
                        default=default,
                        default_factory=default_factory,
                    )
                )
            out.fields = tuple(fields)
            return out
        elif _is_namedtuple(t):
            cls = t[args] if args else t
            if cls in self.cache:
                return self.cache[cls]
            self.cache[cls] = out = NamedTupleType(cls, ())
            hints = self._get_class_annotations(cls)
            out.fields = tuple(
                Field(
                    name=name,
                    encode_name=name,
                    type=self.translate(hints.get(name, Any)),
                    required=name not in t._field_defaults,
                    default=t._field_defaults.get(name, NODEFAULT),
                )
                for name in t._fields
            )
            return out
        else:
            return CustomType(t)


# ---------------------------------------------------------------------------
# Encoded size upper bounds
# ---------------------------------------------------------------------------


class UnboundedTypeError(ValueError):
    """Raised when no finite upper bound on an encoded size can be computed.

    A finite upper bound only exists when every branch of a type has a
    statically knowable size limit. This error is raised for types that can
    grow without limit or whose encoded form is opaque, including:

    - `AnyType` and `CustomType` (the latter relies on a user ``enc_hook``)
    - `RawType` and msgpack `ExtType` (opaque payloads)
    - `StrType`, bytes-like types and containers without a ``max_length``
      constraint
    - `IntType` without bounds on both ends when encoding to JSON (JSON ints
      have arbitrary precision)
    - `DecimalType` unless MessagePack ``decimal_format="number"`` is used
    - any recursive type, whose values may nest arbitrarily deep
    """


# Bytes that JSON encodes with a short two-byte escape (e.g. ``\n``); every
# other control byte is expanded to a six-byte ``\\u00XX`` escape.
_JSON_SHORT_ESCAPES = frozenset((0x08, 0x09, 0x0A, 0x0C, 0x0D))


def _numeric_endpoints(
    t: IntType,
) -> tuple[int | float | None, int | float | None]:
    """Return the inclusive (lower, upper) bounds implied by numeric constraints."""
    if t.ge is not None:
        lower = t.ge
    elif t.gt is not None:
        lower = t.gt + 1
    else:
        lower = None
    if t.le is not None:
        upper = t.le
    elif t.lt is not None:
        upper = t.lt - 1
    else:
        upper = None
    return lower, upper


_PRIMITIVE_TYPE_NAMES: dict[type, str] = {
    AnyType: "Any",
    NoneType: "None",
    BoolType: "bool",
    IntType: "int",
    FloatType: "float",
    StrType: "str",
    BytesType: "bytes",
    ByteArrayType: "bytearray",
    MemoryViewType: "memoryview",
    DateTimeType: "datetime.datetime",
    TimeType: "datetime.time",
    DateType: "datetime.date",
    TimeDeltaType: "datetime.timedelta",
    UUIDType: "uuid.UUID",
    DecimalType: "decimal.Decimal",
    ExtType: "msgspec.msgpack.Ext",
    RawType: "msgspec.Raw",
}


def _type_label(t: Type) -> str:
    cls = getattr(t, "cls", None)
    name = getattr(cls, "__name__", None)
    if name is not None:
        return f"`{name}`"
    primitive = _PRIMITIVE_TYPE_NAMES.get(type(t))
    if primitive is not None:
        return f"`{primitive}`"
    return f"`{type(t).__name__}`"


def _mp_str_header_size(byte_len: int) -> int:
    """MessagePack str header size for a payload of at most ``byte_len`` bytes."""
    if byte_len < 1 << 5:
        return 1
    if byte_len < 1 << 8:
        return 2
    if byte_len < 1 << 16:
        return 3
    return 5


def _mp_bin_header_size(byte_len: int) -> int:
    """MessagePack bin header size for a payload of at most ``byte_len`` bytes."""
    if byte_len < 1 << 8:
        return 2
    if byte_len < 1 << 16:
        return 3
    return 5


def _mp_array_header_size(length: int) -> int:
    """MessagePack array header size for at most ``length`` elements."""
    if length < 16:
        return 1
    if length < 1 << 16:
        return 3
    return 5


_mp_map_header_size = _mp_array_header_size


def _mp_int_size(value: int) -> int:
    """The exact MessagePack encoding size of a concrete integer."""
    if value >= 0:
        if value < 1 << 7:
            return 1
        if value < 1 << 8:
            return 2
        if value < 1 << 16:
            return 3
        if value < 1 << 32:
            return 5
        return 9
    if value >= -(1 << 5):
        return 1
    if value >= -(1 << 7):
        return 2
    if value >= -(1 << 15):
        return 3
    if value >= -(1 << 31):
        return 5
    return 9


def _mp_concrete_str_size(value: str) -> int:
    """The exact MessagePack encoding size of a concrete string."""
    byte_len = len(value.encode("utf-8"))
    return _mp_str_header_size(byte_len) + byte_len


def _json_concrete_str_size(value: str) -> int:
    """The exact worst-case JSON encoding size of a concrete string."""
    data = value.encode("utf-8")
    extra = 0
    for c in data:
        if c < 0x20:
            extra += 1 if c in _JSON_SHORT_ESCAPES else 5
        elif c == 0x22 or c == 0x5C:
            extra += 1
    return 2 + len(data) + extra


class _HasMaxLength(Protocol):
    max_length: int | None


class _EncodedSizeBounder:
    """Computes a safe upper bound on the encoded size of a `Type` tree.

    The bound holds for every value that conforms to the inspected type and
    its constraints. A type graph that contains a branch without a finite
    size limit raises `UnboundedTypeError` instead of returning a result.
    """

    codec: str = ""
    NONE_SIZE: int = 0
    BOOL_SIZE: int = 0

    def __init__(self, *, uuid_format: str, decimal_format: Any) -> None:
        self._memo: dict[int, tuple[Type, int]] = {}
        self._stack: set[int] = set()
        self.uuid_format = uuid_format
        self.decimal_format = decimal_format

    # -- infrastructure ----------------------------------------------------

    def _fail(self, t: Any, reason: str) -> NoReturn:
        raise UnboundedTypeError(
            f"cannot determine a finite {self.codec} encoded-size upper bound "
            f"for {_type_label(t)}: {reason}"
        )

    def _require_max_length(self, t: _HasMaxLength) -> int:
        if t.max_length is None:
            self._fail(
                t,
                "an explicit `Meta(max_length=...)` constraint is required to "
                "bound the size of conforming values",
            )
        return t.max_length

    def bound(self, t: Type) -> int:
        key = id(t)
        cached = self._memo.get(key)
        if cached is not None:
            return cached[1]
        if key in self._stack:
            raise UnboundedTypeError(
                f"{_type_label(t)} is a recursive type; conforming values may "
                "nest arbitrarily deep, so no finite upper bound on the "
                f"{self.codec} encoded size exists"
            )
        self._stack.add(key)
        try:
            result = self.dispatch(t)
        finally:
            self._stack.discard(key)
        self._memo[key] = (t, result)
        return result

    def bound_key(self, t: Type) -> int:
        """Upper bound for a value used as a mapping key."""
        return self.bound(t)

    # -- dispatch ----------------------------------------------------------

    def dispatch(self, t: Type) -> int:
        if isinstance(t, Metadata):
            return self.bound(t.type)
        if isinstance(t, AnyType):
            self._fail(t, "`Any` may hold values of arbitrary size")
        elif isinstance(t, NoneType):
            return self.NONE_SIZE
        elif isinstance(t, BoolType):
            return self.BOOL_SIZE
        elif isinstance(t, IntType):
            return self.int_bound(t)
        elif isinstance(t, FloatType):
            return self.float_bound(t)
        elif isinstance(t, StrType):
            return self.str_bound(t)
        elif isinstance(t, (BytesType, ByteArrayType, MemoryViewType)):
            return self.bytes_bound(t)
        elif isinstance(t, DateTimeType):
            return self.datetime_bound(t)
        elif isinstance(t, TimeType):
            return self.time_bound(t)
        elif isinstance(t, DateType):
            return self.date_bound(t)
        elif isinstance(t, TimeDeltaType):
            return self.timedelta_bound(t)
        elif isinstance(t, UUIDType):
            return self.uuid_bound(t)
        elif isinstance(t, DecimalType):
            return self.decimal_bound(t)
        elif isinstance(t, ExtType):
            return self.ext_bound(t)
        elif isinstance(t, RawType):
            self._fail(
                t,
                "`msgspec.Raw` payloads are copied through verbatim and have "
                "no bounded size",
            )
        elif isinstance(t, EnumType):
            return self.enum_bound(t)
        elif isinstance(t, LiteralType):
            return self.literal_bound(t)
        elif isinstance(t, CustomType):
            self._fail(
                t,
                "custom types are encoded with a user-provided `enc_hook`, "
                "whose output size is not statically known",
            )
        elif isinstance(t, UnionType):
            return max(self.bound(st) for st in t.types)
        elif isinstance(t, CollectionType):
            return self.collection_bound(t)
        elif isinstance(t, TupleType):
            return self.fixed_tuple_bound(t)
        elif isinstance(t, (DictType, FrozenDictType)):
            return self.dict_bound(t)
        elif isinstance(t, StructType):
            return self.struct_bound(t)
        elif isinstance(t, NamedTupleType):
            return self.named_tuple_bound(t)
        elif isinstance(t, (TypedDictType, DataclassType)):
            return self.object_bound(t)
        self._fail(t, "unsupported type")  # pragma: no cover

    # -- shared structural composition ------------------------------------

    def enum_bound(self, t: EnumType) -> int:
        return max(self._concrete(member.value) for member in t.cls)

    def literal_bound(self, t: LiteralType) -> int:
        return max(self._concrete(value) for value in t.values)

    def collection_bound(self, t: CollectionType) -> int:
        max_length = self._require_max_length(t)
        item_bound = self.bound(t.item_type)
        return self._collection(max_length, item_bound)

    def fixed_tuple_bound(self, t: TupleType) -> int:
        return self._fixed_array(tuple(self.bound(st) for st in t.item_types))

    def dict_bound(self, t: DictType | FrozenDictType) -> int:
        max_length = self._require_max_length(t)
        key_bound = self.bound_key(t.key_type)
        value_bound = self.bound(t.value_type)
        return self._mapping(max_length, key_bound, value_bound)

    def struct_bound(self, t: StructType) -> int:
        field_bounds = tuple(self.bound(f.type) for f in t.fields)
        if t.array_like:
            entries = field_bounds
            if t.tag is not None:
                entries = (self._tag_value_bound(t.tag),) + entries
            return self._fixed_array(entries)
        return self._struct_object(t, field_bounds)

    def named_tuple_bound(self, t: NamedTupleType) -> int:
        # NamedTuple instances are tuple subclasses and encode as arrays.
        return self._fixed_array(tuple(self.bound(f.type) for f in t.fields))

    def object_bound(self, t: TypedDictType | DataclassType) -> int:
        field_bounds = tuple(self.bound(f.type) for f in t.fields)
        return self._plain_object(t.fields, field_bounds)

    # -- hooks implemented per codec --------------------------------------

    def int_bound(self, t: IntType) -> int:
        raise NotImplementedError  # pragma: no cover

    def float_bound(self, t: FloatType) -> int:
        raise NotImplementedError  # pragma: no cover

    def str_bound(self, t: StrType) -> int:
        raise NotImplementedError  # pragma: no cover

    def bytes_bound(self, t: BytesType | ByteArrayType | MemoryViewType) -> int:
        raise NotImplementedError  # pragma: no cover

    def datetime_bound(self, t: DateTimeType) -> int:
        raise NotImplementedError  # pragma: no cover

    def time_bound(self, t: TimeType) -> int:
        raise NotImplementedError  # pragma: no cover

    def date_bound(self, t: DateType) -> int:
        raise NotImplementedError  # pragma: no cover

    def timedelta_bound(self, t: TimeDeltaType) -> int:
        raise NotImplementedError  # pragma: no cover

    def uuid_bound(self, t: UUIDType) -> int:
        raise NotImplementedError  # pragma: no cover

    def decimal_bound(self, t: DecimalType) -> int:
        raise NotImplementedError  # pragma: no cover

    def ext_bound(self, t: ExtType) -> int:
        raise NotImplementedError  # pragma: no cover

    def _concrete(self, value: Any) -> int:
        raise NotImplementedError  # pragma: no cover

    def _collection(self, max_length: int, item_bound: int) -> int:
        raise NotImplementedError  # pragma: no cover

    def _fixed_array(self, bounds: tuple[int, ...]) -> int:
        raise NotImplementedError  # pragma: no cover

    def _mapping(self, max_length: int, key_bound: int, value_bound: int) -> int:
        raise NotImplementedError  # pragma: no cover

    def _field_name_size(self, name: str) -> int:
        raise NotImplementedError  # pragma: no cover

    def _tag_value_bound(self, tag: str | int) -> int:
        raise NotImplementedError  # pragma: no cover

    def _plain_object(
        self, fields: tuple[Field, ...], field_bounds: tuple[int, ...]
    ) -> int:
        raise NotImplementedError  # pragma: no cover

    def _struct_object(self, t: StructType, field_bounds: tuple[int, ...]) -> int:
        raise NotImplementedError  # pragma: no cover


class _JSONSizeBounder(_EncodedSizeBounder):
    codec = "JSON"
    NONE_SIZE = 4  # ``null``
    BOOL_SIZE = 5  # ``false``
    FLOAT_SIZE = 24  # longest ryu output, e.g. ``-1.2345678901234567e-300``
    FLOAT_KEY_SIZE = 26  # a float key is a quoted float
    DATE_SIZE = 12
    TIME_SIZE = 23
    DATETIME_SIZE = 34
    TIMEDELTA_SIZE = 28

    def __init__(self, *, uuid_format: str, decimal_format: Any) -> None:
        if uuid_format not in ("canonical", "hex"):
            raise ValueError("uuid_format must be 'canonical' or 'hex'")
        super().__init__(uuid_format=uuid_format, decimal_format=decimal_format)

    def int_bound(self, t: IntType) -> int:
        lower, upper = _numeric_endpoints(t)
        if lower is None or upper is None:
            self._fail(
                t,
                "JSON integers have arbitrary precision; constrain both ends "
                "with `Meta(ge=..., le=...)` (or `gt`/`lt`) to bound the size",
            )
        if not isinstance(lower, int):
            lower = math.ceil(lower)
        if not isinstance(upper, int):
            upper = math.floor(upper)
        magnitude = max(abs(lower), abs(upper))
        return len(str(magnitude)) + (1 if lower < 0 else 0)

    def float_bound(self, t: FloatType) -> int:
        return self.FLOAT_SIZE

    def str_bound(self, t: StrType) -> int:
        # At most 6 JSON bytes per code point (a control byte becomes ``\u00XX``)
        # plus the surrounding quotes.
        return 2 + 6 * self._require_max_length(t)

    def bytes_bound(self, t: BytesType | ByteArrayType | MemoryViewType) -> int:
        max_length = self._require_max_length(t)
        return 2 + 4 * ((max_length + 2) // 3)

    def datetime_bound(self, t: DateTimeType) -> int:
        return self.DATETIME_SIZE

    def time_bound(self, t: TimeType) -> int:
        return self.TIME_SIZE

    def date_bound(self, t: DateType) -> int:
        return self.DATE_SIZE

    def timedelta_bound(self, t: TimeDeltaType) -> int:
        return self.TIMEDELTA_SIZE

    def uuid_bound(self, t: UUIDType) -> int:
        return 38 if self.uuid_format == "canonical" else 34

    def decimal_bound(self, t: DecimalType) -> int:
        if callable(self.decimal_format):
            reason = "a callable `decimal_format` may produce output of arbitrary size"
        elif self.decimal_format == "number":
            reason = (
                "JSON numbers are written from the decimal's full digit string, "
                "which has no length limit"
            )
        else:
            reason = "decimal strings have no length limit"
        self._fail(t, reason)

    def ext_bound(self, t: ExtType) -> int:
        self._fail(
            t,
            "`msgspec.msgpack.Ext` is not JSON-serializable without a custom "
            "`enc_hook`, whose output size is not statically known",
        )

    def _concrete(self, value: Any) -> int:
        if value is None:
            return self.NONE_SIZE
        if isinstance(value, bool):
            return self.BOOL_SIZE
        if isinstance(value, int):
            return len(str(value))
        if isinstance(value, str):
            return _json_concrete_str_size(value)
        raise UnboundedTypeError(  # pragma: no cover - guarded by type_info
            f"unsupported literal or enum value {value!r}"
        )

    def _collection(self, max_length: int, item_bound: int) -> int:
        return 2 + max_length * (item_bound + 1)

    def _fixed_array(self, bounds: tuple[int, ...]) -> int:
        if not bounds:
            return 2
        return sum(bounds) + len(bounds) + 1

    def _mapping(self, max_length: int, key_bound: int, value_bound: int) -> int:
        return 2 + max_length * (key_bound + value_bound + 2)

    def _field_name_size(self, name: str) -> int:
        # Field names are written without escaping; at most 4 UTF-8 bytes per
        # code point, plus the surrounding quotes.
        return 2 + 4 * len(name)

    def _tag_value_bound(self, tag: str | int) -> int:
        if isinstance(tag, str):
            return _json_concrete_str_size(tag)
        return len(str(tag))

    def _plain_object(
        self, fields: tuple[Field, ...], field_bounds: tuple[int, ...]
    ) -> int:
        total = 2
        for field, field_bound in zip(fields, field_bounds):
            total += self._field_name_size(field.encode_name) + field_bound + 2
        return total

    def _struct_object(self, t: StructType, field_bounds: tuple[int, ...]) -> int:
        total = 2
        if t.tag is not None:
            tag_field = t.tag_field
            if tag_field is None:  # pragma: no cover - always set with a tag
                self._fail(t, "tagged struct is missing a tag field name")
            total += self._field_name_size(tag_field) + self._tag_value_bound(t.tag) + 2
        for field, field_bound in zip(t.fields, field_bounds):
            total += self._field_name_size(field.encode_name) + field_bound + 2
        return total

    def bound_key(self, t: Type) -> int:
        # Non-string JSON keys are rendered as strings; numeric keys gain quotes.
        if isinstance(t, Metadata):
            return self.bound_key(t.type)
        if isinstance(t, UnionType):
            return max(self.bound_key(st) for st in t.types)
        if isinstance(t, IntType):
            return self.bound(t) + 2
        if isinstance(t, FloatType):
            return self.FLOAT_KEY_SIZE
        if isinstance(t, EnumType) and all(
            isinstance(member.value, int) for member in t.cls
        ):
            return self.bound(t) + 2
        if isinstance(t, LiteralType):
            return max(self._concrete_key_value(value) for value in t.values)
        return self.bound(t)

    def _concrete_key_value(self, value: Any) -> int:
        if isinstance(value, int) and not isinstance(value, bool):
            return len(str(value)) + 2
        return self._concrete(value)


class _MsgpackSizeBounder(_EncodedSizeBounder):
    codec = "MessagePack"
    NONE_SIZE = 1  # nil
    BOOL_SIZE = 1
    INT_SIZE = 9  # int64/uint64, the largest encodable integers
    FLOAT_SIZE = 9  # float64
    DATE_SIZE = 11  # fixstr + 10 bytes
    TIME_SIZE = 22  # fixstr + at most 21 bytes
    NAIVE_DATETIME_SIZE = 27  # fixstr + at most 26 bytes
    AWARE_DATETIME_SIZE = 15  # timestamp 96 ext
    TIMEDELTA_SIZE = 27  # fixstr + at most 26 bytes

    def __init__(self, *, uuid_format: str, decimal_format: Any) -> None:
        if uuid_format not in ("canonical", "hex", "bytes"):
            raise ValueError("uuid_format must be 'canonical', 'hex' or 'bytes'")
        super().__init__(uuid_format=uuid_format, decimal_format=decimal_format)

    def int_bound(self, t: IntType) -> int:
        # Values outside the 64-bit range can't be MessagePack-encoded at all.
        return self.INT_SIZE

    def float_bound(self, t: FloatType) -> int:
        return self.FLOAT_SIZE

    def str_bound(self, t: StrType) -> int:
        max_bytes = 4 * self._require_max_length(t)
        return _mp_str_header_size(max_bytes) + max_bytes

    def bytes_bound(self, t: BytesType | ByteArrayType | MemoryViewType) -> int:
        max_length = self._require_max_length(t)
        return _mp_bin_header_size(max_length) + max_length

    def datetime_bound(self, t: DateTimeType) -> int:
        if t.tz is True:
            return self.AWARE_DATETIME_SIZE
        return max(self.NAIVE_DATETIME_SIZE, self.AWARE_DATETIME_SIZE)

    def time_bound(self, t: TimeType) -> int:
        return self.TIME_SIZE

    def date_bound(self, t: DateType) -> int:
        return self.DATE_SIZE

    def timedelta_bound(self, t: TimeDeltaType) -> int:
        return self.TIMEDELTA_SIZE

    def uuid_bound(self, t: UUIDType) -> int:
        if self.uuid_format == "bytes":
            return _mp_bin_header_size(16) + 16
        max_bytes = 36 if self.uuid_format == "canonical" else 32
        return _mp_str_header_size(max_bytes) + max_bytes

    def decimal_bound(self, t: DecimalType) -> int:
        if self.decimal_format == "number":
            return self.FLOAT_SIZE
        if callable(self.decimal_format):
            self._fail(
                t,
                "a callable `decimal_format` may produce output of arbitrary size",
            )
        self._fail(t, "decimal strings have no length limit")

    def ext_bound(self, t: ExtType) -> int:
        self._fail(
            t,
            "`msgspec.msgpack.Ext` carries an opaque data buffer of "
            "unconstrained length",
        )

    def _concrete(self, value: Any) -> int:
        if value is None:
            return self.NONE_SIZE
        if isinstance(value, bool):
            return self.BOOL_SIZE
        if isinstance(value, int):
            return _mp_int_size(value)
        if isinstance(value, str):
            return _mp_concrete_str_size(value)
        raise UnboundedTypeError(  # pragma: no cover - guarded by type_info
            f"unsupported literal or enum value {value!r}"
        )

    def _collection(self, max_length: int, item_bound: int) -> int:
        return _mp_array_header_size(max_length) + max_length * item_bound

    def _fixed_array(self, bounds: tuple[int, ...]) -> int:
        return _mp_array_header_size(len(bounds)) + sum(bounds)

    def _mapping(self, max_length: int, key_bound: int, value_bound: int) -> int:
        return _mp_map_header_size(max_length) + max_length * (key_bound + value_bound)

    def _field_name_size(self, name: str) -> int:
        max_bytes = 4 * len(name)
        return _mp_str_header_size(max_bytes) + max_bytes

    def _tag_value_bound(self, tag: str | int) -> int:
        if isinstance(tag, str):
            return _mp_concrete_str_size(tag)
        return _mp_int_size(tag)

    def _plain_object(
        self, fields: tuple[Field, ...], field_bounds: tuple[int, ...]
    ) -> int:
        total = _mp_map_header_size(len(fields))
        for field, field_bound in zip(fields, field_bounds):
            total += self._field_name_size(field.encode_name) + field_bound
        return total

    def _struct_object(self, t: StructType, field_bounds: tuple[int, ...]) -> int:
        count = len(t.fields) + (1 if t.tag is not None else 0)
        total = _mp_map_header_size(count)
        if t.tag is not None:
            tag_field = t.tag_field
            if tag_field is None:  # pragma: no cover - always set with a tag
                self._fail(t, "tagged struct is missing a tag field name")
            total += self._field_name_size(tag_field) + self._tag_value_bound(t.tag)
        for field, field_bound in zip(t.fields, field_bounds):
            total += self._field_name_size(field.encode_name) + field_bound
        return total


def _coerce_type_info(type: Any) -> Type:
    if isinstance(type, Type):
        return type
    return type_info(type)


def max_json_encoded_size(
    type: Any,
    *,
    uuid_format: Literal["canonical", "hex"] = "canonical",
    decimal_format: str | Callable[[decimal.Decimal], Any] = "string",
) -> int:
    """Compute a safe upper bound on the JSON encoded size of a type.

    Given a type annotation (or an already built `Type` instance), return the
    maximum number of bytes that `msgspec.json.encode` could produce for any
    value that conforms to the type and its constraints. The result is a safe
    upper bound; the actual encoded size is usually smaller.

    Parameters
    ----------
    type: type or Type
        The type to bound, either as a type annotation or a `Type` instance
        produced by `type_info`/`multi_type_info`.
    uuid_format: str, optional
        The UUID encoding format, matching ``msgspec.json.Encoder``. Must be
        ``"canonical"`` (the default) or ``"hex"``.
    decimal_format: str or callable, optional
        The decimal encoding format, matching ``msgspec.json.Encoder``. Decimals
        have no statically bounded size, so only the default ``"string"``,
        ``"number"`` and callable variants are accepted for API symmetry; all
        of them make the bound undecidable and raise `UnboundedTypeError`.

    Returns
    -------
    size: int
        The upper bound on the JSON encoded size, in bytes.

    Raises
    ------
    UnboundedTypeError
        If the type contains a branch with no finite encoded-size limit, such
        as an unconstrained `str` or container, an unbounded JSON `int`, an
        `Any`/custom/raw type, a decimal, or a recursive type.

    Examples
    --------
    >>> from typing import Annotated
    >>> from msgspec import Meta
    >>> import msgspec.inspect as mi
    >>> mi.max_json_encoded_size(Annotated[str, Meta(max_length=8)])
    50
    >>> mi.max_json_encoded_size(Annotated[int, Meta(ge=0, le=999)])
    3
    """
    info = _coerce_type_info(type)
    return _JSONSizeBounder(
        uuid_format=uuid_format, decimal_format=decimal_format
    ).bound(info)


def max_msgpack_encoded_size(
    type: Any,
    *,
    uuid_format: Literal["canonical", "hex", "bytes"] = "canonical",
    decimal_format: str | Callable[[decimal.Decimal], Any] = "string",
) -> int:
    """Compute a safe upper bound on the MessagePack encoded size of a type.

    Given a type annotation (or an already built `Type` instance), return the
    maximum number of bytes that `msgspec.msgpack.encode` could produce for
    any value that conforms to the type and its constraints. The result is a
    safe upper bound; the actual encoded size is usually smaller.

    Parameters
    ----------
    type: type or Type
        The type to bound, either as a type annotation or a `Type` instance
        produced by `type_info`/`multi_type_info`.
    uuid_format: str, optional
        The UUID encoding format, matching ``msgspec.msgpack.Encoder``. Must
        be ``"canonical"`` (the default), ``"hex"`` or ``"bytes"``.
    decimal_format: str or callable, optional
        The decimal encoding format, matching ``msgspec.msgpack.Encoder``.
        With ``"number"`` decimals encode as a fixed-size 9-byte float64; the
        default ``"string"`` format and callables have no bounded size and
        raise `UnboundedTypeError`.

    Returns
    -------
    size: int
        The upper bound on the MessagePack encoded size, in bytes.

    Raises
    ------
    UnboundedTypeError
        If the type contains a branch with no finite encoded-size limit, such
        as an unconstrained `str` or container, an `Any`/custom/raw/ext type,
        a string-formatted decimal, or a recursive type.

    Examples
    --------
    >>> from typing import Annotated
    >>> from msgspec import Meta
    >>> import msgspec.inspect as mi
    >>> mi.max_msgpack_encoded_size(Annotated[str, Meta(max_length=8)])
    34
    >>> mi.max_msgpack_encoded_size(Annotated[int, Meta(ge=0, le=999)])
    9
    """
    info = _coerce_type_info(type)
    return _MsgpackSizeBounder(
        uuid_format=uuid_format, decimal_format=decimal_format
    ).bound(info)
