"""Deterministic (non-LLM) checks on a Wide Eye claim.

These run before the LLM so the judge receives hard numbers, not just prose.
"""
from config import ARITHMETIC_TOLERANCE, EXTREME_RATIO, VENTURE_PREMIUM_PCT


def annualize(profit_pct: float, months: int) -> float:
    """Convert a return earned over `months` into an annualised compound rate (%)."""
    return ((1 + profit_pct / 100) ** (12 / months) - 1) * 100


def assess_claim(rec: dict, amount: float, benchmark: dict) -> dict:
    """Score one recommendation against internal arithmetic and a market benchmark.

    Returns:
        annualized_pct: claimed return expressed per year
        arithmetic_ok:  does expected_profit_amount == amount * pct (within tolerance)?
        ceiling_pct:    benchmark 3y CAGR + venture premium (the "reasonable" upper bound)
        ratio / band:   annualised claim vs ceiling -> within_range | stretched | extreme | unknown
    """
    pct, months = rec["expected_profit_pct"], rec["investment_period_months"]
    annualized = annualize(pct, months)

    # Internal consistency: the claimed amount must match the claimed percentage
    implied = amount * pct / 100
    tolerance = max(1.0, ARITHMETIC_TOLERANCE * abs(implied))
    arithmetic_ok = abs(implied - rec["expected_profit_amount"]) <= tolerance

    result = {
        "annualized_pct": round(annualized, 1),
        "arithmetic_ok": arithmetic_ok,
        "ceiling_pct": None,
        "ratio": None,
        "band": "unknown",  # stays "unknown" when no benchmark could be fetched
    }
    cagr = benchmark.get("cagr_3y_pct")
    if cagr is None:
        return result

    ceiling = max(cagr, 0.0) + VENTURE_PREMIUM_PCT  # negative markets don't lower the bar
    ratio = annualized / ceiling
    result.update(
        ceiling_pct=round(ceiling, 1),
        ratio=round(ratio, 2),
        band="within_range" if ratio <= 1 else "stretched" if ratio <= EXTREME_RATIO else "extreme",
    )
    return result
