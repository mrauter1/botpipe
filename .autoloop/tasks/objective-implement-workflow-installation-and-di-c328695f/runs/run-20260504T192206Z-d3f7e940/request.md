* **Objective**

  * Implement workflow installation and discovery for the codebase using two first-class workflow sources:

    * Package-installed workflows:

      ```text
      autoloop/workflows/
      ```
    * Workspace-local workflows:

      ```text
      {workspace}/.autoloop/workflows/
      ```
  * Bare workflow names and aliases must resolve from those sources only.
  * Workspace-local workflows must have precedence over package-installed workflows.
  * The codebase must not implicitly discover workflows from:
   
    ```text
    {workspace}/workflows/
    ```

    * This is a greenfield project. Do not introduce complexity by supporting legacy compatibility.
* **Canonical source kinds**

  * Use exactly these serialized source-kind values:

    ```python
    Literal["workspace", "package"]
    ```
  * Use `"workspace"` for workflows under:

    ```text
    {workspace}/.autoloop/workflows/
    ```
  * Use `"package"` for workflows under:

    ```text
    autoloop/workflows/
    ```
  * Do not use mixed terms such as `"bundled"`, `"packaged"`, or `"installed"` in persisted metadata or API return values.

* **Workflow search roots**

  * Add a workflow-root abstraction:

    ```python
    @dataclass(frozen=True, slots=True)
    class WorkflowSearchRoot:
        kind: Literal["workspace", "package"]
        path: Path
        import_prefix: str | None
        precedence: int
    ```
  * Implement:

    ```python
    def workspace_workflows_root(workspace_root: Path) -> Path:
        return workspace_root.resolve() / ".autoloop" / "workflows"
    ```
  * Implement:

    ```python
    def package_workflows_root() -> Path:
        from importlib.resources import files
        return Path(str(files("autoloop") / "workflows")).resolve()
    ```
  * Implement:

    ```python
    def workflow_search_roots(workspace_root: str | Path) -> tuple[WorkflowSearchRoot, ...]:
        root = Path(workspace_root).resolve()
        return (
            WorkflowSearchRoot(
                kind="workspace",
                path=workspace_workflows_root(root),
                import_prefix=None,
                precedence=100,
            ),
            WorkflowSearchRoot(
                kind="package",
                path=package_workflows_root(),
                import_prefix="autoloop.workflows",
                precedence=10,
            ),
        )
    ```
  * Missing search roots are allowed.
  * Existing search roots that are not directories are hard errors.
  * Do not derive workflow search roots from runtime state directory settings.

* **Supported workflow layouts**

  * Package-installed workflows must use package directories:

    ```text
    autoloop/workflows/<workflow_id>/
      __init__.py
      workflow.toml
      flow.py
      prompts/
      assets/
      docs.md optional
      params.py optional
      specs.py optional
      contracts.py optional
      tests/ optional
    ```
  * `workflow.py` may be supported as an alternative to `flow.py`, but prefer `flow.py` in scaffolds and docs.
  * Workspace-local workflows may use package directories:

    ```text
    {workspace}/.autoloop/workflows/<workflow_id>/
      workflow.toml optional
      flow.py or workflow.py
      prompts/ optional
      assets/ optional
      docs.md optional
      params.py optional
      specs.py optional
      contracts.py optional
      tests/ optional
    ```
  * Workspace-local workflows may also use single-file form:

    ```text
    {workspace}/.autoloop/workflows/<workflow_id>.py
    ```
  * Do not support single-file package-installed workflows.

* **Package structure**

  * Add:

    ```text
    autoloop/workflows/__init__.py
    ```
  * Place all built-in workflows under:

    ```text
    autoloop/workflows/<workflow_id>/
    ```
  * Each package-installed workflow should expose its main workflow class from:

    ```text
    autoloop/workflows/<workflow_id>/__init__.py
    ```
  * Each package-installed workflow package should define `__all__` and include its exported workflow class.
  * If a package-installed workflow exposes `Params`, include `"Params"` in `__all__`.

* **Packaging metadata**

  * Add or update `pyproject.toml`:

    ```toml
    [project.scripts]
    autoloop = "autoloop.runtime.cli:main"

    [tool.setuptools.packages.find]
    include = ["autoloop*", "autoloop_optimizer*"]

    [tool.setuptools.package-data]
    autoloop = [
      "workflows/**/*",
    ]
    ```
  * Add `MANIFEST.in`:

    ```text
    recursive-include autoloop/workflows *
    ```
  * Exclude runtime state, generated runs, caches, and test outputs from package data:

    ```text
    .autoloop/
    __pycache__/
    .pytest_cache/
    .mypy_cache/
    .ruff_cache/
    dist/
    build/
    *.egg-info/
    ```

* **Workflow manifest requirements**

  * `workflow.toml` should define, at minimum:

    ```toml
    name = "<workflow_name>"
    title = "<human readable title>"
    description = "<short description>"
    ```
  * Optional manifest fields:

    ```toml
    aliases = ["alias_a", "alias_b"]
    module = "flow"
    class = "WorkflowClassName"
    ```
  * If `module` is omitted, load `flow.py` first, then `workflow.py`.
  * If `class` is omitted, discover exactly one workflow class in the module.
  * If zero or multiple workflow classes are found, fail with a clear validation error.

* **Catalog entry model**

  * Extend or define catalog entries with:

    ```python
    @dataclass(frozen=True, slots=True)
    class WorkflowCatalogEntry:
        workflow_name: str
        title: str
        description: str
        aliases: tuple[str, ...]
        package_name: str
        package_dir: Path
        manifest_path: Path | None
        source_path: Path
        source_root_kind: Literal["workspace", "package"]
        source_root: Path
        import_prefix: str | None
        precedence: int
        package_module: str | None
        workflow_module: str | None
        authoring_shape: str
        prompts_dir: Path | None
        assets_dir: Path | None
        docs_path: Path | None
        params_path: Path | None
        specs_path: Path | None
        contracts_path: Path | None
        tests_dir: Path | None
        shadowed: bool = False
        shadowed_by: str | None = None
    ```
  * For package-installed workflows:

    * `source_root_kind == "package"`.
    * `import_prefix == "autoloop.workflows"`.
    * `package_module == "autoloop.workflows.<workflow_id>"`.
    * `workflow_module == "autoloop.workflows.<workflow_id>.flow"` or `"autoloop.workflows.<workflow_id>.workflow"`.
  * For workspace-local workflows:

    * `source_root_kind == "workspace"`.
    * `import_prefix is None`.
    * `package_module is None`.
    * `workflow_module is None`.
    * Load by filesystem path.

* **Catalog discovery API**

  * Implement:

    ```python
    def discover_workflow_catalog(
        workspace_root: str | Path,
        *,
        include_shadowed: bool = False,
    ) -> tuple[WorkflowCatalogEntry, ...]:
        ...
    ```
  * Default behavior:

    * Return only the effective catalog.
    * Effective catalog means workspace entries shadow package entries on key collision.
  * When `include_shadowed=True`:

    * Return effective entries plus shadowed package entries.
    * Mark shadowed entries:

      ```python
      shadowed=True
      shadowed_by="<workspace workflow name or path>"
      ```
  * Catalog discovery must scan only:

    ```text
    autoloop/workflows/
    {workspace}/.autoloop/workflows/
    ```
  * Discovery shapes:

    * Directory workflow with manifest:

      ```text
      <root>/<workflow_id>/workflow.toml
      ```
    * Directory workflow without manifest:

      ```text
      <root>/<workflow_id>/flow.py
      ```

      or:

      ```text
      <root>/<workflow_id>/workflow.py
      ```
    * Workspace-only single-file workflow:

      ```text
      {workspace}/.autoloop/workflows/<workflow_id>.py
      ```

* **Resolution-key semantics**

  * A resolution key is either:

    * A workflow name.
    * A workflow alias.
  * Normalize keys by stripping surrounding whitespace.
  * Empty names or aliases are invalid.
  * Resolution order:

    ```text
    1. workspace workflow name
    2. workspace workflow alias
    3. package workflow name
    4. package workflow alias
    ```
  * Within the same source tier, any key collision is an error.
  * These same-tier collisions must fail:

    ```text
    workflow A name == workflow B name
    workflow A name == workflow B alias
    workflow A alias == workflow B alias
    ```
  * Across tiers, workspace keys shadow package keys.
  * Cross-tier collisions must not fail.

* **Bare workflow reference resolution**

  * Implement bare-name resolution through `discover_workflow_catalog(workspace_root)`.
  * Bare references must not probe arbitrary filesystem paths.
  * Bare references must not look under:

    ```text
    {workspace}/workflows/
    ```
  * If no catalog key matches, fail with:

    * The requested name.
    * The workspace root.
    * The searched roots.
  * If same-tier ambiguity exists, fail with:

    * The duplicated key.
    * The source tier.
    * All conflicting workflow paths.
  * If a workspace workflow shadows a package workflow, resolve to the workspace workflow.

* **Explicit filesystem path resolution**

  * Explicit paths are allowed as a general feature.
  * A reference is explicit if it contains a path separator or ends in `.py` or `.toml`.
  * Explicit paths bypass catalog name/alias precedence.
  * Explicit paths may point anywhere readable.
  * Explicit path workflows should still produce normal workflow origin metadata.
  * Explicit path workflows outside the two search roots should use:

    ```python
    source_root_kind = "workspace"
    package_module = None
    workflow_module = None
    ```

    unless a more precise source kind is available.

* **Workspace-local import behavior**

  * Workspace-local workflow packages must support relative imports:

    ```python
    from .specs import State
    from .params import Params
    from .contracts import Output
    ```
  * Do not add `.autoloop` to `sys.path`.
  * Load workspace-local workflows using deterministic isolated module names.
  * Isolated module names should include:

    * A stable prefix.
    * A sanitized workflow id.
    * A hash of the package path.
  * Example:

    ```text
    _autoloop_workspace_workflows.<hash>.<workflow_id>.flow
    ```
  * Workspace-local module reload should invalidate only that workflow’s isolated module namespace.

* **Package workflow import behavior**

  * Package-installed workflows must import through normal Python imports:

    ```python
    autoloop.workflows.<workflow_id>
    autoloop.workflows.<workflow_id>.flow
    ```
  * Do not evict `autoloop.*` broadly from `sys.modules`.
  * Do not delete `__pycache__` under installed package directories.
  * Export validation applies to package-installed workflow packages:

    * The package must import.
    * The main workflow class must be exported from package `__init__.py`.
    * `__all__` must contain the main workflow class name.
    * If `Params` exists and is exported, `__all__` must contain `"Params"`.

* **Workflow loading API**

  * The resolved workflow object should include:

    ```python
    @dataclass(frozen=True, slots=True)
    class ResolvedWorkflow:
        workflow_cls: type
        params_cls: type | None
        reference: str
        workflow_name: str
        class_name: str
        authoring_shape: str
        source_path: Path
        package_dir: Path
        manifest_path: Path | None
        source_root_kind: Literal["workspace", "package"]
        source_root: Path | None
        package_name: str | None
        package_module: str | None
        workflow_module: str | None
    ```
  * Manifest-backed workflows should load through the manifest loader.
  * Non-manifest Python workflows should load through the Python source loader.
  * Package workflows should prefer module import.
  * Workspace workflows should prefer filesystem loading.

* **Runtime workspace metadata**

  * The runtime workflow workspace object should include:

    ```python
    source_root_kind: Literal["workspace", "package"]
    source_root: Path | None
    package_name: str | None
    package_module: str | None
    workflow_module: str | None
    ```
  * Persist workflow origin metadata in run/task metadata:

    ```json
    {
      "name": "...",
      "reference": "...",
      "authoring_shape": "...",
      "module_name": "...",
      "class_name": "...",
      "source_path": "...",
      "manifest_path": "...",
      "package_folder": "...",
      "source_root_kind": "workspace",
      "source_root": "...",
      "package_name": "...",
      "package_module": null,
      "workflow_module": null
    }
    ```
  * `package_folder` must be:

    * Package-installed workflow:

      ```text
      .../site-packages/autoloop/workflows/<workflow_id>
      ```
    * Workspace-local workflow:

      ```text
      {workspace}/.autoloop/workflows/<workflow_id>
      ```
  * Runtime must reference workflow source in place.
  * Runtime must not copy workflow source packages into task/run directories.

* **CLI behavior**

  * Global command:

    ```bash
    autoloop
    ```

    must be installed through the package script entry point.
  * `--root` help text:

    ```text
    Workspace root. Package workflows are loaded from the installed autoloop package; workspace workflows are loaded from .autoloop/workflows/.
    ```
  * Workflow scaffold command must create:

    ```text
    {workspace}/.autoloop/workflows/<workflow_id>/
    ```
  * Scaffold should generate:

    ```text
    workflow.toml
    flow.py
    prompts/
    assets/
    ```
  * Scaffold should not create:

    ```text
    {workspace}/workflows/
    ```
  * `autoloop workflows list` should show the effective catalog by default.
  * `autoloop workflows list --all` should include shadowed package workflows.
  * JSON output for `workflows list` must include:

    ```json
    {
      "name": "...",
      "title": "...",
      "description": "...",
      "aliases": [],
      "authoring_shape": "...",
      "source_path": "...",
      "package_folder": "...",
      "source_root_kind": "workspace",
      "shadowed": false,
      "shadowed_by": null
    }
    ```
  * JSON output for `workflows show` must include:

    ```json
    {
      "name": "...",
      "source_root_kind": "workspace",
      "source_root": "...",
      "package_folder": "...",
      "package_module": null,
      "workflow_module": null,
      "source_path": "...",
      "manifest_path": "...",
      "shadowed": false,
      "shadowed_by": null
    }
    ```

* **Capability inspection**

  * Capability inspection must use the effective workflow catalog by default.
  * Capability inspection must support both source kinds:

    * `"package"`: import by normal module name.
    * `"workspace"`: load by filesystem path.
  * Capability inspection must not assume a top-level `workflows` import package.
  * Capability inspection must not scan `{workspace}/workflows`.
  * Capability inspection may expose shadowed workflows only if explicitly requested.

* **Validation**

  * Validate every discovered workflow entry:

    * Non-empty workflow name.
    * Non-empty package name.
    * Existing source file.
    * Existing package directory.
    * Valid manifest if present.
    * Valid aliases.
    * No duplicate keys within the same source tier.
  * Validate package workflows:

    * Package has `__init__.py`.
    * Package imports successfully.
    * Workflow module imports successfully.
    * Main workflow class is exported from package.
  * Validate workspace workflows:

    * Source file exists.
    * Directory package source has `flow.py` or `workflow.py`.
    * Relative imports work.
  * Validation errors must include concrete paths.

* **Documentation**

  * Document workflow sources:

    ```text
    Package workflows: autoloop/workflows/
    Workspace workflows: {workspace}/.autoloop/workflows/
    ```
  * Document precedence:

    ```text
    Workspace workflow names and aliases override package workflow names and aliases.
    ```
  * Document that `{workspace}/workflows/` is not a workflow discovery root.
  * Document scaffold output under:

    ```text
    .autoloop/workflows/
    ```
  * Document package workflow authoring requirements:

    * Package directory.
    * `workflow.toml`.
    * `flow.py`.
    * `__init__.py`.
    * Exported workflow class.

* **Tests: root discovery**

  * Test `workflow_search_roots(tmp_path)` returns exactly:

    ```text
    tmp_path/.autoloop/workflows
    autoloop/workflows
    ```
  * Test workspace root comes before package root.
  * Test `{workspace}/workflows` is absent.
  * Test missing roots do not fail.
  * Test existing non-directory roots fail.

* **Tests: package discovery**

  * Test `import autoloop.workflows` succeeds.
  * Test at least one package workflow imports as:

    ```python
    autoloop.workflows.<workflow_id>
    ```
  * Test package workflow catalog entries have:

    ```python
    source_root_kind == "package"
    package_module is not None
    workflow_module is not None
    ```

* **Tests: workspace discovery**

  * Test directory workflow under:

    ```text
    tmp/.autoloop/workflows/local_demo/flow.py
    ```

    is discovered.
  * Test manifest-backed workspace workflow is discovered.
  * Test single-file workspace workflow is discovered.
  * Test workspace entries have:

    ```python
    source_root_kind == "workspace"
    package_module is None
    workflow_module is None
    ```

* **Tests: precedence**

  * Test workspace workflow name shadows package workflow name.
  * Test workspace workflow alias shadows package workflow name.
  * Test workspace workflow name shadows package workflow alias.
  * Test workspace workflow alias shadows package workflow alias.
  * Test `discover_workflow_catalog(root)` returns only the workspace entry for shadowed keys.
  * Test `discover_workflow_catalog(root, include_shadowed=True)` returns shadowed package entries marked with:

    ```python
    shadowed=True
    shadowed_by is not None
    ```

* **Tests: duplicate handling**

  * Same source tier duplicate name fails.
  * Same source tier name-vs-alias collision fails.
  * Same source tier duplicate alias fails.
  * Cross-tier duplicate name does not fail.
  * Cross-tier name-vs-alias collision does not fail.
  * Cross-tier duplicate alias does not fail.
  * Cross-tier collisions resolve to workspace.

* **Tests: reference resolution**

  * Bare package workflow name resolves to package workflow.
  * Bare package alias resolves to package workflow.
  * Bare workspace workflow name resolves to workspace workflow.
  * Bare workspace alias resolves to workspace workflow.
  * Bare duplicate key resolves to workspace workflow.
  * Unknown bare name fails with searched roots listed.
  * Explicit filesystem path resolves independently of catalog keys.

* **Tests: imports**

  * Workspace-local package relative imports work:

    ```python
    from .specs import State
    from .params import Params
    from .contracts import Output
    ```
  * Package workflow export validation passes for valid package.
  * Package workflow export validation fails when class is not exported.
  * Package workflow export validation fails when `__all__` omits the workflow class.

* **Tests: CLI**

  * `autoloop workflows list --root <tmp>` lists package workflows in an empty workspace.
  * Adding `<tmp>/.autoloop/workflows/local_demo` makes `local_demo` appear.
  * Workspace `local_demo` shadows package `local_demo`.
  * `autoloop workflows list --all --root <tmp>` includes shadowed package entries.
  * `autoloop init workflow demo --root <tmp>` writes to:

    ```text
    <tmp>/.autoloop/workflows/demo/
    ```
  * CLI help does not describe `{workspace}/workflows` as a discovery root.

* **Tests: packaging**

  * Build a wheel:

    ```bash
    python -m build
    ```
  * Install the wheel into a clean environment.
  * Verify:

    ```bash
    autoloop --help
    ```
  * Verify package workflows are listed in an empty workspace:

    ```bash
    mkdir -p /tmp/autoloop-empty
    autoloop workflows list --root /tmp/autoloop-empty
    ```
  * Verify package workflow assets are accessible after wheel installation:

    * `workflow.toml`
    * prompt files
    * docs/assets if present.

* **Acceptance criteria**

  * Global command works:

    ```bash
    autoloop --help
    ```
  * Package workflows are discoverable without any workspace-local workflow files.
  * Workspace-local workflows are discoverable from:

    ```text
    {workspace}/.autoloop/workflows/
    ```
  * Workspace-local workflows override package workflows by name or alias.
  * Same-tier name/alias collisions are validation errors.
  * No implicit discovery scans:

    ```text
    {workspace}/workflows/
    ```
  * Package workflow imports use:

    ```text
    autoloop.workflows.<workflow_id>
    ```
  * Workspace workflow imports support relative package imports without adding `.autoloop` to `sys.path`.
  * Runtime metadata records workflow source kind, source root, package folder, source path, package module, and workflow module.
  * Wheel installation includes all package workflow files and assets.
  * All tests pass.
