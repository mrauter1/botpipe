"""Flag pseudo-member state and policy-aware cache restoration."""

from __future__ import annotations

import os
import subprocess
import sys
from enum import KEEP, STRICT, Flag, IntFlag
from pathlib import Path

import pytest

from botpipe import codec


def _run(script: Path, input: str | None = None):
    env = {
        **os.environ,
        "PYTHONPATH": os.pathsep.join(
            (str(Path(__file__).resolve().parents[1]), os.environ.get("PYTHONPATH", ""))
        ),
    }
    return subprocess.run(
        [sys.executable, str(script)],
        cwd=script.parent,
        env=env,
        input=input,
        capture_output=True,
        text=True,
        check=False,
    )


def _pseudo(cls, raw, name):
    member = (
        object.__new__(cls) if cls._member_type_ is object else int.__new__(cls, raw)
    )
    object.__setattr__(member, "_value_", raw)
    object.__setattr__(member, "_name_", name)
    return member


class Bits(Flag):
    A = 1
    B = 2


class IntBits(IntFlag):
    A = 1
    B = 2


@pytest.mark.parametrize(
    ("boundary", "constructor_check"),
    [
        (
            "STRICT",
            "\ntry:\n    Boundary(5)\nexcept ValueError:\n    pass\nelse:\n    raise AssertionError('STRICT accepted unknown bits')\n",
        ),
        ("CONFORM", "\nassert Boundary(5) is Boundary.A\n"),
        ("EJECT", "\nassert type(Boundary(5)) is int and Boundary(5) == 5\n"),
    ],
)
def test_boundary_edit_restores_history_without_changing_new_construction(
    tmp_path, boundary, constructor_check
):
    module = tmp_path / "state.py"
    module.write_text(
        "from enum import Flag, KEEP\n"
        "class Boundary(Flag, boundary=KEEP):\n"
        "    A = 1\n"
        "    B = 2\n"
    )
    create = tmp_path / "create.py"
    create.write_text(
        "from botpipe import codec\n"
        "from state import Boundary\n"
        "print(codec.dumps(Boundary(5)))\n"
    )
    recorded = _run(create)
    assert recorded.returncode == 0, recorded.stderr

    module.write_text(
        f"from enum import Flag, {boundary}\n"
        f"class Boundary(Flag, boundary={boundary}):\n"
        "    A = 1\n"
        "    B = 2\n"
    )
    resume = tmp_path / "resume.py"
    resume.write_text(
        "import json, sys\n"
        "from botpipe import codec\n"
        "from state import Boundary\n"
        "value = codec.decode(json.loads(sys.stdin.read()))\n"
        "assert type(value) is Boundary\n"
        "assert value.value == 5 and value.name == 'A|4'\n"
        "assert 5 not in Boundary._value2member_map_\n" + constructor_check
    )
    restored = _run(resume, input=recorded.stdout)
    assert restored.returncode == 0, restored.stderr


@pytest.mark.parametrize("cls", [Bits, IntBits])
@pytest.mark.parametrize("raw", [0, 3])
def test_normal_zero_and_composite_restoration_preserves_identity(cls, raw):
    value = cls(raw)
    encoded = codec.encode(value)
    cls._value2member_map_.pop(raw, None)

    restored = codec.decode(encoded)

    assert restored is cls(raw)


def test_composite_only_strict_admission_matches_stdlib_missing_rules():
    class CompositeOnly(Flag, boundary=STRICT):
        AB = 3
        CD = 12

    for raw in (1, 5):
        value = CompositeOnly(raw)
        assert value.name is None
        encoded = codec.encode(value)
        CompositeOnly._value2member_map_.pop(raw, None)
        assert codec.decode(encoded) is CompositeOnly(raw)

    historical = _pseudo(CompositeOnly, 7, "AB|4")
    encoded = codec.encode(historical)
    restored = codec.decode(encoded)
    assert restored.value == 7
    assert restored.name == "AB|4"
    assert 7 not in CompositeOnly._value2member_map_
    with pytest.raises(ValueError):
        CompositeOnly(7)


def test_negative_declarations_use_stdlib_range_and_normalization_rules():
    class StrictNegative(Flag, boundary=STRICT):
        NEGATIVE = -2
        A = 1

    historical = _pseudo(StrictNegative, -1, "historical")
    restored = codec.decode(codec.encode(historical))
    assert restored.value == -1
    assert restored.name == "historical"
    assert -1 not in StrictNegative._value2member_map_
    with pytest.raises(ValueError):
        StrictNegative(-1)

    from enum import CONFORM

    class ConformNegative(Flag, boundary=CONFORM):
        NEGATIVE = -2
        A = 1

    admitted = ConformNegative(3)
    encoded = codec.encode(admitted)
    ConformNegative._value2member_map_.pop(3)
    assert codec.decode(encoded) is ConformNegative(3)


def test_pseudo_members_with_application_dict_or_slot_state_are_rejected():
    class DictState(Flag):
        A = 1
        B = 2

    dict_value = DictState.A | DictState.B
    dict_value.application_note = "lost"
    with pytest.raises(TypeError, match="unsupported instance state"):
        codec.encode(dict_value)

    class SlotState(Flag):
        __slots__ = ("application_note",)
        A = 1
        B = 2

    slot_value = SlotState.A | SlotState.B
    slot_value.application_note = "lost"
    with pytest.raises(TypeError, match="unsupported instance state"):
        codec.encode(slot_value)

    class MissingState(Flag, boundary=KEEP):
        A = 1

        @classmethod
        def _missing_(cls, value):
            member = super()._missing_(value)
            member.application_note = "lost"
            return member

    with pytest.raises(TypeError, match="unsupported instance state"):
        codec.encode(MissingState(3))


def test_declared_members_remain_references_and_inverted_cache_is_disposable():
    class Bits(Flag):
        A = 1
        B = 2

    Bits.A.application_note = "member state"
    assert codec.decode(codec.encode(Bits.A)) is Bits.A

    composite = Bits.A | Bits.B
    composite._inverted_ = Bits(0)
    encoded = codec.encode(composite)
    assert codec.decode(encoded) is composite


@pytest.mark.parametrize("changed_field", ["name", "state"])
def test_changed_cached_pseudo_member_is_not_substituted_for_stored_state(
    changed_field,
):
    class Bits(Flag):
        A = 1
        B = 2

    cached = Bits.A | Bits.B
    encoded = codec.encode(cached)
    if changed_field == "name":
        object.__setattr__(cached, "_name_", "changed")
    else:
        cached.application_note = "changed"

    restored = codec.decode(encoded)

    assert restored is not cached
    assert restored.value == 3
    assert restored.name == "A|B"
    assert Bits._value2member_map_[3] is cached


@pytest.mark.parametrize("mismatch", ["raw", "type"])
def test_incompatible_cache_entries_are_ignored(mismatch):
    class LocalBits(Flag):
        A = 1
        B = 2

    encoded = codec.encode(LocalBits.A | LocalBits.B)
    if mismatch == "raw":
        incompatible = _pseudo(LocalBits, 4, "A|B")
    else:
        incompatible = object()
    LocalBits._value2member_map_[3] = incompatible

    restored = codec.decode(encoded)

    assert type(restored) is LocalBits
    assert restored.value == 3
    assert restored.name == "A|B"
    assert restored is not incompatible
    assert LocalBits._value2member_map_[3] is incompatible


def test_custom_missing_hook_is_not_called_to_decide_cache_insertion():
    calls = []

    class CustomMissing(Flag, boundary=KEEP):
        A = 1

        @classmethod
        def _missing_(cls, value):
            calls.append(value)
            return super()._missing_(value)

    encoded = codec.encode(_pseudo(CustomMissing, 3, "A|2"))
    restored = codec.decode(encoded)
    assert calls == []
    assert restored.value == 3
    assert 3 not in CustomMissing._value2member_map_


def test_custom_instance_setter_is_not_called_or_cached_through_restore():
    class CustomSetter(Flag):
        A = 1
        B = 2

    encoded = codec.encode(CustomSetter(3))
    CustomSetter._value2member_map_.pop(3)
    calls = []

    def custom_setattr(self, name, value):
        calls.append((name, value))
        if name == "_value_" and value == 3:
            raise RuntimeError("custom setter")
        object.__setattr__(self, name, value)

    CustomSetter.__setattr__ = custom_setattr
    restored = codec.decode(encoded)
    assert calls == []
    assert object.__getattribute__(restored, "_value_") == 3
    assert 3 not in CustomSetter._value2member_map_
    with pytest.raises(RuntimeError, match="custom setter"):
        CustomSetter(3)


@pytest.mark.parametrize("hook_name", ["__getattr__", "__getattribute__"])
def test_custom_instance_access_hook_is_not_called_or_cached_through_restore(
    hook_name,
):
    class CustomAccess(Flag):
        A = 1
        B = 2

    encoded = codec.encode(CustomAccess(3))
    CustomAccess._value2member_map_.pop(3)
    calls = []

    if hook_name == "__getattr__":

        def custom_access(self, name):
            calls.append(name)
            if name == "_value_":
                return 999
            raise AttributeError(name)

    else:

        def custom_access(self, name):
            if name == "_value_":
                try:
                    return object.__getattribute__(self, name)
                except AttributeError:
                    calls.append(name)
                    return 999
            return object.__getattribute__(self, name)

    setattr(CustomAccess, hook_name, custom_access)
    restored = codec.decode(encoded)
    assert calls == []
    assert object.__getattribute__(restored, "_value_") == 3
    assert 3 not in CustomAccess._value2member_map_

    constructed = CustomAccess(3)
    assert constructed.value == 999
    assert calls


def test_custom_iteration_and_numeric_hooks_are_not_called():
    iteration_calls = []

    class CustomIteration(Flag):
        A = 1
        B = 2

    def custom_iteration(cls, value):
        iteration_calls.append(value)
        yield from Flag._iter_member_by_value_.__func__(cls, value)

    CustomIteration._iter_member_ = classmethod(custom_iteration)
    iteration_record = codec.encode(_pseudo(CustomIteration, 3, "A|B"))
    restored = codec.decode(iteration_record)
    assert iteration_calls == []
    assert restored.name == "A|B"
    assert 3 not in CustomIteration._value2member_map_

    definition_calls = []

    class DefinitionOrder(Flag):
        B = 2
        A = 1

    def custom_by_value(cls, value):
        definition_calls.append(value)
        yield from Flag._iter_member_by_value_.__func__(cls, value)

    DefinitionOrder._iter_member_by_value_ = classmethod(custom_by_value)
    definition_record = codec.encode(_pseudo(DefinitionOrder, 3, "B|A"))
    restored = codec.decode(definition_record)
    assert definition_calls == []
    assert restored.name == "B|A"
    assert 3 not in DefinitionOrder._value2member_map_

    numeric_calls = []

    class CustomNumeric(Flag, boundary=KEEP):
        A = 1
        B = 2

    def custom_numeric(value):
        numeric_calls.append(value)
        return hex(value)

    CustomNumeric._numeric_repr_ = custom_numeric
    numeric_record = codec.encode(_pseudo(CustomNumeric, 5, "A|4"))
    restored = codec.decode(numeric_record)
    assert numeric_calls == []
    assert restored.name == "A|4"
    assert 5 not in CustomNumeric._value2member_map_

    known = _pseudo(CustomNumeric, 3, "A|B")
    known_record = codec.encode(known)
    CustomNumeric._value2member_map_.pop(3, None)
    restored = codec.decode(known_record)
    assert numeric_calls == []
    assert restored is CustomNumeric(3)
