# ADR 005: Checkpoint Persistence Model

- Decision name: checkpoint persistence model

## Candidate A

- Description: rely only on append-only events and rebuild runtime state by replaying them.
- correctness: possible, but replay logic becomes more complex than the current needs.
- compatibility: medium because legacy resume already depends on events, but not only on events.
- simplicity: weak because every resume path requires full reconstruction logic.
- extensibility: strong for auditing, but heavier for routine execution.
- observability: strong because all state changes are captured as events.
- testability: medium because replay fixtures get large quickly.
- failure handling: medium because corrupted event history can block recovery.
- performance: weaker on resume because full replay is required.
- migration risk: medium.

## Candidate B

- Description: persist explicit `Checkpoint` snapshots and keep append-only events separately for parity, auditing, and resume metadata.
- correctness: strong because the engine restores directly from a typed snapshot.
- compatibility: strong because events can still preserve legacy resume semantics and observability.
- simplicity: strong because snapshot restore is direct while event logging stays append-only.
- extensibility: strong because checkpoint schema can evolve independently from event sinks.
- observability: strong because both current-state and history views exist.
- testability: strong because checkpoint and event behavior can be tested separately.
- failure handling: strong because best-effort checkpoint-on-failure is straightforward.
- performance: strong because resume reads a small snapshot.
- migration risk: low.

## Candidate C

- Description: store checkpoint-like data only inside session files.
- correctness: weak because engine state and session state are different concerns.
- compatibility: medium because legacy sessions exist, but they do not encode full engine state.
- simplicity: deceptively simple, but state boundaries blur.
- extensibility: weak because checkpoint semantics become provider-store semantics.
- observability: weak because session files stop being simple bindings.
- testability: weak because every resume test depends on provider-session format.
- failure handling: weak because corrupted session files would lose engine state too.
- performance: acceptable.
- migration risk: high because it overloads an existing public file format.

## Selected Option

Candidate B.

## Why The Selected Option Is The Book Architecture Choice

Separating checkpoint snapshots from event history keeps restore logic simple while preserving the append-only logs required for parity and debugging. It is the cleanest boundary between engine state and runtime history.
