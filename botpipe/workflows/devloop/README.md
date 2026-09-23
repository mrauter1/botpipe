# Devloop

`devloop(request, ...)` is an imperative durable workflow for repository work.
It plans ordered phases, independently reviews the plan, implements and reviews
each phase, optionally tests it, and runs a final evidence-grounded audit.

An implementation reviewer can send work back to implementation or request a
bounded phase-item repair. A repair may revise or append future phases while it
preserves completed work and the active phase identity. Failed tests return to
implementation. The test producer runs suitable checks, and the independent
test verifier reruns suitable checks rather than trusting the producer's report.
Its provider turn declares no durable output artifact, although test execution
may create temporary files and caches. `mode="docloop"` and
`skip_test_phase=True` write explicit
reduced-assurance markers instead of fabricated passing test evidence.

The final audit returns `passed` or `needs_followup`. A follow-up audit decision
can start a nested Devloop child until `auto_followup_max_depth` is reached.
The typed `DevLoopResult` records the plan, audit, completed phases, and optional
follow-up receipt.
