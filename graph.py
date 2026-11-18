"""LangGraph pipeline: Wide Eye claims -> evidence -> checks -> LLM judge -> report.

    fetch_predictions -> collect_evidence -> check_plausibility --(any evidence?)--> judge -> finalize
                                                               \\--(none)-----------------> finalize

Only the `judge` node calls the LLM (one batched call for all firms).
"""
from collections import Counter
from concurrent.futures import ThreadPoolExecutor
from typing import TypedDict

from langgraph.graph import END, START, StateGraph

from analysis import assess_claim
from config import MAX_SNIPPET_CHARS, MIN_SNIPPET_CHARS, SEARCH_WORKERS, VERDICTS
from llm import ask_llm
from prompts import SYSTEM_PROMPT, build_user_prompt
from sources import market_benchmark, search_web, wikipedia_summary
from wide_eye_client import WideEyeClient


class State(TypedDict, total=False):
    """Shared state passed between nodes (each node returns only the keys it adds)."""

    scenario_id: str  # input: which Wide Eye sample to validate
    wide_eye: dict    # raw Wide Eye response
    benchmark: dict   # public-market benchmark metrics + evidence record B1
    evidence: dict    # vc_name -> [evidence records with ids E1..En]
    checks: dict      # vc_name -> deterministic plausibility result
    verdicts: dict    # vc_name -> guarded LLM verdict
    report: dict      # final output for the UI / API


# ----------------------------------------------------------------- nodes

def fetch_predictions(state: State) -> dict:
    """Node 1: pull the recommendations from Wide Eye (mock client for now)."""
    return {"wide_eye": WideEyeClient().fetch(state["scenario_id"])}


def _evidence_for(rec: dict, domain: str) -> list[dict]:
    """Gather, de-duplicate, filter and id-tag evidence for one firm."""
    name = rec["vc_name"]
    focus = "" if domain == "any" else domain
    items = wikipedia_summary(name)
    items += search_web(f"{name} venture fund returns performance IRR")
    items += search_web(f"{name} {focus} investments track record".replace("  ", " "))

    seen, kept = set(), []
    for item in items:
        # drop duplicates and snippets too short to carry information
        if item["url"] in seen or len(item["snippet"]) < MIN_SNIPPET_CHARS:
            continue
        seen.add(item["url"])
        kept.append(item)
    for i, item in enumerate(kept, 1):
        item["id"] = f"E{i}"  # stable id the LLM must cite -> provenance link
    return kept


def collect_evidence(state: State) -> dict:
    """Node 2: collect market benchmark once, and per-firm evidence in parallel."""
    wide_eye = state["wide_eye"]
    domain = wide_eye["query"]["domain"]
    recs = wide_eye["recommendations"]
    benchmark = market_benchmark(domain)
    with ThreadPoolExecutor(max_workers=SEARCH_WORKERS) as pool:
        found = list(pool.map(lambda r: _evidence_for(r, domain), recs))
    return {"benchmark": benchmark, "evidence": {r["vc_name"]: ev for r, ev in zip(recs, found)}}


def check_plausibility(state: State) -> dict:
    """Node 3: deterministic arithmetic + benchmark checks (no LLM)."""
    wide_eye = state["wide_eye"]
    amount = wide_eye["query"]["investment_amount"]
    return {"checks": {r["vc_name"]: assess_claim(r, amount, state["benchmark"])
                       for r in wide_eye["recommendations"]}}


def route_after_checks(state: State) -> str:
    """Conditional edge: skip the (paid) LLM call when no firm has any evidence."""
    return "judge" if any(state["evidence"].values()) else "finalize"


def _guard(item: dict, valid_ids: set[str]) -> dict:
    """Sanity-check one LLM verdict: reject unknown labels/ids and unsupported strong verdicts."""
    verdict = item.get("verdict") if item.get("verdict") in VERDICTS else "Uncertain"
    cited = [c for c in item.get("cited_evidence", []) if c in valid_ids]  # drops hallucinated ids
    reasoning = str(item.get("reasoning", "")).strip()

    firm_sources = [c for c in cited if c.startswith("E")]
    if verdict == "Consistent" and len(firm_sources) < 2:
        verdict, reasoning = "Uncertain", f"[Downgraded: <2 firm-specific sources cited] {reasoning}"
    elif verdict == "Inconsistent" and not cited:
        verdict, reasoning = "Uncertain", f"[Downgraded: no evidence cited] {reasoning}"

    try:
        confidence = max(0.0, min(1.0, float(item.get("confidence"))))
    except (TypeError, ValueError):
        confidence = None
    return {"verdict": verdict, "confidence": confidence, "reasoning": reasoning, "cited_evidence": cited}


def judge(state: State) -> dict:
    """Node 4: ONE batched LLM call classifying every firm that has evidence."""
    wide_eye = state["wide_eye"]
    amount = wide_eye["query"]["investment_amount"]
    benchmark_ev = state["benchmark"].get("evidence")

    firms = []
    for rec in wide_eye["recommendations"]:
        evidence = state["evidence"][rec["vc_name"]]
        if not evidence:  # nothing to judge -> finalize marks it Non-accessible
            continue
        firms.append({
            "vc_name": rec["vc_name"],
            "claim": {
                "investment_amount": amount,
                "period_months": rec["investment_period_months"],
                "expected_profit_pct": rec["expected_profit_pct"],
                "expected_profit_amount": rec["expected_profit_amount"],
            },
            "plausibility": state["checks"][rec["vc_name"]],
            "evidence": [
                {**{k: e[k] for k in ("id", "source_type", "title", "url")},
                 "snippet": e["snippet"][:MAX_SNIPPET_CHARS]}
                for e in evidence
            ],
        })

    context = None
    if benchmark_ev:
        context = {"id": "B1", "text": benchmark_ev["snippet"]}
    raw = ask_llm(SYSTEM_PROMPT, build_user_prompt(context, firms))

    verdicts = {}
    for item in raw.get("results", []):
        name = item.get("vc_name")
        if name not in state["evidence"]:
            continue
        valid_ids = {e["id"] for e in state["evidence"][name]} | ({"B1"} if benchmark_ev else set())
        verdicts[name] = _guard(item, valid_ids)
    return {"verdicts": verdicts}


def finalize(state: State) -> dict:
    """Node 5: merge claims, checks, verdicts and cited evidence into the final report."""
    wide_eye = state["wide_eye"]
    benchmark_ev = state.get("benchmark", {}).get("evidence")
    results = []
    for rec in wide_eye["recommendations"]:
        name = rec["vc_name"]
        evidence = state["evidence"].get(name, [])
        verdict = state.get("verdicts", {}).get(name)
        if verdict is None:  # judge skipped it or returned nothing for it
            if evidence:
                verdict = {"verdict": "Uncertain", "confidence": None, "cited_evidence": [],
                           "reasoning": "The judge returned no verdict for this firm."}
            else:
                verdict = {"verdict": "Non-accessible", "confidence": None, "cited_evidence": [],
                           "reasoning": "No usable public evidence could be retrieved for this firm."}

        # Provenance = the exact evidence records the verdict cites
        pool = {e["id"]: e for e in evidence}
        if benchmark_ev:
            pool["B1"] = benchmark_ev
        results.append({
            "vc_name": name,
            "claim": {k: rec[k] for k in ("investment_period_months", "expected_profit_pct",
                                          "expected_profit_amount", "claimed_confidence")},
            "plausibility": state["checks"][name],
            "verdict": verdict["verdict"],
            "confidence": verdict["confidence"],
            "reasoning": verdict["reasoning"],
            "provenance": [pool[i] for i in verdict["cited_evidence"]],
            "evidence_retrieved": len(evidence),
        })

    counts = Counter(r["verdict"] for r in results)
    ranked = counts.most_common()
    tie = len(ranked) > 1 and ranked[0][1] == ranked[1][1]
    return {"report": {
        "request_id": wide_eye["request_id"],
        "query": wide_eye["query"],
        "benchmark": {k: v for k, v in state.get("benchmark", {}).items() if k != "evidence"},
        "summary": {"counts": {v: counts.get(v, 0) for v in VERDICTS},
                    "overall": "Uncertain" if tie else ranked[0][0]},  # ties never claim certainty
        "results": results,
    }}


# ----------------------------------------------------------------- wiring

def build_graph():
    """Assemble and compile the LangGraph workflow."""
    g = StateGraph(State)
    g.add_node("fetch_predictions", fetch_predictions)
    g.add_node("collect_evidence", collect_evidence)
    g.add_node("check_plausibility", check_plausibility)
    g.add_node("judge", judge)
    g.add_node("finalize", finalize)

    g.add_edge(START, "fetch_predictions")
    g.add_edge("fetch_predictions", "collect_evidence")
    g.add_edge("collect_evidence", "check_plausibility")
    g.add_conditional_edges("check_plausibility", route_after_checks,
                            {"judge": "judge", "finalize": "finalize"})
    g.add_edge("judge", "finalize")
    g.add_edge("finalize", END)
    return g.compile()


def run_pipeline(scenario_id: str, on_step=None) -> dict:
    """Run the graph for one scenario; `on_step(node_name)` is called as each node finishes."""
    final: dict = {}
    for update in build_graph().stream({"scenario_id": scenario_id}, stream_mode="updates"):
        for node, delta in update.items():
            final.update(delta or {})
            if on_step:
                on_step(node)
    return final


if __name__ == "__main__":  # quick CLI check: python graph.py S1
    import json
    import sys

    print(json.dumps(run_pipeline(sys.argv[1] if len(sys.argv) > 1 else "S1")["report"], indent=2))
