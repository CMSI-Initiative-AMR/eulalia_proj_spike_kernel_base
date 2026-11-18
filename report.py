"""Builds a self-contained HTML report (inline CSS, no external assets) from the pipeline output."""
import datetime as dt
from html import escape

from config import VERDICTS

# Verdict -> (icon, text colour, background colour)
STYLE = {
    "Consistent": ("✅", "#146c2e", "#e6f4ea"),
    "Inconsistent": ("❌", "#b3261e", "#fce8e6"),
    "Uncertain": ("❓", "#8a5a00", "#fff4d6"),
    "Non-accessible": ("🚫", "#5f6368", "#eceff1"),
}

CSS = """
body{font-family:-apple-system,Segoe UI,Roboto,sans-serif;max-width:960px;margin:2rem auto;padding:0 1rem;color:#1f2328;line-height:1.5}
h1{margin-bottom:.2rem} h2{margin-top:2rem;border-bottom:1px solid #d0d7de;padding-bottom:.3rem}
.muted{color:#656d76;font-size:.9rem}
.cards{display:flex;flex-wrap:wrap;gap:.75rem;margin:1rem 0}
.card{flex:1 1 150px;border-radius:8px;padding:.8rem 1rem}
.card .n{font-size:2rem;font-weight:700} .card .l{font-size:.95rem;font-weight:600}
table{border-collapse:collapse;width:100%;font-size:.9rem}
th,td{border:1px solid #d0d7de;padding:.4rem .6rem;text-align:left} th{background:#f6f8fa}
.badge{display:inline-block;border-radius:12px;padding:.1rem .6rem;font-weight:600;white-space:nowrap}
.firm{border:1px solid #d0d7de;border-radius:8px;padding:1rem;margin:1rem 0;page-break-inside:avoid}
.firm h3{margin:.2rem 0 .5rem}
.ev{background:#f6f8fa;border-radius:6px;padding:.5rem .7rem;margin:.4rem 0;font-size:.88rem}
.ev a{word-break:break-all}
"""


def _badge(verdict: str) -> str:
    """Coloured pill showing the full verdict word (never truncated)."""
    icon, fg, bg = STYLE[verdict]
    return f'<span class="badge" style="color:{fg};background:{bg}">{icon} {escape(verdict)}</span>'


def _evidence_html(items: list[dict]) -> str:
    """Render the cited evidence records (the provenance trail) for one firm."""
    if not items:
        return '<p class="muted">No evidence cited for this verdict.</p>'
    rows = []
    for e in items:
        link = f'<a href="{escape(e["url"])}">{escape(e["title"] or e["url"])}</a>' if e["url"] else escape(e["title"])
        rows.append(
            f'<div class="ev"><b>{escape(e["id"])}</b> · {escape(e["source_type"])} · {link}'
            f'<br>{escape(e["snippet"][:400])}'
            f'<br><span class="muted">Retrieved {escape(e["retrieved_at"])}</span></div>'
        )
    return "".join(rows)


def build_html_report(report: dict) -> str:
    """Return the full report as one HTML string, ready to save or download."""
    q, summary, bench = report["query"], report["summary"], report["benchmark"]
    generated = dt.datetime.now(dt.timezone.utc).strftime("%Y-%m-%d %H:%M UTC")

    cards = "".join(
        f'<div class="card" style="color:{STYLE[v][1]};background:{STYLE[v][2]}">'
        f'<div class="n">{summary["counts"][v]}</div><div class="l">{STYLE[v][0]} {escape(v)}</div></div>'
        for v in VERDICTS
    )
    overall = summary["overall"]
    cards += (
        f'<div class="card" style="color:{STYLE[overall][1]};background:{STYLE[overall][2]};border:2px solid {STYLE[overall][1]}">'
        f'<div class="l">Overall</div><div class="n" style="font-size:1.4rem">{STYLE[overall][0]} {escape(overall)}</div></div>'
    )

    bench_line = (
        f'Benchmark {escape(bench["symbol"])}: 1-year {bench["trailing_1y_pct"]}%, 3-year CAGR {bench["cagr_3y_pct"]}% '
        f'(as of {escape(bench["as_of"])}). Public equities only, not venture-fund performance.'
        if bench else "Benchmark unavailable: market data could not be fetched."
    )

    table_rows = "".join(
        f'<tr><td>{escape(r["vc_name"])}</td><td>{r["claim"]["expected_profit_pct"]}%</td>'
        f'<td>{r["claim"]["investment_period_months"]}</td><td>{r["plausibility"]["annualized_pct"]}%</td>'
        f'<td>{escape(r["plausibility"]["band"])}</td><td>{_badge(r["verdict"])}</td>'
        f'<td>{"" if r["confidence"] is None else r["confidence"]}</td><td>{r["evidence_retrieved"]}</td></tr>'
        for r in report["results"]
    )

    firms = "".join(
        f'<div class="firm"><h3>{escape(r["vc_name"])} {_badge(r["verdict"])}</h3>'
        f'<p>{escape(r["reasoning"])}</p>'
        f'<p class="muted">Claim: {r["claim"]["expected_profit_pct"]}% in {r["claim"]["investment_period_months"]} months '
        f'(≈{r["plausibility"]["annualized_pct"]}%/yr) · arithmetic OK: {r["plausibility"]["arithmetic_ok"]} · '
        f'plausibility: {escape(r["plausibility"]["band"])}</p>'
        f'<b>Provenance</b>{_evidence_html(r["provenance"])}</div>'
        for r in report["results"]
    )

    return f"""<!doctype html><html lang="en"><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1">
<title>Investment Advicer Report - {escape(q["domain"])} ${q["investment_amount"]:,}</title>
<style>{CSS}</style></head><body>
<h1>Investment Advicer Report</h1>
<p class="muted">Wide Eye request {escape(report["request_id"])} · ${q["investment_amount"]:,} {escape(q.get("currency", ""))} · {escape(q["domain"])} domain · generated {generated}</p>
<h2>Summary</h2><div class="cards">{cards}</div>
<p class="muted">{bench_line}</p>
<h2>Results</h2>
<table><tr><th>Venture capital</th><th>Claimed profit</th><th>Months</th><th>Annualised</th><th>Plausibility</th><th>Verdict</th><th>Confidence</th><th>Sources</th></tr>{table_rows}</table>
<h2>Detail and provenance</h2>{firms}
<p class="muted">Automated validation of Wide Eye claims against public sources. It is not investment advice. Sample Wide Eye data in this prototype is fabricated.</p>
</body></html>"""
