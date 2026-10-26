"""
Module  : framework.reporting.executive_report
Author  : Anil Kalisetti
Purpose : Render the management summary as self-contained HTML, Markdown and JSON.

Design goals
    * One page, readable in under a minute: verdict first, evidence second, detail last.
    * Zero external assets (inline CSS + SVG) so the file works as an email attachment or
      CI artifact, even on locked-down networks.
    * Plain language: no stack traces on the front page; those live in the detailed reports.

Outputs written to the reports directory
    executive_summary.html   for stakeholders
    summary.md               for CI job summaries / chat notifications
    summary.json             for dashboards and automation
    history.json             rolling pass-rate history that powers the trend chart
"""

from __future__ import annotations

import html
import json
import os
from collections.abc import Mapping, Sequence
from pathlib import Path
from typing import Any

from framework.reporting.models import CaseResult, RunSummary

_COLORS = {"GREEN": "#1a7f37", "AMBER": "#b7791f", "RED": "#c62828", "NO DATA": "#6b7280"}
_HISTORY_LIMIT = 30

_CSS = """
*{box-sizing:border-box}body{font-family:-apple-system,Segoe UI,Roboto,Arial,sans-serif;margin:0;
background:#f4f6f8;color:#1f2933}main{max-width:1000px;margin:0 auto;padding:24px}
h1{margin:0 0 4px;font-size:22px}h2{font-size:16px;margin:28px 0 10px}
.meta{color:#52606d;font-size:13px}.banner{border-radius:10px;padding:18px 22px;color:#fff;margin:16px 0}
.banner b{font-size:26px;letter-spacing:.5px}.banner p{margin:6px 0 0;font-size:15px}
.kpis{display:grid;grid-template-columns:repeat(auto-fit,minmax(130px,1fr));gap:10px}
.kpi{background:#fff;border-radius:8px;padding:12px 14px;box-shadow:0 1px 2px #0001}
.kpi span{display:block;font-size:12px;color:#52606d}.kpi strong{font-size:22px}
table{width:100%;border-collapse:collapse;background:#fff;border-radius:8px;overflow:hidden;
box-shadow:0 1px 2px #0001;font-size:13px}th,td{padding:8px 10px;text-align:left;
border-bottom:1px solid #e4e7eb;vertical-align:top}th{background:#eef1f4;font-size:12px}
.bar{display:flex;height:10px;border-radius:5px;overflow:hidden;background:#e4e7eb;min-width:140px}
.bar i{display:block;height:100%}.p{background:#1a7f37}.f{background:#c62828}.s{background:#9aa5b1}
.small{font-size:12px;color:#52606d}code{font-size:12px;word-break:break-all}
.note{background:#fff;border-left:4px solid #9aa5b1;padding:10px 14px;font-size:12px;
color:#52606d;margin-top:28px}a{color:#0b5fa5}
"""


def _esc(value: object) -> str:
    return html.escape(str(value), quote=True)


def _fmt_duration(seconds: float) -> str:
    minutes, secs = divmod(int(seconds), 60)
    return f"{minutes}m {secs:02d}s" if minutes else f"{secs}s"


def _bar(counter: Mapping[str, int]) -> str:
    total = sum(counter.values()) or 1
    passed = counter.get("passed", 0)
    failed = counter.get("failed", 0) + counter.get("error", 0)
    other = sum(counter.values()) - passed - failed
    return (
        '<div class="bar">'
        f'<i class="p" style="width:{100 * passed / total:.1f}%"></i>'
        f'<i class="f" style="width:{100 * failed / total:.1f}%"></i>'
        f'<i class="s" style="width:{100 * other / total:.1f}%"></i></div>'
    )


def _sparkline(history: Sequence[Mapping[str, Any]]) -> str:
    """Inline SVG line of pass rate per run (0-100 %)."""
    points = [float(h["pass_rate"]) for h in history][-_HISTORY_LIMIT:]
    if len(points) < 2:
        return '<p class="small">Trend appears after two or more runs with a saved history.</p>'
    width, height, pad = 600, 80, 6
    step = (width - 2 * pad) / (len(points) - 1)
    coords = " ".join(
        f"{pad + i * step:.1f},{height - pad - (p / 100) * (height - 2 * pad):.1f}"
        for i, p in enumerate(points)
    )
    return (
        f'<svg viewBox="0 0 {width} {height}" width="100%" height="80" role="img" '
        'aria-label="Pass rate trend"><rect width="100%" height="100%" fill="#fff"/>'
        f'<polyline fill="none" stroke="#0b5fa5" stroke-width="2" points="{coords}"/></svg>'
        f'<p class="small">Pass rate over the last {len(points)} runs '
        f"(latest {points[-1]:.1f}%, earliest {points[0]:.1f}%).</p>"
    )


def _rel(path: str, base: Path) -> str:
    return os.path.relpath(path, base).replace(os.sep, "/") if path else ""


def _failure_rows(summary: RunSummary, out_dir: Path) -> str:
    rows = []
    for r in summary.failing[:50]:
        shot = (
            f'<a href="{_esc(_rel(r.screenshot, out_dir))}">screenshot</a>' if r.screenshot else ""
        )
        jira = ""
        if r.jira_key:
            base = summary.metadata.jira_base_url.rstrip("/")
            jira = (
                f'<a href="{_esc(base)}/browse/{_esc(r.jira_key)}">{_esc(r.jira_key)}</a>'
                if base
                else _esc(r.jira_key)
            )
        crit = " <strong>(critical)</strong>" if "critical" in r.markers else ""
        rows.append(
            f"<tr><td><strong>{_esc(r.short_name)}</strong>{crit}<br>"
            f'<span class="small"><code>{_esc(r.nodeid)}</code></span></td>'
            f"<td>{_esc(r.layer)}</td><td>{_esc(r.message)}</td><td>{shot}</td><td>{jira}</td></tr>"
        )
    more = len(summary.failing) - 50
    if more > 0:
        rows.append(f'<tr><td colspan="5" class="small">... and {more} more (see detailed report)</td></tr>')
    return "".join(rows)


def render_html(summary: RunSummary, history: Sequence[Mapping[str, Any]], out_dir: Path) -> str:
    m, c = summary.metadata, summary.counts
    color = _COLORS[summary.verdict]
    build_label = f"#{_esc(m.build_number)}" + (f" &middot; {_esc(m.branch)}" if m.branch else "")
    if m.build_url:
        build_label = f'<a href="{_esc(m.build_url)}">{build_label}</a>'

    coverage = f"{summary.coverage_pct:.1f}%" if summary.coverage_pct is not None else "n/a"
    kpis = [
        ("Pass rate", f"{summary.pass_rate:.1f}%"),
        ("Executed", summary.executed),
        ("Passed", c["passed"]),
        ("Failed", c["failed"] + c["error"]),
        ("Skipped", c["skipped"]),
        ("Flaky (re-run)", len(summary.flaky)),
        ("Code coverage", coverage),
        ("Duration", _fmt_duration(m.duration_seconds)),
    ]
    kpi_html = "".join(f'<div class="kpi"><span>{_esc(k)}</span><strong>{_esc(v)}</strong></div>' for k, v in kpis)

    layer_rows = "".join(
        f"<tr><td><strong>{_esc(name)}</strong></td><td>{sum(cnt.values())}</td>"
        f"<td>{cnt['passed']}</td><td>{cnt['failed'] + cnt['error']}</td><td>{cnt['skipped']}</td>"
        f"<td>{'' if (rate := summary.layer_pass_rate(cnt)) is None else f'{rate:.1f}%'}</td>"
        f"<td>{_bar(cnt)}</td></tr>"
        for name, cnt in summary.by_layer().items()
    )
    failures = _failure_rows(summary, out_dir) or '<tr><td colspan="5">No failures. &#10003;</td></tr>'
    slow_rows = "".join(
        f"<tr><td>{_esc(r.short_name)}</td><td>{_esc(r.layer)}</td><td>{r.duration:.2f}s</td></tr>"
        for r in summary.slowest(5)
    )
    flaky_rows = "".join(
        f"<tr><td>{_esc(r.short_name)}</td><td>{_esc(r.layer)}</td><td>{r.reruns}</td></tr>"
        for r in summary.flaky[:10]
    )
    flaky_block = (
        f"<h2>Reliability risk: passed only after retry</h2><table><tr><th>Test</th><th>Area</th>"
        f"<th>Retries</th></tr>{flaky_rows}</table>"
        if flaky_rows
        else ""
    )

    return f"""<!doctype html><html lang="en"><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1">
<title>{_esc(m.product)} - Test Summary</title><style>{_CSS}</style></head><body><main>
<h1>{_esc(m.product)} &mdash; Quality Summary</h1>
<div class="meta">Environment: <strong>{_esc(m.environment)}</strong> &middot; Build {build_label}
&middot; {_esc(m.provider)} &middot; Commit {_esc(m.commit or 'n/a')} &middot; Run: {_esc(m.started_at)}
&middot; Browser/target: {_esc(m.browser or 'n/a')} / {_esc(m.execution_mode)}</div>
<div class="banner" style="background:{color}"><b>{_esc(summary.verdict)}</b><p>{_esc(summary.headline)}</p></div>
<div class="kpis">{kpi_html}</div>
<h2>Results by area</h2>
<table><tr><th>Area</th><th>Total</th><th>Passed</th><th>Failed</th><th>Skipped</th><th>Pass rate</th><th>Health</th></tr>{layer_rows}</table>
<h2>Failures needing attention</h2>
<table><tr><th>Test</th><th>Area</th><th>What went wrong</th><th>Evidence</th><th>Defect</th></tr>{failures}</table>
{flaky_block}
<h2>Trend</h2>{_sparkline(history)}
<h2>Slowest checks</h2><table><tr><th>Test</th><th>Area</th><th>Time</th></tr>{slow_rows}</table>
<h2>Detailed reports</h2><p class="small"><a href="report.html">Full test report</a> &middot;
<a href="coverage-html/index.html">Code coverage</a> &middot; Allure results in <code>allure-results/</code>
&middot; JUnit XML <code>junit.xml</code></p>
<div class="note"><strong>How to read this page.</strong> Pass rate = passed &divide; (passed + failed).
GREEN &ge; {summary.green_threshold:g}% with no critical failures; AMBER &ge; {summary.amber_threshold:g}%;
otherwise RED. Any failed critical check forces RED. Skipped checks are not counted in the pass rate.
Flaky checks failed at first and passed on retry; they pass the build but hide instability.</div>
</main></body></html>"""


def render_markdown(summary: RunSummary) -> str:
    m, c = summary.metadata, summary.counts
    icon = {"GREEN": "🟢", "AMBER": "🟠", "RED": "🔴", "NO DATA": "⚪"}[summary.verdict]
    lines = [
        f"## {icon} {m.product}: {summary.verdict}",
        f"{summary.headline}",
        "",
        "| Metric | Value |",
        "|---|---|",
        f"| Pass rate | {summary.pass_rate:.1f}% |",
        f"| Passed / Failed / Skipped | {c['passed']} / {c['failed'] + c['error']} / {c['skipped']} |",
        f"| Flaky | {len(summary.flaky)} |",
        f"| Code coverage | {'n/a' if summary.coverage_pct is None else f'{summary.coverage_pct:.1f}%'} |",
        f"| Duration | {_fmt_duration(m.duration_seconds)} |",
        f"| Environment | {m.environment} |",
        "",
        "| Area | Total | Passed | Failed |",
        "|---|---|---|---|",
    ]
    lines += [
        f"| {name} | {sum(cnt.values())} | {cnt['passed']} | {cnt['failed'] + cnt['error']} |"
        for name, cnt in summary.by_layer().items()
    ]
    if summary.failing:
        lines += ["", "**Failures**", ""]
        lines += [f"- `{r.short_name}` ({r.layer}): {r.message[:140]}" for r in summary.failing[:15]]
    return "\n".join(lines) + "\n"


def _result_to_dict(r: CaseResult) -> dict[str, Any]:
    return {
        "test": r.nodeid, "layer": r.layer, "outcome": r.outcome,
        "duration_s": round(r.duration, 3), "message": r.message,
        "jira": r.jira_key, "reruns": r.reruns,
    }  # fmt: skip


def load_history(path: Path) -> list[dict[str, Any]]:
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
        return data if isinstance(data, list) else []
    except (OSError, ValueError):
        return []


def write_reports(summary: RunSummary, out_dir: Path) -> dict[str, Path]:
    """Write all summary artifacts; returns ``{name: path}``. History is updated in place.

    TODO(future): to keep a trend across CI runs, persist ``history.json`` between builds
    (GitHub Actions cache/artifact, Jenkins ``archiveArtifacts`` + copyArtifacts, or push it to
    object storage such as S3) and restore it into the reports directory before the test run.
    """
    out_dir.mkdir(parents=True, exist_ok=True)
    history_path = out_dir / "history.json"
    history = load_history(history_path)
    history.append(
        {
            "build": summary.metadata.build_number,
            "date": summary.metadata.started_at,
            "pass_rate": round(summary.pass_rate, 2),
            "total": summary.executed,
            "failed": summary.counts["failed"] + summary.counts["error"],
        }
    )
    history = history[-_HISTORY_LIMIT:]
    history_path.write_text(json.dumps(history, indent=1), encoding="utf-8")

    paths = {
        "html": out_dir / "executive_summary.html",
        "markdown": out_dir / "summary.md",
        "json": out_dir / "summary.json",
        "history": history_path,
    }
    paths["html"].write_text(render_html(summary, history, out_dir), encoding="utf-8")
    paths["markdown"].write_text(render_markdown(summary), encoding="utf-8")
    paths["json"].write_text(
        json.dumps(
            {
                "verdict": summary.verdict,
                "headline": summary.headline,
                "pass_rate": round(summary.pass_rate, 2),
                "counts": dict(summary.counts),
                "coverage_pct": summary.coverage_pct,
                "metadata": summary.metadata.__dict__,
                "failures": [_result_to_dict(r) for r in summary.failing],
            },
            indent=1,
        ),
        encoding="utf-8",
    )
    return paths
