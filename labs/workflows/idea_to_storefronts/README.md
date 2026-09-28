# One Idea, Many Storefronts

`idea_to_storefronts` (alias `storefronts`) turns a niche into researched ideas,
scripts, a digital product and per-platform publishing packages. This lab package
publishes the supplied lean-author workflow with fixes to its human feedback,
packaging dependencies and research checks. It prepares files for the creator;
it does not upload content or create storefront listings.

```sh
botpipe run storefronts --input '{"niche":"Portuguese-speaking home cooks who batch meals"}'
```

The run pauses to select an idea and angle, confirm recordings, approve pieces,
and collect metrics after posting. Its normal producer/reviewer loops allow three
rounds before asking the creator to override, retry with notes or abandon. Research
and verification require a provider with web access.

## Rework and approval

- Gate 3 notes reach the responsible producer and reviewer on the first rework
  round and remain available on subsequent rounds. Later notes can explicitly
  supersede earlier notes. A piece cannot be approved and sent for rework in the
  same answer.
- The creator's angle and off-limits topics reach every platform packager and
  compliance reviewer, including later rebuilds.
- A script or product change rebuilds active platform packages from the updated
  scripts, listing and product files, after all source edits in that answer finish.
  Rebuilt packages need approval again; unchanged source pieces stay approved.
  Package-specific notes survive these rebuilds.
- Product format changes recalculate KDP applicability. A deliberately abandoned
  platform stays dropped while it remains applicable. A newly applicable platform
  gets a package and approval step.
- Each product draft has its own directory. Rework receives the previous files
  as inputs, while packaging consumes only the current draft's deliverables.

If script rework changes recorded speech, the creator must update the recording
and any optional recording aids before uploading. This workflow checks recording
file presence, not the contents of audio/video or agreement with a revised script.

## Research evidence

Evidence must contain valid HTTP(S) URLs; duplicate links do not improve ranking.
A separate, read-only, network-enabled reviewer must open every source and report
whether it supports the specific idea. Missing checks, inaccessible pages and
unsupported sources return concrete findings to the researcher. After three
unsuccessful rounds, the run fails with the outstanding findings before Gate 1;
unverified research has no override path.

These are provider-backed evidence judgments, not a guarantee of factual truth.
The regression suite uses `FakeProvider` to test enforcement, rework and replay;
it does not establish live research or content quality.

## Tests

```sh
python -m pytest -q tests/test_idea_to_storefronts.py
```

Start a new run for version 2; resuming version 1 across this control-flow change
is not supported.
