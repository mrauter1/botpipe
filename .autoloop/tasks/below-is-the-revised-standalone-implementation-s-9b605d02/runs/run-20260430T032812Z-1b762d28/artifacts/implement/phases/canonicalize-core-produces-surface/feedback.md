# Implement ↔ Code Reviewer Feedback

- Task ID: below-is-the-revised-standalone-implementation-s-9b605d02
- Pair: implement
- Phase ID: canonicalize-core-produces-surface
- Phase Directory Key: canonicalize-core-produces-surface
- Phase Title: Canonicalize Core Vocabulary
- Scope: phase-local authoritative verifier artifact

- IMP-001 `blocking` — [__init__.py](/home/rauter/autoloop_v3_bkp/autoloop_v3/__init__.py), [autoloop_v3/core/__init__.py](/home/rauter/autoloop_v3_bkp/autoloop_v3/autoloop_v3/core/__init__.py): the phase acceptance and decisions required reducing package compatibility to one explicit `autoloop_v3.core -> core` bridge after removing the dynamic `core.__init__` mirroring, but the implementation now maintains two explicit bridge layers and duplicates the full `_CORE_SUBMODULES` alias table in both files. This is an intent miss and a maintainability regression: future submodule additions or renames must be synchronized in two places, and the remaining bridge story is no longer “one explicit path.” Minimal fix: centralize the bridge in a single authoritative entrypoint and make the other location a thin delegator or remove it entirely; the alias table should exist in one place only.
