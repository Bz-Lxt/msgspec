import collections
import datetime
import decimal
import enum
import fractions
import json
import os
import pathlib
import subprocess
import sys
import uuid
from dataclasses import dataclass
from typing import (
    Annotated,
    Generic,
    List,
    Literal,
    NamedTuple,
    Optional,
    TypedDict,
    TypeVar,
    Union,
)

import pytest

import msgspec
from msgspec.wire import (
    WireFingerprintUndecidable,
    wire_canonical,
    wire_fingerprint,
)

T = TypeVar("T")


# Module-level types: string forward references cannot resolve classes nested
# inside function bodies, so all recursive types live here.


class Node(msgspec.Struct, Generic[T]):
    value: T
    next: "Node[T] | None" = None


class NodeAgain(msgspec.Struct, Generic[T]):
    value: T
    next: "NodeAgain[T] | None" = None


class Parent(msgspec.Struct):
    children: "list[Child]"


class Child(msgspec.Struct):
    parent: Parent | None = None


class Tree(TypedDict):
    name: str
    children: "list[Tree]"


@dataclass
class DNode:
    value: int
    child: "DNode | None" = None


class CustomThing:
    pass


class Inner(msgspec.Struct):
    custom_field: CustomThing


class Wrapper(msgspec.Struct):
    wrapper_field: Inner


class Cat(msgspec.Struct, tag="cat"):
    meow: str


class Dog(msgspec.Struct, tag="dog"):
    bark: str


# ---------------------------------------------------------------------------
# Basic properties
# ---------------------------------------------------------------------------


def test_fingerprint_format_and_determinism():
    fp = wire_fingerprint(int)
    assert fp.startswith("blake2b256:")
    digest = fp.split(":", 1)[1]
    assert len(digest) == 64
    int(digest, 16)
    assert wire_fingerprint(int) == fp
    assert wire_fingerprint(str) != fp


def test_equivalent_annotation_spellings():
    assert wire_fingerprint(list[int]) == wire_fingerprint(List[int])
    assert wire_fingerprint(Optional[int]) == wire_fingerprint(Union[int, None])
    assert wire_fingerprint(Optional[int]) == wire_fingerprint(int | None)
    assert wire_fingerprint(tuple[int, ...]) == wire_fingerprint(tuple[int, ...])


def test_equivalent_struct_declarations():
    class Point(msgspec.Struct):
        x: int
        y: str = "z"

    class PointAgain(msgspec.Struct):
        x: int
        y: str = "z"

    assert wire_fingerprint(Point) == wire_fingerprint(PointAgain)


def test_equivalent_dataclass_typeddict_namedtuple_enum():
    @dataclass
    class DC1:
        a: int
        b: str = "x"

    @dataclass
    class DC2:
        a: int
        b: str = "x"

    assert wire_fingerprint(DC1) == wire_fingerprint(DC2)

    class TD1(TypedDict):
        name: str
        score: int

    class TD2(TypedDict):
        name: str
        score: int

    assert wire_fingerprint(TD1) == wire_fingerprint(TD2)

    class NT1(NamedTuple):
        a: int
        b: str = "x"

    class NT2(NamedTuple):
        a: int
        b: str = "x"

    assert wire_fingerprint(NT1) == wire_fingerprint(NT2)

    class E1(enum.Enum):
        RED = "red"
        BLUE = "blue"

    class E2(enum.Enum):
        RED = "red"
        BLUE = "blue"

    assert wire_fingerprint(E1) == wire_fingerprint(E2)


# ---------------------------------------------------------------------------
# Union canonicalization
# ---------------------------------------------------------------------------


def test_union_reorder_primitives():
    assert wire_fingerprint(Union[int, str]) == wire_fingerprint(Union[str, int])
    assert wire_fingerprint(int | str | None) == wire_fingerprint(None | str | int)


def test_union_reorder_tagged_structs():
    assert wire_fingerprint(Union[Cat, Dog]) == wire_fingerprint(Union[Dog, Cat])


def test_union_dedup_and_nesting():
    assert wire_fingerprint(Union[int, str, int]) == wire_fingerprint(Union[str, int])
    assert wire_fingerprint(Union[Union[int, str], bool]) == wire_fingerprint(
        Union[int, str, bool]
    )


def test_union_member_change_detected():
    assert wire_fingerprint(Union[int, str]) != wire_fingerprint(Union[int, bool])


# ---------------------------------------------------------------------------
# Aspects that must change the fingerprint
# ---------------------------------------------------------------------------


def test_field_alias_changes_fingerprint():
    class Plain(msgspec.Struct):
        field_one: int

    class Renamed(msgspec.Struct):
        field_one: int = msgspec.field(name="fieldOne")

    assert wire_fingerprint(Plain) != wire_fingerprint(Renamed)

    class Camel(msgspec.Struct, rename="camel"):
        field_one: int

    assert wire_fingerprint(Plain) != wire_fingerprint(Camel)


def test_constraints_change_fingerprint():
    assert wire_fingerprint(int) != wire_fingerprint(Annotated[int, msgspec.Meta(ge=0)])
    assert wire_fingerprint(Annotated[int, msgspec.Meta(ge=0)]) != wire_fingerprint(
        Annotated[int, msgspec.Meta(ge=1)]
    )
    assert wire_fingerprint(str) != wire_fingerprint(
        Annotated[str, msgspec.Meta(pattern=r"^x")]
    )
    assert wire_fingerprint(list[int]) != wire_fingerprint(
        Annotated[list[int], msgspec.Meta(min_length=1)]
    )

    # Constraints on otherwise identical structs still differentiate them.
    class Box1(msgspec.Struct):
        n: Annotated[int, msgspec.Meta(ge=0)]

    class Box2(msgspec.Struct):
        n: Annotated[int, msgspec.Meta(ge=1)]

    assert wire_fingerprint(Box1) != wire_fingerprint(Box2)


def test_metadata_extra_does_not_change_fingerprint():
    # `extra` / `extra_json_schema` are documentation-only and never reach
    # the wire, so they must not perturb the wire fingerprint.
    base = wire_fingerprint(int)
    assert wire_fingerprint(Annotated[int, msgspec.Meta(extra={"foo": "bar"})]) == base
    assert (
        wire_fingerprint(
            Annotated[int, msgspec.Meta(extra_json_schema={"description": "x"})]
        )
        == base
    )


def test_struct_tag_changes_fingerprint():
    class Auto(msgspec.Struct, tag=True):
        x: int

    class Explicit(msgspec.Struct, tag="explicit"):
        x: int

    class OtherField(msgspec.Struct, tag=True, tag_field="kind"):
        x: int

    class Untagged(msgspec.Struct):
        x: int

    fingerprints = {wire_fingerprint(t) for t in (Auto, Explicit, OtherField, Untagged)}
    assert len(fingerprints) == 4


def test_omit_defaults_and_default_values_change_fingerprint():
    class EmitDefaults(msgspec.Struct):
        x: int = 1

    class OmitDefaults(msgspec.Struct, omit_defaults=True):
        x: int = 1

    assert wire_fingerprint(EmitDefaults) != wire_fingerprint(OmitDefaults)

    class OtherDefault(msgspec.Struct, omit_defaults=True):
        x: int = 2

    assert wire_fingerprint(OmitDefaults) != wire_fingerprint(OtherDefault)

    class WithFactory(msgspec.Struct):
        x: int = msgspec.field(default_factory=lambda: 1)

    class WithStatic(msgspec.Struct):
        x: int = 1

    assert wire_fingerprint(WithFactory) != wire_fingerprint(WithStatic)


def test_array_layout_changes_fingerprint():
    class AsObject(msgspec.Struct):
        x: int
        y: str = "z"

    class AsArray(msgspec.Struct, array_like=True):
        x: int
        y: str = "z"

    assert wire_fingerprint(AsObject) != wire_fingerprint(AsArray)

    # A named tuple is encoded as an array while a dataclass is an object.
    class PairNT(NamedTuple):
        x: int
        y: str

    @dataclass
    class PairDC:
        x: int
        y: str

    assert wire_fingerprint(PairNT) != wire_fingerprint(PairDC)


def test_collection_and_tuple_kinds_distinct():
    assert wire_fingerprint(list[int]) != wire_fingerprint(set[int])
    assert wire_fingerprint(set[int]) != wire_fingerprint(frozenset[int])
    assert wire_fingerprint(tuple[int, str]) != wire_fingerprint(tuple[int, ...])
    assert wire_fingerprint(dict[str, int]) != wire_fingerprint(list[int])


def test_literal_and_enum_sensitivity():
    assert wire_fingerprint(Literal["a", "b"]) == wire_fingerprint(Literal["b", "a"])
    assert wire_fingerprint(Literal["a", "b"]) != wire_fingerprint(Literal["a", "c"])

    class E1(enum.Enum):
        RED = "red"

    class E2(enum.Enum):
        RED = "green"

    assert wire_fingerprint(E1) != wire_fingerprint(E2)


# ---------------------------------------------------------------------------
# Recursive types (including recursive generics) must terminate
# ---------------------------------------------------------------------------


def test_recursive_generic_terminates_and_is_stable():
    fp = wire_fingerprint(Node[int])
    assert fp == wire_fingerprint(Node[int])
    # Different parameterizations describe different wire contracts.
    assert fp != wire_fingerprint(Node[str])

    doc = wire_canonical(Node[int])
    assert any("$ref" in json.dumps(node["shape"]) for node in doc["nodes"])


def test_equivalent_recursive_generics_fingerprint_equal():
    assert wire_fingerprint(Node[int]) == wire_fingerprint(NodeAgain[int])


def test_mutual_recursion_terminates():
    assert wire_fingerprint(Parent) == wire_fingerprint(Parent)
    doc = wire_canonical(Parent)
    names = {node["name"] for node in doc["nodes"]}
    assert {"Parent", "Child"} <= names


def test_recursive_typeddict_and_dataclass_terminate():
    assert wire_fingerprint(Tree) == wire_fingerprint(Tree)
    assert wire_fingerprint(DNode) == wire_fingerprint(DNode)


# ---------------------------------------------------------------------------
# Undecidable cases must be reported explicitly
# ---------------------------------------------------------------------------


def test_custom_type_is_undecidable():
    with pytest.raises(WireFingerprintUndecidable) as exc:
        wire_fingerprint(CustomThing)
    assert exc.value.typ is CustomThing
    assert exc.value.path == ()

    for unsupported in (
        collections.deque,
        pathlib.Path,
        fractions.Fraction,
    ):
        with pytest.raises(WireFingerprintUndecidable):
            wire_fingerprint(unsupported)


def test_undecidable_reports_field_path():
    with pytest.raises(WireFingerprintUndecidable) as exc:
        wire_fingerprint(Wrapper)
    assert exc.value.path == ("wrapper_field", "custom_field")


def test_ext_undecidable_for_json_but_describable_for_msgpack():
    with pytest.raises(WireFingerprintUndecidable):
        wire_fingerprint(msgspec.msgpack.Ext, protocol="json")
    # MessagePack supports Ext natively.
    assert wire_fingerprint(msgspec.msgpack.Ext, protocol="msgpack")


def test_callable_decimal_format_undecidable_only_with_decimal():
    hook = lambda d: float(d)  # noqa: E731
    other_hook = lambda d: int(d)  # noqa: E731
    with pytest.raises(WireFingerprintUndecidable):
        wire_fingerprint(decimal.Decimal, decimal_format=hook)
    # The hook never runs for a tree containing no Decimal, so the rest of
    # the tree remains describable and two distinct hook callables make no
    # difference to its wire structure.
    assert wire_fingerprint(int, decimal_format=hook) == wire_fingerprint(
        int, decimal_format=other_hook
    )


def test_unrepresentable_default_value_undecidable():
    class Weird:
        pass

    class Holder(msgspec.Struct):
        weird: Weird = Weird()  # type: ignore[assignment]

    with pytest.raises(WireFingerprintUndecidable):
        wire_fingerprint(Holder)


# ---------------------------------------------------------------------------
# Protocol and encoding option sensitivity
# ---------------------------------------------------------------------------


def test_protocols_always_distinguished():
    for typ in (int, str, bytes, datetime.datetime, uuid.UUID, msgspec.Raw):
        assert wire_fingerprint(typ, protocol="json") != wire_fingerprint(
            typ, protocol="msgpack"
        )


def test_uuid_and_decimal_format_options():
    assert wire_fingerprint(uuid.UUID) != wire_fingerprint(uuid.UUID, uuid_format="hex")
    assert wire_fingerprint(uuid.UUID, protocol="msgpack") != wire_fingerprint(
        uuid.UUID, protocol="msgpack", uuid_format="bytes"
    )
    assert wire_fingerprint(decimal.Decimal) != wire_fingerprint(
        decimal.Decimal, decimal_format="number"
    )


def test_invalid_options_rejected():
    with pytest.raises(ValueError):
        wire_fingerprint(int, protocol="yaml")
    with pytest.raises(ValueError):
        wire_fingerprint(uuid.UUID, uuid_format="bytes")
    with pytest.raises(ValueError):
        wire_fingerprint(decimal.Decimal, decimal_format="banana")


def test_encoder_instance_supplies_options():
    encoder = msgspec.msgpack.Encoder(uuid_format="bytes")
    assert wire_fingerprint(uuid.UUID, encoder=encoder) == wire_fingerprint(
        uuid.UUID, protocol="msgpack", uuid_format="bytes"
    )

    json_encoder = msgspec.json.Encoder(uuid_format="hex")
    assert wire_fingerprint(uuid.UUID, encoder=json_encoder) == wire_fingerprint(
        uuid.UUID, protocol="json", uuid_format="hex"
    )

    with pytest.raises(ValueError):
        wire_fingerprint(int, encoder=encoder, protocol="json")
    with pytest.raises(TypeError):
        wire_fingerprint(int, encoder=object())


# ---------------------------------------------------------------------------
# Canonical document
# ---------------------------------------------------------------------------


def test_canonical_document_is_stable_and_jsonable():
    class Point(msgspec.Struct):
        x: int
        y: str = "z"

    doc = wire_canonical(Point)
    # Must round-trip through plain JSON.
    encoded = json.dumps(doc)
    assert json.loads(encoded) == doc
    assert doc["version"] == 1
    assert doc["algorithm"] == "blake2b256"
    assert doc["fingerprint"] in wire_fingerprint(Point)
    assert wire_canonical(Point) == doc


# ---------------------------------------------------------------------------
# Cross-process stability
# ---------------------------------------------------------------------------


_SUBPROCESS_SCRIPT = """
import json
from typing import Generic, TypeVar, TypedDict, Union
import msgspec
from msgspec.wire import wire_fingerprint

T = TypeVar("T")

class Point(msgspec.Struct):
    x: int
    y: str = "z"

class Cat(msgspec.Struct, tag="cat"):
    meow: str

class Dog(msgspec.Struct, tag="dog"):
    bark: str

class Node(msgspec.Struct, Generic[T]):
    value: T
    next: "Node[T] | None" = None

class Tree(TypedDict):
    name: str
    children: "list[Tree]"

result = {
    "point": wire_fingerprint(Point),
    "union": wire_fingerprint(Union[Cat, Dog]),
    "node_int": wire_fingerprint(Node[int]),
    "tree": wire_fingerprint(Tree),
    "point_mp": wire_fingerprint(Point, protocol="msgpack"),
}
print(json.dumps(result, sort_keys=True))
"""


def test_fingerprint_stable_across_processes():
    class Point(msgspec.Struct):
        x: int
        y: str = "z"

    expected = {
        "point": wire_fingerprint(Point),
        "union": wire_fingerprint(Union[Cat, Dog]),
        "node_int": wire_fingerprint(Node[int]),
        "tree": wire_fingerprint(Tree),
        "point_mp": wire_fingerprint(Point, protocol="msgpack"),
    }

    # Run twice with different hash seeds to prove PYTHONHASHSEED independence.
    for seed in ("1", "1234567"):
        env = dict(os.environ, PYTHONHASHSEED=seed)
        proc = subprocess.run(
            [sys.executable, "-c", _SUBPROCESS_SCRIPT],
            capture_output=True,
            text=True,
            env=env,
            check=True,
        )
        assert json.loads(proc.stdout) == expected
