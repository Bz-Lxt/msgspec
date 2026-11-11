from __future__ import annotations

import datetime
import decimal
import enum
import random
import uuid
from dataclasses import dataclass
from typing import Annotated, Any, Literal, NamedTuple, TypedDict

import pytest

import msgspec
import msgspec.inspect as mi
from msgspec import Meta, Struct
from msgspec.inspect import (
    UnboundedTypeError,
    max_json_encoded_size,
    max_msgpack_encoded_size,
)

I = Annotated[int, Meta(ge=-1000, le=1000)]
I_SMALL = Annotated[int, Meta(ge=0, le=99)]
S = Annotated[str, Meta(max_length=8)]
S_SHORT = Annotated[str, Meta(max_length=3)]
B8 = Annotated[bytes, Meta(max_length=8)]
LIST_I = Annotated[list[I_SMALL], Meta(max_length=3)]


class StrEnum(enum.Enum):
    APPLE = "apple"
    BANANA = "banana"


class IntEnum(enum.IntEnum):
    ONE = 1
    THOUSAND = 1000


class Point(Struct):
    x: I
    y: I


class PointArray(Struct, array_like=True):
    x: I
    y: I


class TaggedPoint(Struct, tag="point", tag_field="kind"):
    x: I_SMALL
    y: I_SMALL


class IntTaggedPoint(Struct, tag=42):
    x: I_SMALL


class UntaggedPoint(Struct):
    x: I_SMALL
    y: I_SMALL


class UntaggedSingle(Struct):
    x: I_SMALL


class Nested(Struct):
    points: Annotated[list[Point], Meta(max_length=2)]
    label: S
    flag: bool = True


class Shared(Struct):
    first: Point
    second: Point


class TD(TypedDict):
    a: I_SMALL
    b: S_SHORT


class NT(NamedTuple):
    a: I_SMALL
    b: S_SHORT


@dataclass
class DC:
    a: I_SMALL
    b: S_SHORT


# ---------------------------------------------------------------------------
# Primitive bounds
# ---------------------------------------------------------------------------


def test_primitive_json_bounds():
    assert max_json_encoded_size(type(None)) == 4
    assert max_json_encoded_size(bool) == 5
    assert max_json_encoded_size(float) == 24
    assert max_json_encoded_size(datetime.datetime) == 34
    assert max_json_encoded_size(datetime.time) == 23
    assert max_json_encoded_size(datetime.date) == 12
    assert max_json_encoded_size(datetime.timedelta) == 28
    assert max_json_encoded_size(uuid.UUID) == 38


def test_primitive_msgpack_bounds():
    assert max_msgpack_encoded_size(type(None)) == 1
    assert max_msgpack_encoded_size(bool) == 1
    assert max_msgpack_encoded_size(int) == 9
    assert max_msgpack_encoded_size(float) == 9
    assert max_msgpack_encoded_size(datetime.date) == 11
    assert max_msgpack_encoded_size(datetime.time) == 22
    assert max_msgpack_encoded_size(datetime.timedelta) == 27
    assert max_msgpack_encoded_size(uuid.UUID) == 38


def test_datetime_msgpack_tz_variants():
    aware = Annotated[datetime.datetime, Meta(tz=True)]
    naive = Annotated[datetime.datetime, Meta(tz=False)]
    assert max_msgpack_encoded_size(aware) == 15
    assert max_msgpack_encoded_size(naive) == 27
    assert max_msgpack_encoded_size(datetime.datetime) == 27
    # JSON is a string either way
    assert max_json_encoded_size(aware) == 34
    assert max_json_encoded_size(naive) == 34


def test_bounded_string_and_bytes():
    assert max_json_encoded_size(S) == 2 + 6 * 8
    assert max_msgpack_encoded_size(S) == 2 + 4 * 8  # 32 bytes -> str8 header
    assert max_json_encoded_size(B8) == 2 + 4 * ((8 + 2) // 3)
    assert max_msgpack_encoded_size(B8) == 2 + 8
    assert max_json_encoded_size(Annotated[str, Meta(max_length=0)]) == 2
    assert max_msgpack_encoded_size(Annotated[str, Meta(max_length=0)]) == 1
    assert max_json_encoded_size(Annotated[bytearray, Meta(max_length=4)]) == 2 + 8
    assert max_json_encoded_size(Annotated[memoryview, Meta(max_length=4)]) == 2 + 8
    assert max_msgpack_encoded_size(Annotated[bytearray, Meta(max_length=4)]) == 6
    assert max_msgpack_encoded_size(Annotated[memoryview, Meta(max_length=4)]) == 6


def test_msgpack_string_header_tiers():
    # max_length counts code points; each code point can occupy 4 UTF-8 bytes,
    # so the header tier is derived from the worst-case byte length.
    assert max_msgpack_encoded_size(Annotated[str, Meta(max_length=7)]) == 1 + 28
    assert max_msgpack_encoded_size(Annotated[str, Meta(max_length=8)]) == 2 + 32
    assert max_msgpack_encoded_size(Annotated[str, Meta(max_length=63)]) == 2 + 252
    assert max_msgpack_encoded_size(Annotated[str, Meta(max_length=64)]) == 3 + 256


# ---------------------------------------------------------------------------
# Numeric constraints
# ---------------------------------------------------------------------------


def test_json_int_constraints():
    assert max_json_encoded_size(Annotated[int, Meta(ge=0, le=999)]) == 3
    assert max_json_encoded_size(Annotated[int, Meta(ge=-100, le=50)]) == 4
    assert max_json_encoded_size(Annotated[int, Meta(gt=0, lt=1000)]) == 3
    assert max_json_encoded_size(Annotated[int, Meta(gt=-1000, lt=0)]) == 4
    assert max_json_encoded_size(Annotated[int, Meta(ge=-(10**18), le=0)]) == 20
    assert max_json_encoded_size(Annotated[int, Meta(ge=0, le=0)]) == 1


def test_json_int_needs_both_endpoints():
    with pytest.raises(UnboundedTypeError, match="arbitrary precision"):
        max_json_encoded_size(int)
    with pytest.raises(UnboundedTypeError, match="arbitrary precision"):
        max_json_encoded_size(Annotated[int, Meta(le=10)])
    with pytest.raises(UnboundedTypeError, match="arbitrary precision"):
        max_json_encoded_size(Annotated[int, Meta(ge=0)])


def test_msgpack_int_always_bounded():
    assert max_msgpack_encoded_size(int) == 9
    assert max_msgpack_encoded_size(Annotated[int, Meta(ge=0, le=5)]) == 9


# ---------------------------------------------------------------------------
# Missing max_length constraints
# ---------------------------------------------------------------------------


@pytest.mark.parametrize(
    "typ",
    [
        str,
        bytes,
        bytearray,
        memoryview,
        list[int],
        set[int],
        frozenset[int],
        tuple[int, ...],
        dict[str, int],
        Annotated[list[str], Meta(min_length=1)],
    ],
)
def test_missing_max_length_is_unbounded(typ):
    with pytest.raises(UnboundedTypeError, match="max_length"):
        max_json_encoded_size(typ)
    with pytest.raises(UnboundedTypeError, match="max_length"):
        max_msgpack_encoded_size(typ)


# ---------------------------------------------------------------------------
# Containers, tuples and mappings
# ---------------------------------------------------------------------------


def test_bounded_collection_bounds():
    # JSON: 2 + n * (item + 1); I_SMALL allows up to two digits -> 2 + 3 * 3
    assert max_json_encoded_size(LIST_I) == 11
    # MessagePack: array header(3) = 1 + 3 * 9
    assert max_msgpack_encoded_size(LIST_I) == 28
    empty = Annotated[list[I_SMALL], Meta(max_length=0)]
    assert max_json_encoded_size(empty) == 2
    assert max_msgpack_encoded_size(empty) == 1


def test_set_and_vartuple_share_collection_semantics():
    set_t = Annotated[set[I_SMALL], Meta(max_length=2)]
    tuple_t = Annotated[tuple[I_SMALL, ...], Meta(max_length=2)]
    assert max_json_encoded_size(set_t) == max_json_encoded_size(tuple_t)
    assert max_msgpack_encoded_size(set_t) == max_msgpack_encoded_size(tuple_t)
    assert max_json_encoded_size(set_t) == 2 + 2 * (2 + 1)


def test_fixed_tuple_bounds():
    typ = tuple[I_SMALL, bool, S_SHORT]
    # JSON: sum(2, 5, 20) + 3 separators + 2 brackets
    assert max_json_encoded_size(typ) == 27 + 3 + 1
    # MessagePack: fixarray header + 9 + 1 + str(12) -> 1 + 10 + 13
    assert max_msgpack_encoded_size(typ) == 1 + 9 + 1 + 13
    assert max_json_encoded_size(tuple[()]) == 2
    assert max_msgpack_encoded_size(tuple[()]) == 1


def test_mapping_bounds_and_numeric_keys():
    typ = Annotated[dict[S_SHORT, I_SMALL], Meta(max_length=2)]
    # key JSON: 2 + 6 * 3 = 20; value: 2
    assert max_json_encoded_size(typ) == 2 + 2 * (20 + 2 + 2)
    # key msgpack: fixstr header + 12 = 13; value: 9; map header: 1
    assert max_msgpack_encoded_size(typ) == 1 + 2 * (13 + 9)

    int_key = Annotated[dict[I_SMALL, S_SHORT], Meta(max_length=2)]
    # JSON renders integer keys as quoted strings -> +2 over the value form
    assert max_json_encoded_size(int_key) == 2 + 2 * ((2 + 2) + 20 + 2)
    assert max_msgpack_encoded_size(int_key) == 1 + 2 * (9 + 13)


# ---------------------------------------------------------------------------
# Enums and literals
# ---------------------------------------------------------------------------


def test_enum_bounds():
    assert max_json_encoded_size(StrEnum) == len('"banana"')
    assert max_msgpack_encoded_size(StrEnum) == 1 + len("banana")
    assert max_json_encoded_size(IntEnum) == 4  # "1000"
    assert max_msgpack_encoded_size(IntEnum) == 3  # uint16


def test_literal_bounds():
    typ = Literal[1, "two", True, None]
    assert max_json_encoded_size(typ) == 5  # "two" with quotes
    assert max_msgpack_encoded_size(typ) == 4  # fixstr "two"
    assert max_json_encoded_size(Literal[True, False]) == 5
    assert max_msgpack_encoded_size(Literal[True, False]) == 1


# ---------------------------------------------------------------------------
# Unions
# ---------------------------------------------------------------------------


def test_union_takes_max_branch():
    typ = I_SMALL | None
    assert max_json_encoded_size(typ) == max(2, 4)
    assert max_msgpack_encoded_size(typ) == max(9, 1)
    # Optional inside a container still yields a finite bound
    wrapped = Annotated[list[I_SMALL | None], Meta(max_length=2)]
    assert max_json_encoded_size(wrapped) == 2 + 2 * (4 + 1)


# ---------------------------------------------------------------------------
# Structs, TypedDicts, dataclasses, NamedTuples
# ---------------------------------------------------------------------------


def test_struct_object_and_array_bounds():
    # int bound for I is 5; field names are 1 code point -> 2 + 4 bytes in JSON
    assert max_json_encoded_size(Point) == 2 + 2 * (6 + 5 + 2)
    # MessagePack name worst case is 4 UTF-8 bytes + fixstr header -> 5 each
    assert max_msgpack_encoded_size(Point) == 1 + 2 * (5 + 9)
    # Array-like: JSON [..] with two values; msgpack fixarray + two ints
    assert max_json_encoded_size(PointArray) == 5 + 5 + 2 + 1
    assert max_msgpack_encoded_size(PointArray) == 1 + 9 + 9


def test_tagged_struct_includes_tag_overhead():
    json_plain = max_json_encoded_size(UntaggedPoint)
    json_tagged = max_json_encoded_size(TaggedPoint)
    # Extra JSON overhead: "kind":"point", -> name(18) + value(7) + 2
    assert json_tagged - json_plain == 18 + 7 + 2

    mp_plain = max_msgpack_encoded_size(UntaggedPoint)
    mp_tagged = max_msgpack_encoded_size(TaggedPoint)
    # Both maps stay in the fixmap tier; extra cost is name str(17) + value(6)
    assert mp_tagged - mp_plain == 17 + 6

    # Integer tag: default tag field is "type" (4 cp), one field "x"
    assert max_json_encoded_size(IntTaggedPoint) > max_json_encoded_size(UntaggedSingle)
    # fixmap(2) + "type" name(17) + int tag 42 (1) + "x" name(5) + int value(9)
    assert max_msgpack_encoded_size(IntTaggedPoint) == 1 + 17 + 1 + 5 + 9


def test_nested_and_shared_structs():
    nested_json = max_json_encoded_size(Nested)
    nested_mp = max_msgpack_encoded_size(Nested)
    assert isinstance(nested_json, int) and nested_json > 0
    assert isinstance(nested_mp, int) and nested_mp > 0
    # Shared acyclic references are memoized, not treated as recursion.
    # Field names "first" (5 cp) and "second" (6 cp) use the 4-byte/cp bound.
    point_json = max_json_encoded_size(Point)
    first_name = 2 + 4 * 5
    second_name = 2 + 4 * 6
    assert max_json_encoded_size(Shared) == (
        2 + (first_name + point_json + 2) + (second_name + point_json + 2)
    )


def test_typeddict_dataclass_namedtuple_bounds():
    # TypedDict / dataclass encode as objects, NamedTuple as an array
    td_json = max_json_encoded_size(TD)
    dc_json = max_json_encoded_size(DC)
    assert td_json == dc_json
    # NamedTuple: fixed array of I_SMALL (2) and S_SHORT (20)
    nt_json = max_json_encoded_size(NT)
    assert nt_json == 22 + 2 + 1
    assert max_msgpack_encoded_size(NT) == 1 + 9 + 13


# ---------------------------------------------------------------------------
# Undecidable types
# ---------------------------------------------------------------------------


@pytest.mark.parametrize(
    "typ",
    [
        Any,
        msgspec.Raw,
        msgspec.msgpack.Ext,
        decimal.Decimal,
    ],
)
def test_opaque_types_are_unbounded(typ):
    with pytest.raises(UnboundedTypeError):
        max_json_encoded_size(typ)
    with pytest.raises(UnboundedTypeError):
        max_msgpack_encoded_size(typ)


class Custom:
    def __init__(self, x):
        self.x = x


def test_custom_type_is_unbounded():
    with pytest.raises(UnboundedTypeError, match="enc_hook"):
        max_json_encoded_size(Custom)
    with pytest.raises(UnboundedTypeError, match="enc_hook"):
        max_msgpack_encoded_size(Custom)


def test_decimal_format_variants():
    for kwargs in ({}, {"decimal_format": "string"}, {"decimal_format": str}):
        with pytest.raises(UnboundedTypeError):
            max_json_encoded_size(decimal.Decimal, **kwargs)
        with pytest.raises(UnboundedTypeError):
            max_msgpack_encoded_size(decimal.Decimal, **kwargs)
    # JSON number form still serializes the full digit string
    with pytest.raises(UnboundedTypeError):
        max_json_encoded_size(decimal.Decimal, decimal_format="number")
    # MessagePack number form is a fixed-size float64
    assert max_msgpack_encoded_size(decimal.Decimal, decimal_format="number") == 9


def test_unbounded_branch_inside_structure_reports_error():
    typ = Annotated[
        list[
            Annotated[
                dict[Annotated[str, Meta(max_length=4)], Any],
                Meta(max_length=3),
            ]
        ],
        Meta(max_length=3),
    ]
    with pytest.raises(UnboundedTypeError, match="Any"):
        max_json_encoded_size(typ)

    class Box(Struct):
        payload: msgspec.Raw

    with pytest.raises(UnboundedTypeError, match="Raw"):
        max_msgpack_encoded_size(Box)


def test_unbounded_error_is_value_error():
    assert issubclass(UnboundedTypeError, ValueError)
    with pytest.raises(ValueError):
        max_json_encoded_size(str)


# ---------------------------------------------------------------------------
# Recursive types
# ---------------------------------------------------------------------------


class RecNode(Struct):
    children: Annotated[list["RecNode"], Meta(max_length=4)]


class RecMutA(Struct):
    b: "RecMutB | None"


class RecMutB(Struct):
    a: RecMutA | None


def test_direct_recursion_is_unbounded():
    # Even with max_length bounding width, nesting depth is unbounded
    with pytest.raises(UnboundedTypeError, match="recursive"):
        max_json_encoded_size(RecNode)
    with pytest.raises(UnboundedTypeError, match="recursive"):
        max_msgpack_encoded_size(RecNode)


def test_mutual_recursion_is_unbounded():
    with pytest.raises(UnboundedTypeError):
        max_json_encoded_size(RecMutA)
    with pytest.raises(UnboundedTypeError):
        max_msgpack_encoded_size(RecMutA)


# ---------------------------------------------------------------------------
# Encoding options
# ---------------------------------------------------------------------------


def test_uuid_format_options():
    assert max_json_encoded_size(uuid.UUID, uuid_format="canonical") == 38
    assert max_json_encoded_size(uuid.UUID, uuid_format="hex") == 34
    assert max_msgpack_encoded_size(uuid.UUID, uuid_format="canonical") == 38
    assert max_msgpack_encoded_size(uuid.UUID, uuid_format="hex") == 34
    assert max_msgpack_encoded_size(uuid.UUID, uuid_format="bytes") == 18


def test_invalid_format_options():
    with pytest.raises(ValueError):
        max_json_encoded_size(uuid.UUID, uuid_format="bytes")
    with pytest.raises(ValueError):
        max_msgpack_encoded_size(uuid.UUID, uuid_format="wat")


def test_accepts_built_type_info():
    info = mi.type_info(Point)
    assert isinstance(info, mi.StructType)
    assert max_json_encoded_size(info) == max_json_encoded_size(Point)
    assert max_msgpack_encoded_size(info) == max_msgpack_encoded_size(Point)
    # Metadata-wrapped inputs are unwrapped transparently
    wrapped = Annotated[Point, Meta(description="a point")]
    assert max_json_encoded_size(wrapped) == max_json_encoded_size(Point)


# ---------------------------------------------------------------------------
# Property-based validation: every generated conforming value must satisfy
# len(encode(value)) <= computed bound
# ---------------------------------------------------------------------------

ALPHABET = 'abc你好\U0001f600\x00\x01\n\t"\\\x1f z'


def _rand_str(rng: random.Random, max_length: int) -> str:
    return "".join(rng.choice(ALPHABET) for _ in range(rng.randint(0, max_length)))


def _rand_bytes(rng: random.Random, max_length: int) -> bytes:
    return bytes(rng.randrange(256) for _ in range(rng.randint(0, max_length)))


def _rand_datetime(rng: random.Random, tz):
    naive = datetime.datetime(
        rng.randint(1, 9999),
        rng.randint(1, 12),
        rng.randint(1, 28),
        rng.randint(0, 23),
        rng.randint(0, 59),
        rng.randint(0, 59),
        rng.randint(0, 999999),
    )
    if tz is False:
        return naive
    offset = datetime.timezone(datetime.timedelta(minutes=rng.randint(-839, 839)))
    aware = naive.replace(tzinfo=offset)
    if tz is True:
        return aware
    return rng.choice([naive, aware])


def _rand_time(rng: random.Random, tz):
    t = datetime.time(
        rng.randint(0, 23),
        rng.randint(0, 59),
        rng.randint(0, 59),
        rng.randint(0, 999999),
    )
    if tz is False:
        return t
    offset = datetime.timezone(datetime.timedelta(minutes=rng.randint(-839, 839)))
    ta = t.replace(tzinfo=offset)
    return ta if tz is True else rng.choice([t, ta])


def gen_value(t: mi.Type, rng: random.Random) -> Any:
    t = t.type if isinstance(t, mi.Metadata) else t
    if isinstance(t, mi.NoneType):
        return None
    if isinstance(t, mi.BoolType):
        return rng.choice([True, False])
    if isinstance(t, mi.IntType):
        lower, upper = t.ge, t.le
        if lower is None or upper is None:
            return rng.randint(-(10**12), 10**12)
        return rng.randint(lower, upper)
    if isinstance(t, mi.FloatType):
        return rng.choice(
            [
                rng.uniform(-1e6, 1e6),
                rng.uniform(-1e300, 1e300),
                0.0,
                -0.0,
                1.7976931348623157e308,
                5e-324,
                float("inf"),
                float("nan"),
            ]
        )
    if isinstance(t, mi.StrType):
        return _rand_str(rng, t.max_length)
    if isinstance(t, mi.BytesType):
        return _rand_bytes(rng, t.max_length)
    if isinstance(t, mi.ByteArrayType):
        return bytearray(_rand_bytes(rng, t.max_length))
    if isinstance(t, mi.MemoryViewType):
        return memoryview(_rand_bytes(rng, t.max_length))
    if isinstance(t, mi.DateTimeType):
        return _rand_datetime(rng, t.tz)
    if isinstance(t, mi.TimeType):
        return _rand_time(rng, t.tz)
    if isinstance(t, mi.DateType):
        return datetime.date(
            rng.randint(1, 9999), rng.randint(1, 12), rng.randint(1, 28)
        )
    if isinstance(t, mi.TimeDeltaType):
        return datetime.timedelta(
            days=rng.randint(-1000, 1000),
            seconds=rng.randint(0, 86399),
            microseconds=rng.randint(0, 999999),
        )
    if isinstance(t, mi.UUIDType):
        return uuid.UUID(int=rng.getrandbits(128))
    if isinstance(t, mi.EnumType):
        return rng.choice(list(t.cls))
    if isinstance(t, mi.LiteralType):
        return rng.choice(t.values)
    if isinstance(t, mi.UnionType):
        return gen_value(rng.choice(t.types), rng)
    if isinstance(t, mi.CollectionType):
        n = rng.randint(0, t.max_length)
        values = [gen_value(t.item_type, rng) for _ in range(n)]
        if isinstance(t, (mi.SetType, mi.FrozenSetType)):
            values = list(set(values))
            if len(values) > t.max_length:
                values = values[: t.max_length]
        if isinstance(t, mi.FrozenSetType):
            return frozenset(values)
        if isinstance(t, mi.SetType):
            return set(values)
        if isinstance(t, mi.VarTupleType):
            return tuple(values)
        return values
    if isinstance(t, mi.TupleType):
        return tuple(gen_value(st, rng) for st in t.item_types)
    if isinstance(t, (mi.DictType, mi.FrozenDictType)):
        n = rng.randint(0, t.max_length)
        out = {}
        for _ in range(n * 5):
            if len(out) >= n:
                break
            out[gen_value(t.key_type, rng)] = gen_value(t.value_type, rng)
        return out
    if isinstance(t, mi.StructType):
        kwargs = {f.name: gen_value(f.type, rng) for f in t.fields}
        return t.cls(**kwargs)
    if isinstance(t, mi.TypedDictType):
        return {f.encode_name: gen_value(f.type, rng) for f in t.fields}
    if isinstance(t, mi.DataclassType):
        return t.cls(**{f.name: gen_value(f.type, rng) for f in t.fields})
    if isinstance(t, mi.NamedTupleType):
        return t.cls(*(gen_value(f.type, rng) for f in t.fields))
    raise AssertionError(f"unsupported type in generator: {t!r}")  # pragma: no cover


FUZZ_TYPES = [
    type(None),
    bool,
    float,
    I,
    I_SMALL,
    S,
    S_SHORT,
    B8,
    Annotated[bytearray, Meta(max_length=6)],
    Annotated[memoryview, Meta(max_length=6)],
    datetime.datetime,
    Annotated[datetime.datetime, Meta(tz=True)],
    Annotated[datetime.datetime, Meta(tz=False)],
    datetime.time,
    datetime.date,
    datetime.timedelta,
    uuid.UUID,
    StrEnum,
    IntEnum,
    Literal[1, "two", True, None],
    LIST_I,
    Annotated[set[I_SMALL], Meta(max_length=3)],
    Annotated[frozenset[I_SMALL], Meta(max_length=3)],
    Annotated[tuple[S_SHORT, ...], Meta(max_length=3)],
    tuple[I_SMALL, bool, S_SHORT],
    tuple[()],
    Annotated[dict[S_SHORT, I_SMALL], Meta(max_length=3)],
    Annotated[dict[I_SMALL, S_SHORT], Meta(max_length=3)],
    Point,
    PointArray,
    TaggedPoint,
    IntTaggedPoint,
    Nested,
    Shared,
    TD,
    NT,
    DC,
    I_SMALL | None,
    Annotated[list[I_SMALL | None], Meta(max_length=3)],
]


@pytest.mark.parametrize("typ", FUZZ_TYPES)
def test_json_bound_holds_for_random_values(typ):
    bound = max_json_encoded_size(typ)
    encoder = msgspec.json.Encoder()
    rng = random.Random(1234)
    info = mi.type_info(typ)
    for _ in range(60):
        value = gen_value(info, rng)
        assert len(encoder.encode(value)) <= bound


@pytest.mark.parametrize("typ", FUZZ_TYPES)
def test_msgpack_bound_holds_for_random_values(typ):
    bound = max_msgpack_encoded_size(typ)
    encoder = msgspec.msgpack.Encoder()
    rng = random.Random(5678)
    info = mi.type_info(typ)
    for _ in range(60):
        value = gen_value(info, rng)
        assert len(encoder.encode(value)) <= bound


def test_uuid_option_bounds_hold_for_random_values():
    rng = random.Random(9090)
    for json_fmt in ("canonical", "hex"):
        bound = max_json_encoded_size(uuid.UUID, uuid_format=json_fmt)
        enc = msgspec.json.Encoder(uuid_format=json_fmt)
        for _ in range(20):
            value = uuid.UUID(int=rng.getrandbits(128))
            assert len(enc.encode(value)) <= bound
    for mp_fmt in ("canonical", "hex", "bytes"):
        bound = max_msgpack_encoded_size(uuid.UUID, uuid_format=mp_fmt)
        enc = msgspec.msgpack.Encoder(uuid_format=mp_fmt)
        for _ in range(20):
            value = uuid.UUID(int=rng.getrandbits(128))
            assert len(enc.encode(value)) <= bound


def test_msgpack_decimal_number_bound_holds():
    bound = max_msgpack_encoded_size(decimal.Decimal, decimal_format="number")
    enc = msgspec.msgpack.Encoder(decimal_format="number")
    for value in [
        decimal.Decimal("0"),
        decimal.Decimal("-1.234567890123456789"),
        decimal.Decimal("1e100"),
        decimal.Decimal("3.141592653589793238462643383279"),
    ]:
        assert len(enc.encode(value)) <= bound


# ---------------------------------------------------------------------------
# Extremal values: saturate every constraint simultaneously
# ---------------------------------------------------------------------------


def test_extremal_json_string_escaping():
    typ = Annotated[str, Meta(max_length=16)]
    bound = max_json_encoded_size(typ)
    # Every code point a control byte -> 6 JSON bytes each plus quotes
    control = "\x01" * 16
    assert len(msgspec.json.encode(control)) == 2 + 6 * 16 == bound
    # Astral symbols use 4 UTF-8 bytes and are never escaped
    astral = "\U0001f600" * 16
    assert len(msgspec.json.encode(astral)) == 2 + 4 * 16 <= bound
    # Short escapes
    short = "\n" * 16
    assert len(msgspec.json.encode(short)) == 2 + 2 * 16 <= bound


def test_extremal_bytes_and_base64():
    typ = Annotated[bytes, Meta(max_length=100)]
    payload = bytes(i % 256 for i in range(100))
    assert len(msgspec.json.encode(payload)) <= max_json_encoded_size(typ)
    assert len(msgspec.msgpack.encode(payload)) <= max_msgpack_encoded_size(typ)


def test_extremal_temporal_values():
    assert len(msgspec.json.encode(datetime.datetime.max)) <= max_json_encoded_size(
        datetime.datetime
    )
    assert len(msgspec.json.encode(datetime.time.max)) <= max_json_encoded_size(
        datetime.time
    )
    assert len(msgspec.json.encode(datetime.timedelta.max)) <= max_json_encoded_size(
        datetime.timedelta
    )
    assert len(msgspec.msgpack.encode(datetime.datetime.max)) <= (
        max_msgpack_encoded_size(datetime.datetime)
    )
    assert len(msgspec.msgpack.encode(datetime.timedelta.max)) <= (
        max_msgpack_encoded_size(datetime.timedelta)
    )


def test_extremal_struct_saturates_container():
    points = [Point(-1000, 1000) for _ in range(2)]
    value = Nested(points=points, label="\x01" * 8, flag=False)
    assert len(msgspec.json.encode(value)) <= max_json_encoded_size(Nested)
    assert len(msgspec.msgpack.encode(value)) <= max_msgpack_encoded_size(Nested)
