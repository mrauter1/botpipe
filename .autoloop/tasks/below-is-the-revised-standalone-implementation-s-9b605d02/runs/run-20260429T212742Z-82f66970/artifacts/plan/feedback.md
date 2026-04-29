# Plan ↔ Plan Verifier Feedback

- Replaced the empty plan with a five-phase implementation plan tied to actual repo coupling: public/simple surface cleanup, compiler/validation canonicalization, engine/provider/persistence cleanup, repo consumer migration plus optimizer separation, and final strictness/regression verification. This phase order matches where legacy names currently live (`autoloop/simple.py`, `core/*`, `runtime/static_graph.py`, loader/state handling, `stdlib`, and tests) and keeps resume-risk migration narrowly scoped to persisted run data.
