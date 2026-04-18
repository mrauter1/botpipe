"""Authoring helpers that return strict workflow step declarations."""

from __future__ import annotations

from collections.abc import Mapping, Sequence

from autoloop_v3.workflow import Artifact, PairStep, Session

from .prompts import PromptPair


def pair_step(
    *,
    name: str,
    prompts: PromptPair,
    session: Session | None = None,
    requires: Sequence[Artifact] | None = None,
    produces: Mapping[str, Artifact] | None = None,
    log_artifacts: Sequence[Artifact] | None = None,
) -> PairStep:
    """Build a `PairStep` from an explicit prompt pair."""

    return PairStep(
        name=name,
        producer=prompts.producer,
        verifier=prompts.verifier,
        session=session,
        requires=requires,
        produces=produces,
        log_artifacts=log_artifacts,
    )

