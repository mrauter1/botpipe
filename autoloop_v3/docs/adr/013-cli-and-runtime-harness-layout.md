# ADR 013: CLI And Runtime Harness Layout

- Decision name: CLI/runtime harness layout

## Candidate A

- Description: build one large `main.py` that owns loader, config, workspace, providers, execution, and CLI parsing.
- correctness: workable, but the runtime becomes hard to change safely.
- compatibility: high in the short term because it mirrors the current monolith.
- simplicity: weak over time because concerns stay entangled.
- extensibility: weak because every new feature touches the same file.
- observability: medium because logging can be centralized, but ownership stays muddy.
- testability: weak because most tests become integration-heavy.
- failure handling: weak because the control flow is hard to isolate.
- performance: acceptable.
- migration risk: medium because later modularization would be invasive.

## Candidate B

- Description: split the runtime into `loader.py`, `config.py`, `workspace.py`, `logging.py`, `runner.py`, and a thin `cli.py`.
- correctness: strong because each operational concern has one owner.
- compatibility: strong because the runner can preserve old CLI behavior while calling the new engine.
- simplicity: strong because the CLI is only argument parsing and dispatch.
- extensibility: strong because new providers or stores attach without growing one file.
- observability: strong because logging and workspace events have explicit modules.
- testability: strong because config, workspace, runner, and CLI can be tested separately.
- failure handling: strong because errors can be classified by runtime stage.
- performance: strong enough; module boundaries do not harm this workload.
- migration risk: low.

## Candidate C

- Description: expose only a library API and defer all CLI concerns to external scripts.
- correctness: fine for a library, but it drops a required operational surface.
- compatibility: weak because the legacy runtime is CLI-driven.
- simplicity: strong for the package, but only by removing scope.
- extensibility: medium.
- observability: medium because external scripts may diverge.
- testability: medium because library tests are easy, CLI parity is absent.
- failure handling: medium.
- performance: strong.
- migration risk: high because it narrows the accepted runtime behavior.

## Selected Option

Candidate B.

## Why The Selected Option Is The Book Architecture Choice

It preserves the CLI contract while keeping runtime responsibilities separated and testable. The runner becomes the operational orchestrator, and the CLI stays a thin shell rather than the implementation center.
