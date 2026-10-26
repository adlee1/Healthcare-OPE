"""Generate a source-linked Python symbol index without importing project modules."""
from __future__ import annotations

import ast
import hashlib
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
OUTPUT = ROOT / "docs" / "FUNCTION_INDEX.md"


def escape(value: str) -> str:
    return value.replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;").replace("|", "&#124;").replace("`", "&#96;")


def source_files() -> list[Path]:
    return sorted([
        *ROOT.glob("*.py"),
        *(ROOT / "src").rglob("*.py"),
        *(ROOT / "scripts").rglob("*.py"),
        *(ROOT / "tests").rglob("*.py"),
    ], key=lambda path: path.relative_to(ROOT).as_posix())


def symbols(tree: ast.AST) -> list[tuple[int, str, str, str]]:
    records = []

    def visit(node: ast.AST, parents: tuple[str, ...] = ()) -> None:
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef)):
            name = ".".join((*parents, node.name))
            if isinstance(node, ast.ClassDef):
                signature = name + "(" + ", ".join(ast.unparse(base) for base in node.bases) + ")"
                kind = "class"
            else:
                signature = name + "(" + ast.unparse(node.args) + ")"
                if node.returns:
                    signature += " -> " + ast.unparse(node.returns)
                kind = "async function" if isinstance(node, ast.AsyncFunctionDef) else "function/method"
            records.append((node.lineno, kind, signature, (ast.get_docstring(node) or "").split("\n\n", 1)[0]))
            parents = (*parents, node.name)
        for child in ast.iter_child_nodes(node):
            visit(child, parents)

    visit(tree)
    return sorted(records)


def generate() -> str:
    entries = []
    for path in source_files():
        relative = path.relative_to(ROOT).as_posix()
        tree = ast.parse(path.read_text(encoding="utf-8"), filename=relative)
        anchor = "module-" + hashlib.sha256(relative.encode()).hexdigest()[:12]
        entries.append((relative, anchor, ast.get_docstring(tree) or "", symbols(tree)))
    lines = [
        "# Python function and class index", "",
        "Start with [CODE_GUIDE.md](CODE_GUIDE.md) for model roles, execution entry points, and the development workflow.", "",
        f"This generated index covers **{len(entries)} Python files** and **{sum(len(entry[3]) for entry in entries)} named definitions** in root scripts, `scripts/`, `src/`, and `tests/`.", "",
        "Every named function, method, nested function, and class is included. Click a source line to read its implementation. The descriptions below are existing source docstrings, not inferred documentation; a blank description means no docstring is present. Anonymous lambdas and dynamically assigned callables are outside this static index.", "",
        "Regenerate after source edits with `python scripts/generate_code_index.py`. The generator parses syntax only: it does not import project modules, load clinical data, train models, or call APIs.", "",
        "## File navigation", "", "| File | Definitions |", "|---|---:|",
    ]
    for relative, anchor, _, records in entries:
        lines.append(f"| [{relative}](#{anchor}) | {len(records)} |")
    for relative, anchor, doc, records in entries:
        lines.extend(["", f'<a id="{anchor}"></a>', "", f"## {relative}", "", f"[Open source](../{relative})", ""])
        if doc:
            lines.extend(["Source module docstring:", "", "> " + escape(" ".join(doc.split())), ""])
        if not records:
            lines.append("No named function or class definitions in this file.")
            continue
        lines.extend(["| Source | Kind | Signature | Existing docstring |", "|---|---|---|---|"])
        for line, kind, signature, description in records:
            lines.append(f"| [L{line}](../{relative}#L{line}) | {kind} | <code>{escape(signature)}</code> | {escape(' '.join(description.split()))} |")
    return "\n".join(lines) + "\n"


if __name__ == "__main__":
    OUTPUT.write_text(generate(), encoding="utf-8")
    print(OUTPUT.relative_to(ROOT).as_posix())
