# Assemble the evidence pack

Inspect only the permitted evidence surface and produce a source-traceable handoff.

- `source_register.json` records each inspected source, provenance, relevant scope or time, contribution, limitations, and confidence. Prefer immutable declared-evidence artifacts from `evidence_intake`; label any additional live discovery separately with its observation time. Never list an uninspected source as evidence.
- `evidence_pack` answers the framed questions with citations to registered sources. Distinguish observation, supported inference, allegation, and unknown; describe contradictions instead of averaging them away.
- `evidence_gaps` explains each unresolved gap, its decision impact, and the specific evidence that could resolve it.
- `investigation_summary.json` contains `authoritative_artifacts`, `investigation_kind`, `ready_for_downstream_assessment`, `source_count`, `finding_count`, `unresolved_gap_count`, and non-empty `key_findings`.

Readiness means the downstream consumer can act within the stated uncertainty, not that every gap is closed. An unavailable declared source stays an explicit gap and may justify `question` or `blocked`; never replace it with guessed content. Accept when counts and findings match the artifacts and all material claims are traceable. Rework source or synthesis defects locally; replan a changed scope. Do not diagnose, remediate, or draft final communications.
