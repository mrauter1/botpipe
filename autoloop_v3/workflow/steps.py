"""Workflow step and session declarations."""

from __future__ import annotations

from itertools import count
from typing import TYPE_CHECKING, Mapping, Sequence

from .prompts import PromptSpec

if TYPE_CHECKING:
    from .artifacts import Artifact


_STEP_COUNTER = count()
_SESSION_COUNTER = count()


class Session:
    """Session slot marker."""

    __slots__ = ("name", "_order")

    def __init__(self) -> None:
        self.name: str | None = None
        self._order = next(_SESSION_COUNTER)

    def bind_name(self, name: str) -> None:
        if self.name is None:
            self.name = name
        elif self.name != name:
            raise ValueError(f"session already named {self.name!r}; cannot rename to {name!r}")

    def __repr__(self) -> str:
        return f"Session(name={self.name!r})"


class Step:
    """Base step declaration."""

    kind = "step"

    def __init__(
        self,
        *,
        name: str,
        session: Session | None = None,
        requires: Sequence[Artifact] | None = None,
        produces: Mapping[str, Artifact] | None = None,
        log_artifacts: Sequence[Artifact] | None = None,
    ) -> None:
        self.name = name
        self.session = session
        self.requires = tuple(requires or ())
        self.produces = dict(produces or {})
        self.log_artifacts = tuple(log_artifacts or ())
        self._order = next(_STEP_COUNTER)
        for artifact_name, artifact in self.produces.items():
            artifact.bind_name(artifact_name)

    def __getattr__(self, item: str) -> Artifact:
        try:
            return self.produces[item]
        except KeyError as exc:
            raise AttributeError(item) from exc

    def __repr__(self) -> str:
        return f"{self.__class__.__name__}(name={self.name!r})"


class PairStep(Step):
    """Producer/verifier step."""

    kind = "pair"

    def __init__(
        self,
        *,
        name: str,
        producer: PromptSpec,
        verifier: PromptSpec,
        session: Session | None = None,
        requires: Sequence[Artifact] | None = None,
        produces: Mapping[str, Artifact] | None = None,
        log_artifacts: Sequence[Artifact] | None = None,
    ) -> None:
        super().__init__(
            name=name,
            session=session,
            requires=requires,
            produces=produces,
            log_artifacts=log_artifacts,
        )
        self.producer = producer
        self.verifier = verifier


class LLMStep(Step):
    """Single provider turn."""

    kind = "llm"

    def __init__(
        self,
        *,
        name: str,
        producer: PromptSpec,
        session: Session | None = None,
        requires: Sequence[Artifact] | None = None,
        produces: Mapping[str, Artifact] | None = None,
        log_artifacts: Sequence[Artifact] | None = None,
    ) -> None:
        super().__init__(
            name=name,
            session=session,
            requires=requires,
            produces=produces,
            log_artifacts=log_artifacts,
        )
        self.producer = producer


class SystemStep(Step):
    """Pure system handler step."""

    kind = "system"

    def __init__(
        self,
        *,
        name: str,
        session: Session | None = None,
        requires: Sequence[Artifact] | None = None,
        produces: Mapping[str, Artifact] | None = None,
        log_artifacts: Sequence[Artifact] | None = None,
    ) -> None:
        super().__init__(
            name=name,
            session=session,
            requires=requires,
            produces=produces,
            log_artifacts=log_artifacts,
        )
