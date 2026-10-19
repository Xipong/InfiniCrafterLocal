#!/usr/bin/env python3
"""Advisory Python growth report against a Git merge base; never a release gate."""
from __future__ import annotations

import argparse
import ast
from collections import Counter, defaultdict
import hashlib
import json
import sys
from typing import Any

import agentctl

# Starting review thresholds, not correctness claims or mandatory refactor targets.
TARGETS = {"function_lines": 300, "branches": 20, "nesting": 6, "file_function_lines": 2000}
FUNCTIONS = (ast.FunctionDef, ast.AsyncFunctionDef)
SCOPES = (*FUNCTIONS, ast.ClassDef, ast.Lambda)
BLOCKS = (ast.For, ast.AsyncFor, ast.While, ast.With, ast.AsyncWith, ast.Try, ast.Match)


class _Flow(ast.NodeVisitor):
    """Count local decision points and control blocks, excluding nested scopes."""

    def __init__(self) -> None:
        self.depth = self.nesting = self.branches = 0

    def _block(self, nodes: list[ast.stmt]) -> None:
        if not nodes:
            return
        self.depth += 1
        self.nesting = max(self.nesting, self.depth)
        for node in nodes:
            self.visit(node)
        self.depth -= 1

    def visit_If(self, node: ast.If) -> None:
        self.branches += 1
        self.visit(node.test)
        self._block(node.body)
        # An elif/else-if chain is one decision level, not deeper nesting.
        if len(node.orelse) == 1 and isinstance(node.orelse[0], ast.If):
            self.visit(node.orelse[0])
        else:
            self._block(node.orelse)

    def generic_visit(self, node: ast.AST) -> None:
        if isinstance(node, SCOPES):
            return
        if isinstance(node, ast.BoolOp):
            self.branches += len(node.values) - 1
        elif isinstance(node, (ast.For, ast.AsyncFor, ast.While, ast.ExceptHandler, ast.IfExp)):
            self.branches += 1
        elif isinstance(node, ast.comprehension):
            self.branches += 1 + len(node.ifs)
        elif isinstance(node, ast.Match):
            self.branches += len(node.cases)
        block = isinstance(node, BLOCKS)
        self.depth += int(block)
        self.nesting = max(self.nesting, self.depth)
        super().generic_visit(node)
        self.depth -= int(block)


def measure(source: str, path: str) -> dict[str, Any]:
    tree = ast.parse(source.lstrip("\ufeff"), filename=path)
    functions: dict[str, Any] = {}
    covered_lines: set[int] = set()
    occurrences: dict[str, int] = defaultdict(int)

    def collect(node: ast.AST, prefix: str = "") -> None:
        if isinstance(node, (*FUNCTIONS, ast.ClassDef)):
            name = prefix + node.name
            if isinstance(node, FUNCTIONS):
                occurrences[name] += 1
                key = name if occurrences[name] == 1 else f"{name}#{occurrences[name]}"
                flow = _Flow()
                for statement in node.body:
                    flow.visit(statement)
                end = node.end_lineno or node.lineno
                covered_lines.update(range(node.lineno, end + 1))
                functions[key] = {
                    "line": node.lineno,
                    "fingerprint": hashlib.sha256(ast.dump(node, include_attributes=False).encode()).hexdigest(),
                    "function_lines": end - node.lineno + 1,
                    "branches": flow.branches,
                    "nesting": flow.nesting,
                }
            prefix = name + "."
        for child in ast.iter_child_nodes(node):
            collect(child, prefix)

    collect(tree)
    return {"functions": functions, "file_function_lines": len(covered_lines)}


def compare(before: dict[str, str], after: dict[str, str]) -> dict[str, Any]:
    baseline = {path: measure(source, path) for path, source in before.items()}
    current = {path: measure(source, path) for path, source in after.items()}
    by_fingerprint: dict[str, list[tuple[str, str, dict[str, Any]]]] = defaultdict(list)
    for path, measured in baseline.items():
        for name, function in measured["functions"].items():
            by_fingerprint[function["fingerprint"]].append((path, name, function))
    current_fingerprints = Counter(function["fingerprint"] for measured in current.values()
                                   for function in measured["functions"].values())
    warnings: list[dict[str, Any]] = []
    files: list[dict[str, Any]] = []
    for path in sorted(baseline.keys() | current.keys()):
        measured = current.get(path, {"functions": {}, "file_function_lines": 0})
        old = baseline.get(path, {"functions": {}, "file_function_lines": 0})
        files.append({"path": path, "beforeFunctionLines": old["file_function_lines"],
                      "afterFunctionLines": measured["file_function_lines"]})
        for name, function in measured["functions"].items():
            previous = old["functions"].get(name)
            baseline_path = path
            # Exact moves retain their old caps when both owners are in scope.
            if previous is None:
                matches = by_fingerprint.get(function["fingerprint"], [])
                if len(matches) == 1 and current_fingerprints[function["fingerprint"]] == 1:
                    baseline_path, _, previous = matches[0]
            for metric in ("function_lines", "branches", "nesting"):
                before_value = previous[metric] if previous else 0
                cap = max(TARGETS[metric], before_value)
                if function[metric] > cap:
                    warnings.append({"path": path, "function": name, "line": function["line"], "metric": metric,
                                     "before": before_value, "after": function[metric], "cap": cap,
                                     "baselinePath": baseline_path if previous else None})
        metric = "file_function_lines"
        cap = max(TARGETS[metric], old[metric])
        if measured[metric] > cap:
            warnings.append({"path": path, "metric": metric, "before": old[metric], "after": measured[metric], "cap": cap})
    return {"files": files, "warnings": warnings}


def _in_scope(path: str) -> bool:
    return (path.endswith(".py") and path.startswith(("LocalGenerator/infini_local/", "tools/", "toolbox/"))
            and "/tests/" not in path and not path.rsplit("/", 1)[-1].startswith(("test_", "conftest.")))


def build_report(base: str, paths: list[str] | None = None) -> dict[str, Any]:
    revision = agentctl.run_git("rev-parse", "--verify", "--end-of-options", base + "^{commit}")
    if revision.returncode:
        raise ValueError(f"code health needs an available Git --base revision: {base}")
    ancestor = agentctl.run_git("merge-base", revision.stdout.strip(), "HEAD")
    if ancestor.returncode:
        raise ValueError(f"no merge base with {base}")
    baseline = ancestor.stdout.strip()
    selected = agentctl.repository_paths(paths, require_files=True) if paths else agentctl.changed_files(base)
    if paths and any(not _in_scope(path) for path in selected):
        raise ValueError("--path must select Python implementation files under LocalGenerator/infini_local, tools or toolbox")
    selected = agentctl.repository_paths([path for path in selected if _in_scope(path)])
    before: dict[str, str] = {}
    after: dict[str, str] = {}
    if selected:
        listing = agentctl.run_git("ls-tree", "-r", "--name-only", "-z", baseline, "--", *selected)
        if listing.returncode:
            raise ValueError(listing.stderr.strip() or "cannot read baseline tree")
        tracked = set(listing.stdout.split("\0"))
        for path in selected:
            if path in tracked:
                content = agentctl.run_git("show", f"{baseline}:{path}")
                if content.returncode:
                    raise ValueError(content.stderr.strip() or f"cannot read baseline source: {path}")
                before[path] = content.stdout
            target = agentctl.ROOT / path
            if target.is_file():
                after[path] = target.read_text(encoding="utf-8-sig")
    result = compare(before, after)
    return {"schema": "infini.code-health.v1", "advisory": True, "releaseReady": False,
            "status": "warnings" if result["warnings"] else "measured" if selected else "not_selected",
            "comparisonBase": base, "baselineRevision": baseline, "paths": selected, "targets": TARGETS, **result}


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--base", default="HEAD", help="Compare current sources to this merge base (default: HEAD)")
    parser.add_argument("--path", action="append", help="Limit measurement to an existing Python implementation file (repeatable)")
    args = parser.parse_args(argv)
    try:
        report = build_report(args.base, args.path)
    except (ValueError, OSError, SyntaxError) as exc:
        print(json.dumps({"advisory": True, "status": "unavailable", "error": str(exc)}, ensure_ascii=False), file=sys.stderr)
        return 2
    print(json.dumps(report, ensure_ascii=False, indent=2))
    return 0  # Growth is review advice. Parse/Git failures above are not a clean measurement.


if __name__ == "__main__":
    raise SystemExit(main())
