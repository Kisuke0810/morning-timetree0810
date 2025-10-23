#!/usr/bin/env python3
"""
List cron schedules in GitHub Actions workflows.

Outputs file path, workflow name, and cron lines for each *.yml under .github/workflows.
No external dependencies; parses name: and cron: lines heuristically.
"""
from __future__ import annotations

import sys
from pathlib import Path


def extract_workflow_name(lines: list[str]) -> str | None:
    for line in lines:
        # strip comments and trailing newline
        raw = line.rstrip("\n")
        if raw.strip().startswith("#"):
            continue
        if raw.lstrip().startswith("name:"):
            # Keep original after colon
            try:
                return raw.split(":", 1)[1].strip().strip('"')
            except Exception:
                return raw.strip()
    return None


def extract_crons(lines: list[str]) -> list[str]:
    crons: list[str] = []
    for raw in lines:
        # Remove inline comments conservatively
        line_no_comment = raw.split('#', 1)[0]
        line = line_no_comment.strip()
        if line.startswith("#"):
            continue
        if line.startswith("- cron:") or line.startswith("cron:"):
            # Accept both top-level and list-item style
            expr = line.split(":", 1)[1].strip()
            # Trim surrounding quotes if present
            if (expr.startswith('"') and expr.endswith('"')) or (expr.startswith("'") and expr.endswith("'")):
                expr = expr[1:-1]
            if expr:
                crons.append(expr)
    return crons


def main() -> int:
    root = Path(".")
    wf_dir = root / ".github" / "workflows"
    if not wf_dir.is_dir():
        print("No .github/workflows directory found", file=sys.stderr)
        return 1

    files = sorted(wf_dir.glob("*.yml"))
    if not files:
        print("No workflow files found", file=sys.stderr)
        return 1

    print("# GitHub Actions Cron Audit")
    print()
    for path in files:
        text = path.read_text(encoding="utf-8", errors="ignore").splitlines()
        name = extract_workflow_name(text) or "(no name)"
        crons = extract_crons(text)
        print(f"- file: {path}")
        print(f"  name: {name}")
        if crons:
            print("  crons:")
            for c in crons:
                print(f"    - {c}")
        else:
            print("  crons: []")
        print("")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
