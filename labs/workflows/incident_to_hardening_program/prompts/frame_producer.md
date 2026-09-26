# Frame the incident response

Establish a usable incident boundary without assuming a cause.

- `incident_scope_brief` states the trigger, window, affected system, declared severity, known impact, commander or decision owner, and explicit scope limits.
- `response_objectives` separates immediate safety or service restoration from diagnosis and longer-term hardening.
- `evidence_intake_register` maps timeline, impact, change, telemetry, and control questions to captured declared sources in `evidence_intake`, explicit unavailable records, or permitted live discovery.
- Label reported facts, observations, and assumptions separately.

Accept when responders can gather evidence without silently widening the incident. Rework local ambiguity; replan a changed boundary or objective; ask or block on a prerequisite that prevents safe response. Do not assert root cause or final blast radius.
