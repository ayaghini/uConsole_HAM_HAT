#!/usr/bin/env python3
"""Generate AI onboarding artifacts for this repository.

Outputs:
  - AGENT_CODE_INDEX.json       (machine-readable file/module/class/function index)
  - AGENT_ONBOARDING_PACK.md    (human-readable fast onboarding with key routes)

The goal is to let an AI agent load minimal files/tokens while still
understanding architecture, extension points, and common task routing.
"""

from __future__ import annotations

import ast
import json
from dataclasses import dataclass, asdict
from pathlib import Path
from typing import Any


ROOT = Path(__file__).resolve().parents[1]
TARGET_DIRS = ["app", "scripts"]
ROOT_FILES = ["main.py", "requirements.txt", "VERSION", "AGENT_CONTEXT.json", "PROJECT_COMPONENT_MAP.md"]
SKIP_DIRS = {".venv", "__pycache__", ".git", ".vscode", ".claude"}


@dataclass
class FuncInfo:
    name: str
    lineno: int
    end_lineno: int
    args: list[str]
    decorators: list[str]
    doc: str


@dataclass
class ClassInfo:
    name: str
    lineno: int
    end_lineno: int
    bases: list[str]
    decorators: list[str]
    doc: str
    methods: list[FuncInfo]


@dataclass
class ImportInfo:
    module: str
    names: list[str]
    lineno: int


@dataclass
class FileInfo:
    path: str
    bytes: int
    lines: int
    module_doc: str
    imports: list[ImportInfo]
    constants: list[str]
    functions: list[FuncInfo]
    classes: list[ClassInfo]


def _safe_read(path: Path) -> str:
    return path.read_text(encoding="utf-8", errors="replace")


def _short_doc(node: ast.AST) -> str:
    raw = ast.get_docstring(node) or ""
    first = raw.strip().splitlines()[:2]
    return " ".join(x.strip() for x in first if x.strip())


def _unparse(node: ast.AST | None) -> str:
    if node is None:
        return ""
    try:
        return ast.unparse(node)
    except Exception:
        return ""


def _decorators(node: ast.AST) -> list[str]:
    decs = []
    for d in getattr(node, "decorator_list", []):
        val = _unparse(d)
        if val:
            decs.append(val)
    return decs


def _func_info(node: ast.FunctionDef | ast.AsyncFunctionDef) -> FuncInfo:
    args = []
    for a in node.args.args:
        args.append(a.arg)
    if node.args.vararg:
        args.append("*" + node.args.vararg.arg)
    for a in node.args.kwonlyargs:
        args.append(a.arg)
    if node.args.kwarg:
        args.append("**" + node.args.kwarg.arg)
    return FuncInfo(
        name=node.name,
        lineno=node.lineno,
        end_lineno=getattr(node, "end_lineno", node.lineno),
        args=args,
        decorators=_decorators(node),
        doc=_short_doc(node),
    )


def _class_info(node: ast.ClassDef) -> ClassInfo:
    methods: list[FuncInfo] = []
    for n in node.body:
        if isinstance(n, (ast.FunctionDef, ast.AsyncFunctionDef)):
            methods.append(_func_info(n))
    return ClassInfo(
        name=node.name,
        lineno=node.lineno,
        end_lineno=getattr(node, "end_lineno", node.lineno),
        bases=[_unparse(b) for b in node.bases if _unparse(b)],
        decorators=_decorators(node),
        doc=_short_doc(node),
        methods=methods,
    )


def _imports(tree: ast.Module) -> list[ImportInfo]:
    out: list[ImportInfo] = []
    for n in tree.body:
        if isinstance(n, ast.Import):
            out.append(
                ImportInfo(
                    module="",
                    names=[x.name for x in n.names],
                    lineno=n.lineno,
                )
            )
        elif isinstance(n, ast.ImportFrom):
            out.append(
                ImportInfo(
                    module=n.module or "." * n.level,
                    names=[x.name for x in n.names],
                    lineno=n.lineno,
                )
            )
    return out


def _constants(tree: ast.Module) -> list[str]:
    out: list[str] = []
    for n in tree.body:
        if isinstance(n, ast.Assign):
            for t in n.targets:
                if isinstance(t, ast.Name) and t.id.isupper():
                    out.append(t.id)
        elif isinstance(n, ast.AnnAssign):
            t = n.target
            if isinstance(t, ast.Name) and t.id.isupper():
                out.append(t.id)
    return sorted(set(out))


def analyze_python_file(path: Path) -> FileInfo | None:
    text = _safe_read(path)
    try:
        tree = ast.parse(text)
    except SyntaxError:
        return None

    funcs: list[FuncInfo] = []
    classes: list[ClassInfo] = []
    for n in tree.body:
        if isinstance(n, (ast.FunctionDef, ast.AsyncFunctionDef)):
            funcs.append(_func_info(n))
        elif isinstance(n, ast.ClassDef):
            classes.append(_class_info(n))

    return FileInfo(
        path=str(path.relative_to(ROOT)).replace("\\", "/"),
        bytes=path.stat().st_size,
        lines=text.count("\n") + 1,
        module_doc=_short_doc(tree),
        imports=_imports(tree),
        constants=_constants(tree),
        functions=funcs,
        classes=classes,
    )


def iter_python_files() -> list[Path]:
    out: list[Path] = []
    for d in TARGET_DIRS:
        base = ROOT / d
        if not base.exists():
            continue
        for p in base.rglob("*.py"):
            if any(part in SKIP_DIRS for part in p.parts):
                continue
            out.append(p)
    root_main = ROOT / "main.py"
    if root_main.exists():
        out.append(root_main)
    return sorted(set(out))


def build_index() -> dict[str, Any]:
    file_infos: list[dict[str, Any]] = []
    function_total = 0
    class_total = 0
    method_total = 0

    for p in iter_python_files():
        info = analyze_python_file(p)
        if info is None:
            continue
        function_total += len(info.functions)
        class_total += len(info.classes)
        method_total += sum(len(c.methods) for c in info.classes)
        file_infos.append(asdict(info))

    file_infos.sort(key=lambda x: x["path"])

    # Component groups by path prefix
    component_groups = {
        "app_core": [f["path"] for f in file_infos if f["path"].startswith("app/") and "/ui/" not in f["path"] and "/engine/" not in f["path"]],
        "engine": [f["path"] for f in file_infos if f["path"].startswith("app/engine/")],
        "ui": [f["path"] for f in file_infos if f["path"].startswith("app/ui/")],
        "scripts": [f["path"] for f in file_infos if f["path"].startswith("scripts/")],
        "entry": [f["path"] for f in file_infos if f["path"] == "main.py"],
    }

    return {
        "project": "HAM HAT Control Center v2",
        "generated_by": "scripts/generate_agent_onboarding_pack.py",
        "root": str(ROOT),
        "summary": {
            "python_files": len(file_infos),
            "top_level_functions": function_total,
            "classes": class_total,
            "class_methods": method_total,
        },
        "root_files_present": [f for f in ROOT_FILES if (ROOT / f).exists()],
        "component_groups": component_groups,
        "files": file_infos,
    }


def build_markdown(index: dict[str, Any]) -> str:
    summary = index["summary"]
    lines: list[str] = []
    lines.append("# Agent Onboarding Pack")
    lines.append("")
    lines.append("This file is generated. Rebuild with:")
    lines.append("`python scripts/generate_agent_onboarding_pack.py`")
    lines.append("")
    lines.append("## Project Snapshot")
    lines.append("")
    lines.append(f"- Project: `{index['project']}`")
    lines.append(f"- Python files indexed: `{summary['python_files']}`")
    lines.append(f"- Top-level functions: `{summary['top_level_functions']}`")
    lines.append(f"- Classes: `{summary['classes']}`")
    lines.append(f"- Class methods: `{summary['class_methods']}`")
    lines.append("")
    lines.append("## Fast Read Order")
    lines.append("")
    fast = [
        "main.py",
        "app/app.py",
        "app/app_state.py",
        "app/engine/models.py",
        "app/engine/aprs_engine.py",
        "app/engine/aprs_modem.py",
        "app/engine/radio_ctrl.py",
        "app/engine/sa818_client.py",
        "app/ui/comms_tab.py",
        "app/ui/aprs_tab.py",
        "app/ui/main_tab.py",
    ]
    for f in fast:
        lines.append(f"- `{f}`")
    lines.append("")
    lines.append("## Component File Lists")
    lines.append("")
    for group, files in index["component_groups"].items():
        lines.append(f"### {group}")
        lines.append("")
        for f in files:
            lines.append(f"- `{f}`")
        lines.append("")
    lines.append("## Class and Function Index")
    lines.append("")
    for f in index["files"]:
        lines.append(f"### {f['path']}")
        lines.append("")
        if f["module_doc"]:
            lines.append(f"- Module: {f['module_doc']}")
        lines.append(f"- Size: `{f['lines']} lines`, `{f['bytes']} bytes`")
        if f["constants"]:
            lines.append(f"- Constants: `{', '.join(f['constants'])}`")
        if f["classes"]:
            lines.append("- Classes:")
            for c in f["classes"]:
                base = f" ({', '.join(c['bases'])})" if c["bases"] else ""
                lines.append(f"  - `{c['name']}`{base}  [L{c['lineno']}]")
                for m in c["methods"]:
                    arg_s = ", ".join(m["args"])
                    lines.append(f"    - `{m['name']}({arg_s})`  [L{m['lineno']}]")
        if f["functions"]:
            lines.append("- Top-level functions:")
            for fn in f["functions"]:
                arg_s = ", ".join(fn["args"])
                lines.append(f"  - `{fn['name']}({arg_s})`  [L{fn['lineno']}]")
        lines.append("")
    return "\n".join(lines).rstrip() + "\n"


def main() -> int:
    index = build_index()
    json_path = ROOT / "AGENT_CODE_INDEX.json"
    md_path = ROOT / "AGENT_ONBOARDING_PACK.md"
    json_path.write_text(json.dumps(index, indent=2), encoding="utf-8")
    md_path.write_text(build_markdown(index), encoding="utf-8")
    print(f"[ok] wrote {json_path.name}")
    print(f"[ok] wrote {md_path.name}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

