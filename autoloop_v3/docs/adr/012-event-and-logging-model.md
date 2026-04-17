# ADR 012: Event And Logging Model

- Decision name: event/logging model

## Candidate A

- Description: keep only human-readable raw logs and derive everything else from them.
- correctness: weak because machine resume and parity checks depend on structured data.
- compatibility: medium because raw logs already exist.
- simplicity: simple to append, weak for consumers.
- extensibility: weak because each new consumer must parse text.
- observability: medium for humans, weak for tooling.
- testability: weak because log parsing becomes part of behavior tests.
- failure handling: weak because malformed text is hard to recover from.
- performance: acceptable.
- migration risk: medium.

## Candidate B

- Description: keep append-only structured events for machine state, human-readable raw logs for chronology, and a separate decisions ledger for authoritative decisions and clarifications.
- correctness: strong because each sink has one responsibility.
- compatibility: strong because it preserves the current workspace artifacts.
- simplicity: strong because event, raw, and decision consumers stop overloading one file.
- extensibility: strong because new event types do not require raw-log parsing.
- observability: strong for both humans and tooling.
- testability: strong because each artifact can be asserted independently.
- failure handling: strong because one corrupted sink does not destroy all observability.
- performance: strong because append-only writes are cheap.
- migration risk: low.

## Candidate C

- Description: move all runtime history into a database-backed observability store.
- correctness: potentially strong, but it would diverge from current artifact expectations.
- compatibility: weak because existing workflows and tests expect files in `.autoloop`.
- simplicity: weak because operating a database is out of scope.
- extensibility: strong in theory.
- observability: strong, but at the cost of a new operational dependency.
- testability: medium because fixtures become heavier.
- failure handling: medium because storage availability becomes critical.
- performance: strong.
- migration risk: high because it changes the runtime contract materially.

## Selected Option

Candidate B.

## Why The Selected Option Is The Book Architecture Choice

It preserves the current workspace artifacts while giving each one a precise role. That keeps pause or resume, debugging, and parity testing straightforward without inventing a heavier storage system.
