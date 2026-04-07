"""Generate an HTML monitoring dashboard from collected metrics.

Usage:
    python scripts/generate_dashboard.py metrics.json [--output dashboard.html]
    python scripts/generate_dashboard.py metrics1.json metrics2.json ...
"""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path


def load_metrics(path: Path) -> dict:
    """Load a metrics JSON file. Raises OSError or json.JSONDecodeError on failure."""
    with path.open() as f:
        return json.load(f)


def _status(m: dict) -> str:
    errors = m.get("structure_errors", 0) + m.get("quality_errors", 0)
    score = m.get("consistency_score", 1.0)
    return "PASS" if (errors == 0 and score >= 1.0) else "FAIL"


def _status_color(status: str) -> str:
    return "#2da44e" if status == "PASS" else "#cf222e"


def generate_html(metrics_list: list[dict], *, repo_name: str = "bdf-datastore") -> str:
    """Render an HTML dashboard from a list of metrics dicts (oldest → newest)."""
    latest = metrics_list[-1] if metrics_list else None
    history = metrics_list[-10:] if metrics_list else []

    # --- Latest summary ---
    if latest:
        status = _status(latest)
        color = _status_color(status)
        total = latest["cell_counts"]["total"]
        consistency = f"{latest['consistency_score'] * 100:.1f}%"
        struct_err = latest["structure_errors"]
        qual_err = latest["quality_errors"]
        timestamp = latest["timestamp"][:10]  # date part
        by_contrib = latest["cell_counts"].get("by_contributor", {})

        contrib_rows = "".join(
            f"<tr><td>{c}</td><td>{n}</td></tr>"
            for c, n in sorted(by_contrib.items())
        )
        summary_html = f"""
        <section class="summary">
          <h2>Latest run: <span style="color:{color}">{status}</span></h2>
          <p>Generated: {timestamp}</p>
          <table>
            <tr><th>Metric</th><th>Value</th></tr>
            <tr><td>Total cells</td><td>{total}</td></tr>
            <tr><td>Consistency score</td><td>{consistency}</td></tr>
            <tr><td>Structure errors</td><td>{struct_err}</td></tr>
            <tr><td>Quality errors</td><td>{qual_err}</td></tr>
          </table>
          <h3>Cells by contributor</h3>
          <table>
            <tr><th>Contributor</th><th>Cells</th></tr>
            {contrib_rows}
          </table>
        </section>"""
    else:
        summary_html = "<section class='summary'><p>No data available. N/A</p></section>"

    # --- History table ---
    history_rows = ""
    for m in reversed(history):
        s = _status(m)
        c = _status_color(s)
        ts = m["timestamp"][:10]
        cells = m["cell_counts"]["total"]
        score = f"{m['consistency_score'] * 100:.1f}%"
        errs = m["structure_errors"] + m["quality_errors"]
        history_rows += (
            f'<tr><td>{ts}</td><td style="color:{c};font-weight:bold">{s}</td>'
            f'<td>{cells}</td><td>{score}</td><td>{errs}</td></tr>'
        )

    return f"""<!DOCTYPE html>
<html lang="en">
<head>
  <meta charset="UTF-8">
  <title>{repo_name} Dashboard</title>
  <style>
    body {{ font-family: sans-serif; max-width: 900px; margin: 2rem auto; padding: 0 1rem; }}
    table {{ border-collapse: collapse; width: 100%; margin-bottom: 1rem; }}
    th, td {{ border: 1px solid #ccc; padding: 0.4rem 0.8rem; text-align: left; }}
    th {{ background: #f6f8fa; }}
  </style>
</head>
<body>
  <h1>{repo_name} — Data Quality Dashboard</h1>
  {summary_html}
  <section>
    <h2>History (last {len(history)} runs)</h2>
    <table>
      <tr><th>Date</th><th>Status</th><th>Cells</th><th>Consistency</th><th>Errors</th></tr>
      {history_rows}
    </table>
  </section>
</body>
</html>"""


def main() -> int:
    parser = argparse.ArgumentParser(description="Generate HTML dashboard from metrics.")
    parser.add_argument("metrics", nargs="+", metavar="FILE", help="metrics.json file(s)")
    parser.add_argument("--output", default="dashboard.html", help="Output HTML file.")
    parser.add_argument("--repo-name", default="bdf-datastore")
    args = parser.parse_args()

    all_metrics = []
    for p in args.metrics:
        all_metrics.append(load_metrics(Path(p)))

    html = generate_html(all_metrics, repo_name=args.repo_name)
    Path(args.output).write_text(html)
    print(f"Dashboard written to {args.output}", file=sys.stderr)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
