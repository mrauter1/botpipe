# Investigate a workflow before proposing a change

Return a `DiagnosticAssessment` matching the injected schema. This is a
read-only investigation. Inspect workflow source only under
`analysis_source_root`. Inspect the recorded runs only under
`analysis_evidence_root`, starting at `index.json`. That bundle contains the
recorded operation inputs, prompts, responses, failures, rejection notes, and
referenced artifact versions available to this investigation.

Assess the workflow's actual purpose, the whole workflow, and relevant steps.
Use the supplied executable signature and caller trial availability when
drafting representative trial cases. Caller-supplied cases are constraints;
do not silently replace them. A scope may be uncertain or not assessed when
the evidence is insufficient.

Make every proposed trial case self-contained through its typed arguments,
captured `assets`, or the caller's explicit fixture. Asset destinations are
automatically inlined for the tool-free judge. Add relative `judge_input_paths`
for any other fixture reference files needed to apply the rubric, and relative
`output_paths` for every workspace result file the workflow should produce.
Do not leave required evidence as an unreadable filename: the judge has no tools
and receives only bounded captured bytes. Prefer textual or JSON evidence;
missing, oversized, or binary essential files make comparison inconclusive.

Every evidence link must keep exactly one basis:

- `observation`: name supplied observation IDs for deterministic recorded facts
  such as status, counts, and usage; no text quote is needed for these facts;
- `trace`: ground claims about prompts, responses, rejection reasons, or artifact
  contents with a relative `evidence_path` and exact `quote` from the evidence
  bundle; do not transcribe observation IDs for textual citations;
- `source`: name captured workflow paths in `source_paths`; when quoting source,
  use that same relative path as `evidence_path` plus an exact `quote`;
- `inference`: identify reasoning as inference and do not attach direct citation
  fields.

Do not invent executions, causes, counts, measurements, paths, or quotes. A
combined observation-and-quote citation must identify the cited operation.
Create a concise rubric fixed before candidate generation. Mark
criteria that are obligations with `must_preserve: true`, state needed evidence
and falsification, and provide a comparison rule. Do not choose an
implementation.

When `grounding_feedback` is present, correct that exact citation, case, or
rubric defect while preserving valid findings. Do not edit any frozen file.
