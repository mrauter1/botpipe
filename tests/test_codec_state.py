from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
from typing import Annotated, Any, ClassVar, Generic, TypeVar

import pytest
from pydantic import (
    BaseModel,
    ConfigDict,
    Field,
    Json,
    PlainSerializer,
    PrivateAttr,
    RootModel,
    Secret,
    SecretStr,
    computed_field,
    field_serializer,
    field_validator,
)

from botpipe import Policy, codec
from botpipe.artifacts import ArtifactHandle, ArtifactMap
from botpipe.models import Result, RunResult


class TransformingModel(BaseModel):
    calls: ClassVar[int] = 0
    post_init_calls: ClassVar[int] = 0
    value: str
    payload: Json[list[int]]

    @field_validator("value")
    @classmethod
    def transform(cls, value: str) -> str:
        cls.calls += 1
        return value + "!"

    def model_post_init(self, context):
        type(self).post_init_calls += 1


class Animal(BaseModel):
    name: str


class Cat(Animal):
    lives: int


class Envelope(BaseModel):
    model_config = ConfigDict(extra="allow")

    animal: Animal
    optional: int = Field(default=7, alias="wireOptional")


@dataclass(frozen=True, slots=True)
class FrozenState:
    post_init_calls: ClassVar[int] = 0
    value: int
    derived: int = field(init=False)

    def __post_init__(self):
        type(self).post_init_calls += 1
        object.__setattr__(self, "derived", self.value * 2)


@dataclass(init=False)
class ConstructedState:
    calls: ClassVar[int] = 0
    value: int

    def __init__(self, value):
        type(self).calls += 1
        self.value = value


def _default_items():
    DefaultedState.default_calls += 1
    return [3]


@dataclass
class DefaultedState:
    default_calls: ClassVar[int] = 0
    items: list[int] = field(default_factory=_default_items)


T = TypeVar("T")


class Box(BaseModel, Generic[T]):
    item: T


def test_root_model_restoration_can_be_snapshotted_again():
    class Root(RootModel[list[int]]):
        pass

    first = codec.encode(Root([1, 2]))
    restored = codec.decode(first)
    assert restored.root == [1, 2]
    assert vars(restored) == {"root": [1, 2]}
    assert codec.encode(restored) == first


def test_native_path_round_trip_uses_concrete_type_identity():
    value = Path("native/path.txt")
    assert codec.decode(codec.encode(value)) == value

    class DerivedPath(type(value)):
        pass

    with pytest.raises(TypeError, match="unsupported durable value"):
        codec.encode(DerivedPath("derived/path.txt"))


def test_optional_generic_secret_contract_is_rejected_even_when_empty():
    class Credentials(BaseModel):
        token: Secret[str] | None = None

    with pytest.raises(TypeError, match="secret"):
        codec.encode(Credentials())


def test_model_state_round_trip_does_not_revalidate_and_preserves_json():
    TransformingModel.calls = 0
    TransformingModel.post_init_calls = 0
    original = TransformingModel(value="kept", payload="[1,2,3]")

    restored = codec.decode(codec.encode(original))

    assert TransformingModel.calls == 1
    assert TransformingModel.post_init_calls == 1
    assert restored.value == "kept!"
    assert restored.payload == [1, 2, 3]
    assert restored.model_fields_set == {"value", "payload"}


def test_model_state_preserves_concrete_nested_type_alias_state_and_extras():
    original = Envelope(animal=Cat(name="Mochi", lives=9), bonus={"ok": True})

    encoded = codec.encode(original)
    restored = codec.decode(encoded)

    assert set(encoded["fields"]) == {"animal", "optional"}
    assert encoded["fields_set"] == ["animal", "bonus"]
    assert type(restored.animal) is Cat
    assert restored.optional == 7
    assert restored.model_fields_set == {"animal", "bonus"}
    assert restored.__pydantic_extra__ == {"bonus": {"ok": True}}


def test_frozen_slotted_dataclass_state_does_not_run_post_init():
    FrozenState.post_init_calls = 0
    original = FrozenState(4)

    restored = codec.decode(codec.encode(original))

    assert FrozenState.post_init_calls == 1
    assert restored.value == 4
    assert restored.derived == 8


def test_dataclass_restore_does_not_run_constructor_or_default_factory():
    ConstructedState.calls = 0
    constructed = ConstructedState(4)
    ConstructedState.calls = 0
    restored_constructed = codec.decode(codec.encode(constructed))
    assert restored_constructed.value == 4
    assert ConstructedState.calls == 0

    DefaultedState.default_calls = 0
    defaulted = DefaultedState()
    DefaultedState.default_calls = 0
    restored_defaulted = codec.decode(codec.encode(defaulted))
    assert restored_defaulted.items == [3]
    assert DefaultedState.default_calls == 0


def test_repository_dataclasses_and_generated_pydantic_generics_round_trip():
    values = [
        Policy(model="small"),
        Result(value=3, artifacts=ArtifactMap()),
        RunResult(run_id="r", task_id="t", status="completed", value=4),
        Box[int](item=5),
    ]

    for value in values:
        restored = codec.decode(codec.encode(value))
        assert type(restored) is type(value)
        assert restored == value


def test_register_annotation_recovers_generated_types_in_a_fresh_registry():
    annotation = list[Box[int]]
    original = Box[int](item=5)
    record = codec.encode(original)
    reference = record["type"]
    codec._TYPES.pop(reference)

    codec.register_annotation(annotation)

    assert codec.decode(record) == original


def test_encoded_field_reads_versioned_state_without_resolving_the_type():
    record = codec.encode(Result(value=Cat(name="A", lives=8), artifacts=ArtifactMap()))

    encoded = codec.encoded_field(record, "value")

    assert encoded["$botpipe"] == "model"
    assert encoded["type"].endswith(":Cat")


class SerializedModel(BaseModel):
    value: str

    @field_serializer("value")
    def redact(self, value):
        return "redacted"


class ExcludedModel(BaseModel):
    visible: str
    hidden: str = Field(exclude=True)


class PrivateModel(BaseModel):
    value: str
    _memo: str = PrivateAttr(default="cache")


class SecretModel(BaseModel):
    password: SecretStr


class ComputedModel(BaseModel):
    value: int

    @computed_field
    @property
    def doubled(self) -> int:
        return self.value * 2


class NestedSerializedModel(BaseModel):
    values: list[Annotated[int, PlainSerializer(lambda value: value + 1)]]


class AnyModel(BaseModel):
    value: Any


@dataclass
class CacheState:
    value: int


@pytest.mark.parametrize(
    ("value", "message"),
    [
        (SerializedModel(value="x"), "custom serializers"),
        (ExcludedModel(visible="x", hidden="y"), "excluded Pydantic fields"),
        (PrivateModel(value="x"), "private attributes"),
        (SecretModel(password="secret"), "secret fields"),
        (ComputedModel(value=1), "custom serializers"),
        (NestedSerializedModel(values=[1]), "custom serializers"),
        (AnyModel(value=SecretStr("secret")), "secret values"),
    ],
)
def test_hidden_or_custom_model_state_is_rejected(value, message):
    with pytest.raises(TypeError, match=message):
        codec.encode({"nested": value})


def test_cached_and_cyclic_state_is_rejected_with_a_field_path():
    cached = CacheState(1)
    cached.cache = "derived"
    with pytest.raises(TypeError, match=r"\$: dataclass has cached or unknown state"):
        codec.encode(cached)

    cycle = []
    cycle.append({"again": cycle})
    with pytest.raises(TypeError, match=r"\$\[0\]\.again: cycles"):
        codec.encode(cycle)


def test_missing_unknown_version_and_corrupt_state_are_rejected():
    incomplete = {
        "$botpipe": "model",
        "type": codec.type_name(Animal),
        "value": {"name": "old"},
    }
    with pytest.raises(TypeError, match="durable record is missing"):
        codec.decode(incomplete)

    record = codec.encode(Animal(name="new"))
    record["version"] = 2
    with pytest.raises(TypeError, match="unsupported model state version 2"):
        codec.decode(record)

    record = codec.encode(Animal(name="new"))
    record["fields"]["unknown"] = 1
    with pytest.raises(TypeError, match="recorded fields do not match"):
        codec.decode(record)

    record = codec.encode(Animal(name="new"))
    record["extra"] = {}
    with pytest.raises(TypeError, match="does not allow extra fields"):
        codec.decode(record)

    record = codec.encode(Envelope(animal=Animal(name="new"), bonus=1))
    record["extra"]["animal"] = record["fields"]["animal"]
    with pytest.raises(TypeError, match="duplicates declared fields"):
        codec.verify_contracts(record)


def test_decode_rejects_wrong_type_category_before_hydration():
    record = codec.encode(Animal(name="new"))
    record["type"] = codec.type_name(FrozenState)
    with pytest.raises(TypeError, match="storage contract"):
        codec.decode(record)


def test_decode_rejects_values_outside_the_encoded_language():
    with pytest.raises(TypeError, match="unsupported encoded value object"):
        codec.decode(object())
    with pytest.raises(TypeError, match="untagged durable mapping"):
        codec.decode({"value": 1})


def test_decode_preflights_later_shapes_before_hydrating_earlier_values(
    monkeypatch, tmp_path
):
    handle = ArtifactHandle(
        name="report",
        path=tmp_path / "report.txt",
        source_path=tmp_path / "source.txt",
        kind="text",
        digest="abc",
    )
    encoded_handle = codec.encode(handle)
    calls = 0
    original = ArtifactHandle.from_record.__func__

    def counted(cls, record):
        nonlocal calls
        calls += 1
        return original(cls, record)

    monkeypatch.setattr(ArtifactHandle, "from_record", classmethod(counted))
    malformed = [encoded_handle, {"$botpipe": "bytes", "value": "not base64"}]

    with pytest.raises(TypeError, match="invalid base64"):
        codec.decode(malformed)
    assert calls == 0


def test_repeated_contract_metadata_does_not_consume_payload_limit(monkeypatch):
    monkeypatch.setattr(codec, "_MAX_VALUES", 30)
    values = [Animal(name=str(index)) for index in range(12)]

    encoded = codec.encode(values)
    restored = codec.decode(encoded)

    assert restored == values


def test_dataclass_descriptors_are_rejected_without_invoking_them():
    calls = []

    class Descriptor:
        def __get__(self, instance, owner=None):
            if instance is None:
                return self
            calls.append("get")
            return instance.__dict__["value"]

        def __set__(self, instance, value):
            calls.append("set")
            instance.__dict__["value"] = value

    @dataclass
    class DescriptorState:
        value: int = Descriptor()

    original = DescriptorState(1)
    calls.clear()
    with pytest.raises(TypeError, match="field descriptors are not durable"):
        codec.encode(original)
    assert calls == []

    record = codec.encode(CacheState(1))
    record["type"] = codec.type_name(DescriptorState)
    with pytest.raises(TypeError, match="field descriptors are not durable"):
        codec.decode(record)
    assert calls == []


def test_dataclasses_with_unrepresented_native_state_are_rejected():
    @dataclass
    class NativeState(list):
        value: int

    state = NativeState(1)
    state.append("hidden")

    with pytest.raises(TypeError, match="custom or native __new__"):
        codec.encode(state)


def test_artifact_handle_schema_is_bounded_plain_json():
    handle = ArtifactHandle(
        name="report",
        path=Path("/snapshots/report.json"),
        source_path=Path("/workspace/report.json"),
        kind="json",
        digest="abc",
        schema={"value": float("nan")},
    )
    with pytest.raises(TypeError, match="non-finite floats"):
        codec.encode(handle)

    cycle = {}
    cycle["self"] = cycle
    object.__setattr__(handle, "schema", cycle)
    with pytest.raises(TypeError, match="cycles are not supported"):
        codec.encode(handle)

    artifacts = ArtifactMap()
    artifacts._handles["again"] = artifacts
    with pytest.raises(TypeError, match="cycles are not supported"):
        codec.encode(artifacts)
