* **Goal**

  * Implement a greenfield Autoloop v3 worklist system for **ordered, selectable, progress-tracked worklists**.
  * The common authoring case must be concise:

    ```python
    phase = progress_artifact_worklist(
        "phase",
        model=PhasePlan,
        fallback=implicit_phase_plan,
    )
    ```
  * Authors should not normally specify:

    * `collection="items"`
    * `item_id="id"`
    * `title="title"`
    * `status="status"`
    * selector params such as `phase`, `from_phase`, `to_phase`, `phase_mode`
  * Treat this as greenfield.
  * Do not add legacy aliases, migration shims, or compatibility behavior for old board shapes.

* **Architecture ownership**

  * Core owns **generic ordered selection**.
  * Stdlib owns the **common progress-backed JSON artifact worklist type**.
  * Workflow code owns domain semantics.
  * Core worklists must remain generic.
  * Core `WorkItem.status` remains `str | None`, not an enum.
  * The stdlib progress worklist type may enforce a default status vocabulary.
  * Do not add phase-specific concepts to core or stdlib.
  * Do not add duplicate route-helper wrappers when existing route/effect primitives already express status mutation and advancement.

* **Canonical progress board shape**

  * A progress board is a JSON object with a single ordered collection named `items`.
  * Each item uses the canonical fields:

    ```json
    {
      "id": "phase-1",
      "title": "Phase 1",
      "status": "planned"
    }
    ```
  * Additional fields are domain payload:

    ```json
    {
      "id": "phase-1",
      "title": "Phase 1",
      "status": "planned",
      "objective": "...",
      "acceptance_criteria": []
    }
    ```
  * Do not support noncanonical defaults such as:

    * `phases`
    * `phase_id`
    * `work_items`
    * `name`
    * automatic list-field detection
  * If a workflow needs a noncanonical shape, it should use a lower-level custom source, not `progress_artifact_worklist`.

* **Files to implement**

  * Modify:

    * `autoloop/core/worklists.py`
    * `autoloop/stdlib/__init__.py`
  * Add:

    * `autoloop/stdlib/worklists.py`
    * `tests/unit/test_worklist_selectors.py`
    * `tests/unit/test_stdlib_progress_worklists.py`
    * `tests/runtime/test_progress_worklists.py`
  * Do not modify root `autoloop/__init__.py` in the first pass.
  * Do not modify provider, checkpoint, session, or route internals unless a test exposes a direct integration bug.

* **Core selector modes**

  * Implement exactly four selector modes:

    * `all`
    * `single`
    * `up_to`
    * `from_to`
  * Do not support aliases:

    * no `up-to`
    * no `upto`
    * no `from-to`
    * no `range`
  * Invalid mode strings must fail clearly.
  * Mode names are canonical API.

* **Core `Selector` API**

  * Define:

    ```python
    @dataclass(frozen=True, slots=True)
    class Selector:
        item_param: str | None = None
        start_param: str | None = None
        end_param: str | None = None
        mode_param: str | None = None
        default_mode: Literal["all", "single", "up_to", "from_to"] = "all"
        allowed_modes: tuple[str, ...] = ("all", "single", "up_to", "from_to")
    ```
  * `item_param` is the primary selected-item parameter.
  * `start_param` is the inclusive start bound for `from_to`.
  * `end_param` is the inclusive end bound for `up_to` and `from_to`.
  * `mode_param` selects the mode.
  * `default_mode` defaults to `all`.
  * `allowed_modes` defaults to all four supported modes.
  * Validation rules:

    * All parameter names, when provided, must be non-empty strings after stripping.
    * `allowed_modes` must be non-empty.
    * Each allowed mode must be one of `all`, `single`, `up_to`, `from_to`.
    * `allowed_modes` must not contain duplicates.
    * `default_mode` must be included in `allowed_modes`.
    * Do not normalize hyphens or aliases.
    * Store stripped values.

* **Default selector convention**

  * `progress_artifact_worklist("phase", ...)` automatically uses:

    ```python
    Selector(
        item_param="phase",
        start_param="from_phase",
        end_param="to_phase",
        mode_param="phase_mode",
        default_mode="all",
        allowed_modes=("all", "single", "up_to", "from_to"),
    )
    ```
  * `progress_artifact_worklist("slice", ...)` automatically uses:

    ```python
    Selector(
        item_param="slice",
        start_param="from_slice",
        end_param="to_slice",
        mode_param="slice_mode",
        default_mode="all",
        allowed_modes=("all", "single", "up_to", "from_to"),
    )
    ```
  * Authors can override the selector:

    ```python
    phase = progress_artifact_worklist(
        "phase",
        model=PhasePlan,
        selector=Selector(
            item_param="selected_phase",
            start_param="start_phase",
            end_param="end_phase",
            mode_param="selection_mode",
        ),
    )
    ```

* **Core selection semantics**

  * Given ordered items `[p1, p2, p3, p4, p5]`:

    * `mode=all` selects `[p1, p2, p3, p4, p5]`.
    * `mode=single`, `phase=p3` selects `[p3]`.
    * `mode=single` with no explicit item selects `[p1]`.
    * `mode=up_to`, `phase=p3` selects `[p1, p2, p3]`.
    * `mode=up_to`, `to_phase=p3` selects `[p1, p2, p3]`.
    * `mode=up_to` with no bound selects all items.
    * `mode=from_to`, `from_phase=p2`, `to_phase=p4` selects `[p2, p3, p4]`.
    * `mode=from_to`, `from_phase=p2` selects `[p2, p3, p4, p5]`.
    * `mode=from_to`, `to_phase=p4` selects `[p1, p2, p3, p4]`.
    * `mode=from_to`, `phase=p4` treats `phase` as the end bound and selects `[p1, p2, p3, p4]`.
    * `mode=from_to` with no bounds selects all items.
  * `from_to` is inclusive.
  * If start appears after end, raise a workflow execution error.
  * If a referenced item id does not exist, raise a workflow execution error.
  * If `mode=all`, selector-bound item parameters are invalid:

    * `phase_mode=all`, `phase=p3` fails.
    * `phase_mode=all`, `from_phase=p2` fails.
    * `phase_mode=all`, `to_phase=p4` fails.
  * Empty or whitespace-only selector params count as absent.
  * `Selection.explicit` must be:

    * `True` when a selector-bound parameter is supplied and used.
    * `False` for default `all`.
    * `False` for default `single` selecting the first item.
    * `False` for `up_to` or `from_to` with no explicit bounds.

* **Core selection implementation**

  * Implement selection in `Worklist`, after source loading and validation.
  * Sources return ordered items only.
  * Sources do not own selection logic.
  * Use `ctx.workflow_params` for selector parameter lookup.
  * Add private helpers as needed:

    ```python
    def _selector_mode(ctx: Context, selector: Selector, worklist_name: str) -> str: ...
    def _selector_param(ctx: Context, name: str | None) -> str | None: ...
    def _item_indexes(items: Sequence[WorkItem[T]]) -> dict[str, int]: ...
    def _require_item_id(...): ...
    ```
  * Selector errors must include:

    * worklist name,
    * mode,
    * parameter name,
    * offending value,
    * known ids when relevant.

* **Stdlib default work statuses**

  * Add:

    ```python
    class WorkStatus(str, Enum):
        planned = "planned"
        in_progress = "in_progress"
        blocked = "blocked"
        completed = "completed"
        failed = "failed"
    ```
  * These are the only default statuses for `progress_artifact_worklist`.
  * `skipped` is not part of the strict default set.
  * `skipped` should be available through `extra_statuses`.
  * Do not include `ready` or `deferred` by default.
  * Do not include workflow-domain statuses such as:

    * `implemented`
    * `tested`
    * `approved`
    * `released`
  * Core worklists may still carry arbitrary string statuses; this vocabulary applies only to stdlib progress worklists.

* **Stdlib `WorkStatusPolicy`**

  * Implement:

    ```python
    @dataclass(frozen=True, slots=True)
    class WorkStatusPolicy:
        extra_statuses: tuple[str, ...] = ()
        initial: str = WorkStatus.planned.value
        active: str = WorkStatus.in_progress.value
        success: str = WorkStatus.completed.value
        blocked: str = WorkStatus.blocked.value
        failed: str = WorkStatus.failed.value
        terminal: frozenset[str] = field(default_factory=lambda: frozenset({
            WorkStatus.completed.value,
            WorkStatus.blocked.value,
            WorkStatus.failed.value,
        }))
        aliases: Mapping[str, str] = field(default_factory=lambda: {
            "todo": "planned",
            "queued": "planned",
            "started": "in_progress",
            "in-progress": "in_progress",
            "done": "completed",
            "complete": "completed",
            "finished": "completed",
        })

        @property
        def statuses(self) -> tuple[str, ...]:
            ...
    ```
  * `statuses` returns:

    ```python
    (
        "planned",
        "in_progress",
        "blocked",
        "completed",
        "failed",
        *extra_statuses,
    )
    ```
  * Validate:

    * Default statuses plus `extra_statuses` must be non-empty.
    * Every status must be a non-empty string.
    * No duplicate statuses.
    * `initial`, `active`, `success`, `blocked`, and `failed` must be in `statuses`.
    * All `terminal` statuses must be in `statuses`.
    * Alias keys and values must be non-empty strings.
    * Alias values must resolve to supported statuses.
  * Implement:

    ```python
    def normalize(self, raw: str | None) -> str: ...
    def is_supported(self, raw: str | None) -> bool: ...
    def is_terminal(self, raw: str | None) -> bool: ...
    ```
  * `normalize` behavior:

    * `None` or whitespace-only returns `initial`.
    * Strip whitespace.
    * Lowercase.
    * Replace spaces with underscores.
    * Apply aliases.
    * Reject unsupported statuses with `ValueError`.
  * Do not include typo aliases such as `in_porgress` by default.

* **Optional skipped policy**

  * Provide a clear way to enable skipped:

    ```python
    SKIPPABLE_WORK_STATUS_POLICY = WorkStatusPolicy(
        extra_statuses=("skipped",),
        terminal=frozenset({
            WorkStatus.completed.value,
            WorkStatus.blocked.value,
            WorkStatus.failed.value,
            "skipped",
        }),
    )
    ```
  * Export this constant only if desired.
  * Otherwise document the pattern:

    ```python
    status_policy=WorkStatusPolicy(
        extra_statuses=("skipped",),
        terminal=frozenset({"completed", "blocked", "failed", "skipped"}),
    )
    ```

* **Stdlib Pydantic base models**

  * Add:

    ```python
    class ProgressItem(BaseModel):
        id: str
        title: str
        status: str = WorkStatus.planned.value
    ```
  * Add:

    ```python
    ItemT = TypeVar("ItemT", bound=ProgressItem)

    class ProgressBoard(BaseModel, Generic[ItemT]):
        items: list[ItemT]
    ```
  * If Pydantic generic complexity is too high, use:

    ```python
    class ProgressBoard(BaseModel):
        items: list[ProgressItem]
    ```

    and allow workflows to define their own board model with the same shape.
  * Recommended workflow shape:

    ```python
    class PhaseItem(ProgressItem):
        objective: str
        acceptance_criteria: list[str] = []

    class PhasePlan(ProgressBoard[PhaseItem]):
        pass
    ```

* **Default artifact convention**

  * `progress_artifact_worklist("phase", model=PhasePlan)` creates a default artifact if none is provided.
  * Default path:

    ```text
    {workflow_folder}/worklists/phase.json
    ```
  * Default artifact name:

    ```text
    phase_board
    ```
  * Implementation:

    ```python
    Artifact.json(
        "{workflow_folder}/worklists/phase.json",
        schema=PhasePlan,
        required=False,
        name="phase_board",
    )
    ```
  * For `progress_artifact_worklist("slice", ...)`:

    * path: `{workflow_folder}/worklists/slice.json`
    * artifact name: `slice_board`
  * Authors may override:

    ```python
    phase = progress_artifact_worklist(
        "phase",
        artifact=Artifact.json("{workflow_folder}/phase_plan.json", schema=PhasePlan),
        model=PhasePlan,
    )
    ```

* **Stdlib `ProgressJsonCollectionSource`**

  * Implement:

    ```python
    @dataclass(frozen=True, slots=True)
    class ProgressJsonCollectionSource(WorklistSource[Mapping[str, Any]]):
        artifact: Artifact
        model: type[BaseModel] | None = None
        fallback: Callable[[Context], Mapping[str, Any] | BaseModel] | None = None
        write_fallback: bool = True
        status_policy: WorkStatusPolicy = field(default_factory=WorkStatusPolicy)

        mutable: bool = True
        artifact_backed: bool = True
    ```
  * Do not expose `collection`, `item_id`, `title`, or `status` on this common-case source.
  * Hard-code:

    * collection field: `items`
    * id field: `id`
    * title field: `title`
    * status field: `status`
  * If authors need a different shape, they should write a custom source.
  * Validate:

    * `artifact` must be an `Artifact`.
    * `model`, if provided, must be a `BaseModel` subclass.
    * `fallback`, if provided, must be callable.
    * `status_policy` must be a `WorkStatusPolicy`.

* **`ProgressJsonCollectionSource.ensure(ctx)`**

  * Resolve the artifact path with core artifact template resolution.
  * If the path exists, do nothing.
  * If the path does not exist and no fallback is configured, do nothing.
  * If fallback is configured and `write_fallback=True`:

    * materialize fallback,
    * normalize missing statuses,
    * validate against `model` if provided,
    * write pretty JSON with trailing newline.

* **Fallback materialization**

  * Fallback signature:

    ```python
    Callable[[Context], Mapping[str, Any] | BaseModel]
    ```
  * If fallback returns a Pydantic model:

    * use `model_dump(mode="json")`.
  * If fallback returns a mapping:

    * convert to shallow dict.
  * Any other return type is an error.
  * Fallback payload must use:

    ```json
    {"items": [...]}
    ```
  * If fallback lacks `items`, fail.
  * If an item lacks `id` or `title`, fail.
  * If an item lacks `status`, set it to policy `initial`.

* **`ProgressJsonCollectionSource.load(ctx)`**

  * If artifact exists:

    * read JSON,
    * require top-level object,
    * validate with `model` if provided,
    * use validated `model_dump(mode="json")` as canonical payload.
  * If artifact is missing:

    * use fallback if configured,
    * optionally write fallback if `write_fallback=True`,
    * otherwise raise a clear execution error.
  * Extract `items`.
  * Require `items` to be a list.
  * Require every item to be an object.
  * For each item:

    * require non-empty string `id`,
    * require non-empty string `title`,
    * normalize `status` through `WorkStatusPolicy`,
    * include normalized `status` in item payload,
    * create a core `WorkItem`.
  * Reject duplicate ids.
  * Preserve source order.

* **`ProgressJsonCollectionSource.save(ctx, items)`**

  * Load current artifact payload if present.
  * If missing and fallback exists, materialize fallback.
  * If missing and fallback does not exist, fail.
  * Validate with `model` before mutation if configured.
  * Update only `status` fields for matching item ids.
  * Do not reorder items.
  * Do not add items.
  * Do not delete items.
  * Do not mutate non-status payload fields.
  * Normalize saved statuses through `WorkStatusPolicy`.
  * Validate with `model` after mutation if configured.
  * Write pretty JSON with trailing newline.

* **`ProgressJsonCollectionSource.validate(ctx, items)`**

  * Return `None` on success.
  * Return a readable string on validation failure.
  * Validate:

    * no duplicate ids,
    * every status is supported by policy,
    * every id is non-empty,
    * every title is non-empty.

* **Stdlib factory**

  * Implement:

    ```python
    def progress_artifact_worklist(
        name: str,
        *,
        model: type[BaseModel] | None = None,
        fallback: Callable[[Context], Mapping[str, Any] | BaseModel] | None = None,
        artifact: Artifact | None = None,
        selector: Selector | None = None,
        status_policy: WorkStatusPolicy | None = None,
        write_fallback: bool = True,
        item_state: type[BaseModel] | None = None,
    ) -> Worklist[Mapping[str, Any]]:
        ...
    ```
  * `name` is required positional.
  * Defaults:

    * `artifact`: auto-created from name and model.
    * `selector`: auto-created from name.
    * `status_policy`: `WorkStatusPolicy()`.
    * `write_fallback`: `True`.
  * Return:

    ```python
    Worklist(
        name=name,
        source=ProgressJsonCollectionSource(...),
        selector=selector or progress_selector(name),
        item_state_model=item_state,
    )
    ```

* **Default selector factory**

  * Implement:

    ```python
    def progress_selector(name: str) -> Selector:
        return Selector(
            item_param=name,
            start_param=f"from_{name}",
            end_param=f"to_{name}",
            mode_param=f"{name}_mode",
            default_mode="all",
            allowed_modes=("all", "single", "up_to", "from_to"),
        )
    ```
  * Export `progress_selector` only if useful.
  * Do not add selector aliases.

* **Artifact access from generated worklist**

  * Preferred greenfield API:

    * `progress_artifact_worklist(...)` returns a `Worklist` with an `.artifact` property when artifact-backed.
  * This enables:

    ```python
    phase = progress_artifact_worklist("phase", model=PhasePlan)

    plan = produce_verify_step(
        "plan",
        writes={"phase_plan": phase.artifact},
        ...
    )
    ```
  * If adding `.artifact` to generic `Worklist` is too invasive:

    * return a thin subclass or documented artifact-backed worklist type.
  * Do not return a tuple.
  * Do not make workflow authors separately construct the artifact in the common case.

* **Recommended authoring example**

  * Target syntax:

    ```python
    class PhaseItem(ProgressItem):
        objective: str
        acceptance_criteria: list[str] = []

    class PhasePlan(ProgressBoard[PhaseItem]):
        pass

    def implicit_phase_plan(ctx: Context) -> PhasePlan:
        return PhasePlan(
            items=[
                PhaseItem(
                    id="default",
                    title="Default phase",
                    objective="Complete the requested task.",
                    acceptance_criteria=[],
                )
            ]
        )

    class MyWorkflow(Workflow):
        phase = progress_artifact_worklist(
            "phase",
            model=PhasePlan,
            fallback=implicit_phase_plan,
        )
    ```

* **Route/effect usage**

  * Do not add new route helper wrappers.
  * Use existing route/effect primitives:

    ```python
    "accepted": Route.complete_and_advance(
        after_phase_advance,
        worklist="phase",
        exhausted="audit_ready",
    )
    ```
  * Blocking:

    ```python
    "blocked": Route.advance(
        after_phase_advance,
        worklist="phase",
        status=WorkStatus.blocked.value,
    )
    ```
  * Failure:

    ```python
    "failed": Route.advance(
        after_phase_advance,
        worklist="phase",
        status=WorkStatus.failed.value,
    )
    ```
  * Manual status mutation:

    ```python
    return Effects(
        worklists=(
            WorklistEffect(
                worklist="phase",
                set_current_status=WorkStatus.in_progress.value,
            ),
        )
    )
    ```

* **No legacy support**

  * Do not support:

    * `up-to`
    * `upto`
    * `from-to`
    * `range`
    * `phase_id`
    * `phases`
    * automatic field detection
    * typo aliases
    * old custom board shapes
    * silent status coercion beyond explicit `WorkStatusPolicy.aliases`
  * If users need legacy compatibility, they should write an adapter step or custom source.

* **Error quality**

  * Selector errors must include:

    * worklist name,
    * mode,
    * parameter name,
    * offending value,
    * known ids when item lookup fails.
  * Source errors must include:

    * artifact path for file issues,
    * `items` for collection issues,
    * item id when item-specific.
  * Do not leak raw `KeyError`, `json.JSONDecodeError`, or uncontextualized Pydantic errors.

* **Unit tests: core selectors**

  * Add `tests/unit/test_worklist_selectors.py`.
  * Required tests:

    * `test_selector_default_all_selects_all_items`
    * `test_selector_all_rejects_item_param`
    * `test_selector_all_rejects_start_param`
    * `test_selector_all_rejects_end_param`
    * `test_selector_single_with_item_selects_one_item`
    * `test_selector_single_without_item_selects_first_item`
    * `test_selector_up_to_with_item_selects_prefix`
    * `test_selector_up_to_with_end_param_selects_prefix`
    * `test_selector_up_to_without_bound_selects_all`
    * `test_selector_from_to_with_start_and_end_selects_inclusive_range`
    * `test_selector_from_to_with_only_start_selects_suffix`
    * `test_selector_from_to_with_only_end_selects_prefix`
    * `test_selector_from_to_uses_item_param_as_end_bound`
    * `test_selector_from_to_without_bounds_selects_all`
    * `test_selector_from_to_start_after_end_fails`
    * `test_selector_unknown_item_fails_with_known_ids`
    * `test_selector_rejects_unknown_mode`
    * `test_selector_rejects_duplicate_allowed_modes`
    * `test_selector_rejects_default_mode_not_allowed`

* **Unit tests: stdlib progress worklists**

  * Add `tests/unit/test_stdlib_progress_worklists.py`.
  * Required tests:

    * `test_work_status_policy_default_statuses_are_minimal`
    * `test_work_status_policy_supports_extra_statuses`
    * `test_work_status_policy_can_enable_skipped`
    * `test_work_status_policy_normalizes_aliases`
    * `test_work_status_policy_rejects_unknown_status`
    * `test_progress_board_base_model_accepts_items`
    * `test_progress_source_loads_canonical_items_collection`
    * `test_progress_source_rejects_missing_items_collection`
    * `test_progress_source_rejects_non_object_item`
    * `test_progress_source_rejects_missing_id`
    * `test_progress_source_rejects_missing_title`
    * `test_progress_source_normalizes_missing_status_to_initial`
    * `test_progress_source_rejects_duplicate_ids`
    * `test_progress_source_validates_with_pydantic_model`
    * `test_progress_source_writes_fallback_when_missing`
    * `test_progress_source_missing_without_fallback_fails`
    * `test_progress_source_save_updates_status_only`
    * `test_progress_source_save_preserves_order`
    * `test_progress_artifact_worklist_uses_default_artifact_path`
    * `test_progress_artifact_worklist_uses_default_selector_names`

* **Runtime integration tests**

  * Add `tests/runtime/test_progress_worklists.py`.
  * Test default all:

    * workflow has `progress_artifact_worklist("phase", ...)`.
    * scoped step completes and advances.
    * default run processes all items.
    * all processed statuses persist as `completed`.
  * Test `single`:

    * params: `phase_mode=single`, `phase=p3`
    * only `p3` processed.
  * Test `up_to`:

    * params: `phase_mode=up_to`, `phase=p3`
    * `p1`, `p2`, `p3` processed.
  * Test `from_to`:

    * params: `phase_mode=from_to`, `from_phase=p2`, `to_phase=p4`
    * `p2`, `p3`, `p4` processed.
  * Test invalid range:

    * params: `phase_mode=from_to`, `from_phase=p4`, `to_phase=p2`
    * workflow fails with clear selector error.
  * Test skipped-enabled policy if implemented:

    * source accepts `skipped` only when policy includes `extra_statuses=("skipped",)`.

* **Acceptance criteria**

  * Minimal authoring works:

    ```python
    phase = progress_artifact_worklist(
        "phase",
        model=PhasePlan,
        fallback=implicit_phase_plan,
    )
    ```
  * The generated worklist has:

    * canonical artifact path,
    * canonical selector,
    * default minimal status policy,
    * optional extra statuses,
    * fallback support,
    * Pydantic validation.
  * Default statuses are exactly:

    * `planned`
    * `in_progress`
    * `blocked`
    * `completed`
    * `failed`
  * `skipped` is available only through `extra_statuses`.
  * `single`, `up_to`, and `from_to` work for any ordered worklist.
  * `from_to` is inclusive.
  * Status changes persist back to the JSON artifact.
  * No legacy alias support is added.
  * No phase-specific implementation is added to core or stdlib.
  * No route-helper duplicate layer is added.
  * Existing generic core worklists remain possible.
  * All new tests pass.
  * Existing tests continue to pass.

* **Suggested validation commands**

  * Focused tests:

    ```bash
    pytest tests/unit/test_worklist_selectors.py tests/unit/test_stdlib_progress_worklists.py tests/runtime/test_progress_worklists.py
    ```
  * Adjacent tests:

    ```bash
    pytest tests/unit/test_stdlib_and_extensions.py tests/unit/test_primitives_and_stores.py tests/runtime/test_workspace_and_context.py
    ```
  * Full suite:

    ```bash
    pytest
    ```
