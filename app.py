"""Streamlit UI: pick one of three Wide Eye inputs, run the validator, inspect results.

Run with:  streamlit run app.py
"""
import os

import pandas as pd
import streamlit as st

from config import DEFAULT_MODEL, VERDICTS
from graph import run_pipeline
from report import build_html_report
from wide_eye_client import WideEyeClient

ICONS = {"Consistent": "✅", "Inconsistent": "❌", "Uncertain": "❓", "Non-accessible": "🚫"}
# Card colours (dark text on light tint stays readable in Streamlit light and dark themes)
FG = {"Consistent": "#146c2e", "Inconsistent": "#b3261e", "Uncertain": "#8a5a00", "Non-accessible": "#444b52"}
BG = {"Consistent": "#e6f4ea", "Inconsistent": "#fce8e6", "Uncertain": "#fff4d6", "Non-accessible": "#eceff1"}
STEP_LABELS = {
    "fetch_predictions": "Fetched Wide Eye predictions",
    "collect_evidence": "Collected evidence from search, Wikipedia and market data",
    "check_plausibility": "Ran arithmetic and benchmark checks",
    "judge": "LLM judged each claim against the evidence",
    "finalize": "Built the provenance report",
}


def safe(text: str) -> str:
    """Escape `$` so Streamlit does not render dollar amounts as LaTeX."""
    return str(text).replace("$", "\\$")


st.set_page_config(page_title="Investment Advicer Tool", layout="wide")
st.title("Investment Advicer Tool")
st.caption("Validates Wide Eye venture-capital profit predictions against independent public sources.")

client = WideEyeClient()
scenarios = {s["id"]: s["query"] for s in client.list_scenarios()}

# --- Sidebar: OpenRouter settings (env is read at call time in llm.py) ---
with st.sidebar:
    st.header("OpenRouter")
    key = st.text_input("API key", type="password", value=os.getenv("OPENROUTER_API_KEY", ""))
    model = st.text_input("Model", value=os.getenv("OPENROUTER_MODEL", DEFAULT_MODEL))
    if key:
        os.environ["OPENROUTER_API_KEY"] = key
    os.environ["OPENROUTER_MODEL"] = model

# --- Input picker: the three Wide Eye test inputs ---
choice = st.radio(
    "Select a Wide Eye input",
    options=list(scenarios),
    format_func=lambda s: f"{s}: ${scenarios[s]['investment_amount']:,} · {scenarios[s]['domain']} domain",
    horizontal=True,
)
with st.expander("Wide Eye API response (mock)"):
    st.json(client.fetch(choice))

# --- Run the LangGraph pipeline, streaming node progress into a status box ---
if st.button("Validate predictions", type="primary"):
    with st.status("Running validation graph...", expanded=True) as status:
        try:
            final = run_pipeline(choice, on_step=lambda n: st.write(f"✔ {STEP_LABELS.get(n, n)}"))
            st.session_state["report"] = final["report"]
            status.update(label="Validation complete", state="complete")
        except Exception as exc:  # surface key/network/LLM errors instead of a stack trace
            status.update(label="Validation failed", state="error")
            st.error(str(exc))

report = st.session_state.get("report")
if report:
    q = report["query"]
    st.subheader(f"Results: ${q['investment_amount']:,} · {q['domain']} domain")

    # Top-level analysis: HTML cards (st.metric truncates long values like "Uncertain")
    overall = report["summary"]["overall"]
    cards = "".join(
        f'<div style="flex:1 1 140px;border-radius:8px;padding:.7rem 1rem;background:{BG[v]};color:{FG[v]}">'
        f'<div style="font-size:.95rem;font-weight:600">{ICONS[v]} {v}</div>'
        f'<div style="font-size:2rem;font-weight:700">{report["summary"]["counts"][v]}</div></div>'
        for v in VERDICTS
    )
    cards += (
        f'<div style="flex:1 1 170px;border-radius:8px;padding:.7rem 1rem;background:{BG[overall]};'
        f'color:{FG[overall]};border:2px solid {FG[overall]}">'
        f'<div style="font-size:.95rem;font-weight:600">Overall</div>'
        f'<div style="font-size:1.5rem;font-weight:700;white-space:normal">{ICONS[overall]} {overall}</div></div>'
    )
    st.markdown(f'<div style="display:flex;flex-wrap:wrap;gap:.75rem;margin:.5rem 0 1rem">{cards}</div>',
                unsafe_allow_html=True)

    # Download the full report as a standalone HTML file
    st.download_button(
        "⬇ Download HTML report",
        data=build_html_report(report),
        file_name=f"investment_report_{report['request_id']}.html",
        mime="text/html",
    )

    bench = report["benchmark"]
    if bench:
        st.caption(f"Benchmark {bench['symbol']}: 1y {bench['trailing_1y_pct']}%, 3y CAGR {bench['cagr_3y_pct']}% (as of {bench['as_of']})")
    else:
        st.caption("Benchmark unavailable: market data could not be fetched.")

    # Summary table
    st.dataframe(pd.DataFrame([{
        "Venture capital": r["vc_name"],
        "Claimed profit %": r["claim"]["expected_profit_pct"],
        "Period (months)": r["claim"]["investment_period_months"],
        "Annualised %": r["plausibility"]["annualized_pct"],
        "Plausibility": r["plausibility"]["band"],
        "Verdict": f"{ICONS[r['verdict']]} {r['verdict']}",
        "Confidence": r["confidence"],
        "Sources found": r["evidence_retrieved"],
    } for r in report["results"]]), use_container_width=True, hide_index=True)

    # Per-firm reasoning + provenance trail
    for r in report["results"]:
        with st.expander(f"{ICONS[r['verdict']]} {r['vc_name']} - {r['verdict']}"):
            st.write(safe(r["reasoning"]))
            st.caption(
                f"Claim: {r['claim']['expected_profit_pct']}% in {r['claim']['investment_period_months']} months "
                f"(≈{r['plausibility']['annualized_pct']}%/yr) · arithmetic OK: {r['plausibility']['arithmetic_ok']}"
            )
            if r["provenance"]:
                st.markdown("**Provenance (evidence cited)**")
                for e in r["provenance"]:
                    st.markdown(f"- `{e['id']}` *{e['source_type']}* · [{safe(e['title'] or e['url'])}]({e['url']})")
                    st.caption(safe(e["snippet"][:250]) + f" - retrieved {e['retrieved_at']}")
            else:
                st.caption("No evidence cited for this verdict.")
