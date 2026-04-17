# ADR 010: Resume And Answer Injection Mechanism

- Decision name: resume/answer injection mechanism

## Candidate A

- Description: keep pending questions and answers only in raw logs and reconstruct them when resuming.
- correctness: possible, but prompt parsing becomes part of resume logic.
- compatibility: medium because logs are authoritative history, but not ideal state.
- simplicity: weak because resume depends on log scraping.
- extensibility: weak because answer semantics stay implicit.
- observability: medium because the history is visible, but not structured for restore.
- testability: weak because resume behavior depends on text formatting.
- failure handling: weak because malformed logs can block restore.
- performance: weaker because resume must parse history.
- migration risk: medium.

## Candidate B

- Description: persist pending question and pending answer in the typed checkpoint, expose the answer on `Context`, and consume it exactly once on resumed execution.
- correctness: strong because the resume contract is explicit.
- compatibility: strong because logs can still record clarifications while the engine restores from structure.
- simplicity: strong because engine restore is direct and answer semantics are clear.
- extensibility: strong because future resume metadata can extend the checkpoint.
- observability: strong because both checkpoint data and logs exist.
- testability: strong because pause and resume flows can be asserted without parsing logs.
- failure handling: strong because best-effort checkpointing preserves the pending interaction state.
- performance: strong because resume reads structured data directly.
- migration risk: low.

## Candidate C

- Description: inject answers only as ad hoc runtime overrides without persisting them in checkpoints.
- correctness: weak because resumed runs can lose pending user input.
- compatibility: medium because a fresh prompt can include the answer, but state is implicit.
- simplicity: simple in code, but incomplete as a runtime contract.
- extensibility: weak because interaction state is not durable.
- observability: medium because logs still show the answer.
- testability: weak because behavior depends on external runner state.
- failure handling: weak because crashes after answer receipt can lose it.
- performance: strong.
- migration risk: high because it breaks durable resume semantics.

## Selected Option

Candidate B.

## Why The Selected Option Is The Book Architecture Choice

Pause and resume are first-class workflow behaviors in the spec. The cleanest design is to encode them in the checkpoint model instead of reconstructing them from logs or ephemeral runner state.
