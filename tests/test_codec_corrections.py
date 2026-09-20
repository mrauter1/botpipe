from __future__ import annotations

import json
import subprocess
import sys
from dataclasses import dataclass
from datetime import date, datetime, timedelta, timezone, tzinfo
from typing import Annotated
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

import pytest
from pydantic import BaseModel, TypeAdapter
from pydantic_core import core_schema

from botpipe import codec


class CoreSchemaRedacted(str):
    @classmethod
    def __get_pydantic_core_schema__(cls, source, handler):
        return core_schema.no_info_after_validator_function(
            cls,
            handler(str),
            serialization=core_schema.plain_serializer_function_ser_schema(
                lambda value: "[redacted]"
            ),
        )


class CoreSchemaRedactedModel(BaseModel):
    value: CoreSchemaRedacted


class PlainReferencedType:
    pass


class RedactingMetadata:
    def __get_pydantic_core_schema__(self, source, handler):
        schema = handler(source)
        schema["serialization"] = core_schema.plain_serializer_function_ser_schema(
            lambda value: "[redacted]"
        )
        return schema


RedactedText = Annotated[str, RedactingMetadata()]


@dataclass
class CoreSchemaRedactedDataclass:
    secret: str

    @classmethod
    def __get_pydantic_core_schema__(cls, source, handler):
        schema = handler(source)
        schema["serialization"] = core_schema.plain_serializer_function_ser_schema(
            lambda value: {"secret": "[redacted]"}
        )
        return schema


def test_core_schema_serializer_is_rejected_during_preflight_and_encoding():
    message = "custom serializers installed through core schemas"
    with pytest.raises(TypeError, match=message):
        codec.schema_for(CoreSchemaRedacted)
    with pytest.raises(TypeError, match=message):
        codec.preflight(CoreSchemaRedactedModel)
    with pytest.raises(TypeError, match=message):
        codec.schema_for(CoreSchemaRedactedModel)
    with pytest.raises(TypeError, match=message):
        codec.encode(CoreSchemaRedactedModel(value="secret"))


def test_compiled_annotation_and_dataclass_core_serializers_are_rejected():
    message = "custom serializers installed through core schemas"
    assert TypeAdapter(RedactedText).dump_python("raw secret") == "[redacted]"
    with pytest.raises(TypeError, match=message):
        codec.preflight(RedactedText)
    with pytest.raises(TypeError, match=message):
        codec.schema_for(RedactedText)

    value = CoreSchemaRedactedDataclass("raw secret")
    assert TypeAdapter(CoreSchemaRedactedDataclass).dump_python(value) == {
        "secret": "[redacted]"
    }
    with pytest.raises(TypeError, match=message):
        codec.preflight(CoreSchemaRedactedDataclass)
    with pytest.raises(TypeError, match=message):
        codec.encode(value)


def test_preflight_types_does_not_compile_unadapted_plain_classes():
    assert codec.preflight_types(PlainReferencedType) == (PlainReferencedType,)


def test_preflight_types_accepts_the_abstract_pydantic_model_base():
    assert codec.preflight_types(type[BaseModel]) == (BaseModel,)


def test_date_and_supported_datetime_state_round_trip_faithfully():
    named_offset = timezone(
        timedelta(hours=-3, seconds=-4, microseconds=-5), "Review clock"
    )
    values = [
        date(2024, 2, 29),
        datetime(2024, 11, 3, 1, 30, 45, 123456, fold=1),  # noqa: DTZ001
        datetime(
            2024,
            11,
            3,
            1,
            30,
            45,
            123456,
            tzinfo=named_offset,
            fold=1,
        ),
    ]

    for original in values:
        restored = codec.decode(codec.encode(original))
        assert type(restored) is type(original)
        assert restored == original
        if type(original) is datetime:
            assert restored.fold == original.fold
            assert restored.tzname() == original.tzname()
            assert restored.utcoffset() == original.utcoffset()
            assert restored.tzinfo is None or type(restored.tzinfo) is timezone


class ArbitraryTimezone(tzinfo):
    def utcoffset(self, dt):
        return timedelta(hours=2)

    def dst(self, dt):
        return timedelta(0)

    def tzname(self, dt):
        return "arbitrary"


def test_zoneinfo_datetime_timezone_is_rejected():
    try:
        zone = ZoneInfo("UTC")
    except ZoneInfoNotFoundError:
        pytest.skip("system timezone database has no UTC entry")
    unsupported = datetime(2024, 1, 1, tzinfo=zone)
    with pytest.raises(TypeError, match="datetime.timezone fixed offsets"):
        codec.encode(unsupported)


def test_arbitrary_datetime_timezone_is_rejected():
    unsupported = datetime(2024, 1, 1, tzinfo=ArbitraryTimezone())
    with pytest.raises(TypeError, match="datetime.timezone fixed offsets"):
        codec.encode(unsupported)


def test_postponed_dataclass_annotation_restores_generated_model_fresh_process(
    tmp_path,
):
    module = tmp_path / "portable_state.py"
    module.write_text(
        """\
from __future__ import annotations
from dataclasses import dataclass
from typing import Generic, TypeVar
from pydantic import BaseModel

T = TypeVar("T")

class Types:
    class Box(BaseModel, Generic[T]):
        item: T

    @dataclass
    class Payload:
        box: Box[int]
""",
        encoding="utf-8",
    )
    create = """
import sys
sys.path.insert(0, sys.argv[1])
from botpipe import codec
from portable_state import Types
print(codec.dumps(Types.Payload(Types.Box[int](item=7))))
"""
    encoded = subprocess.run(
        [sys.executable, "-c", create, str(tmp_path)],
        check=True,
        capture_output=True,
        text=True,
    ).stdout.strip()
    json.loads(encoded)

    resume = """
import json
import sys
sys.path.insert(0, sys.argv[1])
from botpipe import codec
from portable_state import Types
codec._TYPES.clear()
codec.preflight(Types.Payload)
restored = codec.decode(json.loads(sys.stdin.read()))
assert type(restored) is Types.Payload
assert type(restored.box) is Types.Box[int]
assert restored.box.item == 7
"""
    subprocess.run(
        [sys.executable, "-c", resume, str(tmp_path)],
        input=encoded,
        check=True,
        capture_output=True,
        text=True,
    )


def test_inherited_postponed_annotations_use_each_bases_module(tmp_path):
    (tmp_path / "base_state.py").write_text(
        """\
from __future__ import annotations
from dataclasses import dataclass
from typing import Generic, TypeVar
from pydantic import BaseModel

T = TypeVar("T")

class Box(BaseModel, Generic[T]):
    item: T

@dataclass
class Base:
    box: Box[int]
""",
        encoding="utf-8",
    )
    (tmp_path / "child_state.py").write_text(
        """\
from __future__ import annotations
from dataclasses import dataclass
from base_state import Base
from other_box import Box

@dataclass
class Child(Base):
    label: str
""",
        encoding="utf-8",
    )
    (tmp_path / "other_box.py").write_text(
        """\
from typing import Generic, TypeVar
from pydantic import BaseModel

T = TypeVar("T")

class Box(BaseModel, Generic[T]):
    wrong_item: T
""",
        encoding="utf-8",
    )
    create = """
import sys
sys.path.insert(0, sys.argv[1])
from botpipe import codec
from base_state import Box
from child_state import Child
print(codec.dumps(Child(Box[int](item=7), "yes")))
"""
    encoded = subprocess.run(
        [sys.executable, "-c", create, str(tmp_path)],
        check=True,
        capture_output=True,
        text=True,
    ).stdout.strip()

    resume = """
import json
import sys
sys.path.insert(0, sys.argv[1])
from botpipe import codec
from base_state import Box
from child_state import Child
codec._TYPES.clear()
types = codec.preflight_types(Child)
assert Child in types
assert Box[int] in types
restored = codec.decode(json.loads(sys.stdin.read()))
assert type(restored) is Child
assert type(restored.box) is Box[int]
assert restored.box.item == 7
assert restored.label == "yes"
"""
    subprocess.run(
        [sys.executable, "-c", resume, str(tmp_path)],
        input=encoded,
        check=True,
        capture_output=True,
        text=True,
    )
