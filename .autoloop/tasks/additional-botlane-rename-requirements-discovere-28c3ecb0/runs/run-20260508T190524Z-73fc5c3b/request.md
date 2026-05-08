Additional Botlane rename requirements discovered from repository review

1. Public API symbol policy
   Rename branded public API symbols, not only package paths:
   - Autoloop -> Botlane
   - AutoloopSDKError -> BotlaneSDKError
   - Any Autoloop-prefixed public exception, facade, result helper, debug helper, or exported symbol must become Botlane-prefixed.
   - Update __all__ exports accordingly.
   - Do not keep Autoloop as an alias to Botlane.

2. Runtime and CLI identity
   Update every CLI parser, help string, command description, runtime message, package-loading description, and workspace-loading description:
   - prog="autoloop" -> prog="botlane"
   - "filesystem autoloop runtime" -> "filesystem Botlane runtime"
   - "installed autoloop package" -> "installed botlane package"
   - ".autoloop/workflows/" -> ".botlane/workflows/"
   - console executable autoloop -> botlane
   Remove any installed `autoloop` executable.

3. Workspace, generated module, and dynamic import identity
   Rename all internal/generated module namespaces and workspace prefixes:
   - _autoloop_workspace_workflows -> _botlane_workspace_workflows
   - autoloop.workflows -> botlane.workflows
   - autoloop.core... -> botlane.core...
   - autoloop.runtime... -> botlane.runtime...
   - autoloop_optimizer... -> botlane_optimizer...
   This includes importlib calls, sys.modules cleanup, module-cache keys, workflow catalog roots, workflow fixture strings, and generated workflow source code.

4. Schema and artifact identity
   Update all schema identifiers and generated artifact schemas that use the product prefix:
   - autoloop.branch_results/v1 -> botlane.branch_results/v1
   - autoloop.git_tracking/v1 -> botlane.git_tracking/v1
   - autoloop.workflow_static_step_graph/v1 -> botlane.workflow_static_step_graph/v1
   - any other autoloop.* schema -> botlane.*
   Do not rename unrelated schema prefixes such as docloop.* unless they are intentionally product-branded in the target design.

5. Legacy removal
   Delete legacy compatibility modules and commands rather than renaming them:
   - Remove legacy import modules.
   - Remove import-legacy CLI commands.
   - Remove .superloop migration/import references.
   - Remove dry-run/rollback compatibility flags whose only purpose was legacy import compatibility.
   - Remove tests that assert unsupported legacy behavior still exists.

6. Test fixture rewrite
   Rewrite not only normal imports but also embedded workflow source strings inside tests, docs, examples, and fixtures. Any string that would generate a user-facing example or importable workflow must use botlane.

7. Negative strictness tests
   Add or update strictness tests proving:
   - import autoloop fails.
   - import autoloop_optimizer fails.
   - python -m autoloop fails or is absent.
   - autoloop CLI is not installed.
   - botlane CLI is installed and help text contains botlane, not autoloop.
   - generated workspaces use .botlane only.
   - generated schemas use botlane.* only.
   - repository grep has no active autoloop, Autoloop, AUTOLOOP, .autoloop, autoloop_optimizer, or _autoloop_workspace_workflows references outside explicit historical changelog text.
   
   Casing policy

Use `Botlane` only for human-facing prose and CapWords Python symbols:
- Botlane
- BotlaneSDKError
- BotlaneExecutionError, if such branded symbols exist

Use `botlane` for every machine-facing identifier:
- import botlane
- from botlane import ...
- botlane_optimizer
- pip install botlane
- botlane CLI command
- .botlane runtime directory
- botlane.* schema IDs
- botlane-* marker/header prefixes
- botlane/ filesystem paths
- botlane package metadata
- botlane docs URLs, examples, generated paths, and serialized metadata

Use `BOTLANE` only for constants and environment variables:
- BOTLANE_HOME
- BOTLANE_PROVIDER
- BOTLANE_CONFIG
