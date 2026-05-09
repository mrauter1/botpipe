from __future__ import annotations

import ast
from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parents[2]
CORE_ROOT = REPO_ROOT / "botlane" / "core"


def test_botlane_core_has_no_runtime_imports_outside_type_checking() -> None:
    violations: list[str] = []
    for path in sorted(CORE_ROOT.rglob("*.py")):
        tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
        violations.extend(_runtime_import_violations(tree, path))

    assert not violations, "\n".join(violations)


def _runtime_import_violations(tree: ast.AST, path: Path) -> list[str]:
    violations: list[str] = []

    def visit(node: ast.AST, *, in_type_checking: bool) -> None:
        if isinstance(node, ast.If) and _is_type_checking_guard(node.test):
            for child in node.body:
                visit(child, in_type_checking=True)
            for child in node.orelse:
                visit(child, in_type_checking=in_type_checking)
            return

        if not in_type_checking:
            if isinstance(node, ast.Import):
                for alias in node.names:
                    if alias.name == "botlane.runtime" or alias.name.startswith("botlane.runtime."):
                        violations.append(f"{path.relative_to(REPO_ROOT)} imports {alias.name}")
            elif isinstance(node, ast.ImportFrom):
                module = node.module or ""
                if module == "botlane.runtime" or module.startswith("botlane.runtime."):
                    violations.append(f"{path.relative_to(REPO_ROOT)} imports from {module}")
                elif node.level >= 1 and (module == "runtime" or module.startswith("runtime.")):
                    violations.append(
                        f"{path.relative_to(REPO_ROOT)} uses relative runtime import level={node.level} module={module!r}"
                    )
                elif node.level >= 1 and not module:
                    for alias in node.names:
                        if alias.name == "runtime":
                            violations.append(
                                f"{path.relative_to(REPO_ROOT)} uses relative runtime import level={node.level}"
                            )

        for child in ast.iter_child_nodes(node):
            visit(child, in_type_checking=in_type_checking)

    visit(tree, in_type_checking=False)
    return violations


def _is_type_checking_guard(expr: ast.AST) -> bool:
    if isinstance(expr, ast.Name):
        return expr.id == "TYPE_CHECKING"
    if isinstance(expr, ast.Attribute):
        return isinstance(expr.value, ast.Name) and expr.value.id == "typing" and expr.attr == "TYPE_CHECKING"
    return False
