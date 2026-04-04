"""Health check endpoint for bdf-datastore CI monitoring.

Produces a structured health report with status: healthy | degraded | critical.

Usage:
    python scripts/health_check.py [repo-root] [--json]
"""
from __future__ import annotations

import argparse
import datetime
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))

from validate_structure import validate as validate_structure
from validate_quality import validate_quality
from collect_metrics import collect_cell_counts, compute_consistency_score

EXIT_CODES: dict[str, int] = {
    "healthy": 0,
    "degraded": 1,
    "critical": 2,
}


def run_health_check(root: Path) -> dict:
    """Run all validations and return a health report dict."""
    struct_errors, struct_warnings = validate_structure(root)
    qual_errors, qual_warnings = validate_quality(root)

    counts = collect_cell_counts(root)
    consistency_score = compute_consistency_score(root)

    if struct_errors or qual_errors:
        status = "critical"
    elif struct_warnings or qual_warnings:
        status = "degraded"
    else:
        status = "healthy"

    return {
        "status": status,
        "timestamp": datetime.datetime.now(datetime.timezone.utc).isoformat(),
        "cell_count": counts["total"],
        "structure_errors": len(struct_errors),
        "structure_warnings": len(struct_warnings),
        "quality_errors": len(qual_errors),
        "quality_warnings": len(qual_warnings),
        "consistency_score": consistency_score,
        "issues": struct_errors + qual_errors,
        "warnings": struct_warnings + qual_warnings,
    }


def format_health_summary(report: dict) -> str:
    """Render a concise human-readable health summary."""
    status = report["status"].upper()
    lines = [
        f"[{status}] {report['cell_count']} cell(s) — "
        f"consistency {report['consistency_score'] * 100:.1f}%  "
        f"errors={report['structure_errors'] + report['quality_errors']}  "
        f"warnings={report['structure_warnings'] + report['quality_warnings']}",
    ]
    for issue in report["issues"]:
        lines.append(f"  ERROR  {issue}")
    for warning in report["warnings"]:
        lines.append(f"  WARN   {warning}")
    return "\n".join(lines)


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Health check for bdf-datastore."
    )
    parser.add_argument("root", nargs="?", default=".", help="Repository root.")
    parser.add_argument("--json", action="store_true", help="Output JSON.")
    args = parser.parse_args()

    root = Path(args.root).resolve()
    report = run_health_check(root)

    if args.json:
        print(json.dumps(report, indent=2))
    else:
        print(format_health_summary(report))

    return EXIT_CODES[report["status"]]


if __name__ == "__main__":
    raise SystemExit(main())
