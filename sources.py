"""Evidence collectors: web search, Wikipedia, public-market benchmark.

All collectors return records with one shared schema so provenance stays uniform:
    {source_type, title, url, snippet, retrieved_at}
Every collector swallows network errors and returns an empty result instead, which
the pipeline later interprets as "Non-accessible".
"""
import datetime as dt
from urllib.parse import quote

import requests

from config import DOMAIN_BENCHMARKS, RESULTS_PER_QUERY

WIKI_SUMMARY_API = "https://en.wikipedia.org/api/rest_v1/page/summary/{title}"
USER_AGENT = "InvestmentAdvicerTool/0.1 (research prototype)"


def _record(source_type: str, title: str, url: str, snippet: str) -> dict:
    """Build one evidence record, stamped with the retrieval time (provenance)."""
    return {
        "source_type": source_type,
        "title": (title or "").strip(),
        "url": url or "",
        "snippet": (snippet or "").strip(),
        "retrieved_at": dt.datetime.now(dt.timezone.utc).isoformat(timespec="seconds"),
    }


def search_web(query: str, max_results: int = RESULTS_PER_QUERY) -> list[dict]:
    """Keyless DuckDuckGo text search. Returns [] on any failure."""
    try:
        from ddgs import DDGS  # current package name
    except ImportError:
        try:
            from duckduckgo_search import DDGS  # legacy package name
        except ImportError:
            return []
    try:
        hits = DDGS().text(query, max_results=max_results) or []
    except Exception:  # rate limit, offline, etc.
        return []
    return [_record("web_search", h.get("title"), h.get("href"), h.get("body")) for h in hits]


def wikipedia_summary(name: str) -> list[dict]:
    """Fetch the Wikipedia lead summary for an entity; cheap proof the firm exists."""
    url = WIKI_SUMMARY_API.format(title=quote(name.replace(" ", "_")))
    try:
        resp = requests.get(url, headers={"User-Agent": USER_AGENT}, timeout=10)
        if resp.status_code != 200:
            return []
        data = resp.json()
        if data.get("type") == "disambiguation":  # ambiguous page = unusable evidence
            return []
        page = data.get("content_urls", {}).get("desktop", {}).get("page", "")
        return [_record("wikipedia", data.get("title", name), page, data.get("extract"))]
    except Exception:
        return []


def market_benchmark(domain: str) -> dict:
    """Pull trailing-1y and 3y-CAGR returns of a public-market proxy via yfinance.

    Returns {} if data is unavailable, else the metrics plus an `evidence` record
    (id "B1") that the LLM can cite like any other source.
    """
    symbol = DOMAIN_BENCHMARKS.get(domain.lower(), DOMAIN_BENCHMARKS["any"])
    try:
        import yfinance as yf

        close = yf.Ticker(symbol).history(period="5y", auto_adjust=True)["Close"].dropna()
        if len(close) < 760:  # need ~3 years of trading days
            return {}
        last = float(close.iloc[-1])
        one_year = (last / float(close.iloc[-253]) - 1) * 100            # ~252 trading days
        cagr_3y = ((last / float(close.iloc[-757])) ** (1 / 3) - 1) * 100  # ~756 trading days
        as_of = str(close.index[-1].date())
    except Exception:
        return {}

    snippet = (
        f"{symbol} (public-market proxy for domain '{domain}'): trailing 1-year return "
        f"{one_year:.1f}%, 3-year CAGR {cagr_3y:.1f}% as of {as_of}. "
        "Public equities only - this is NOT venture-fund performance."
    )
    evidence = _record("market_data", f"{symbol} price history", f"https://finance.yahoo.com/quote/{symbol}", snippet)
    evidence["id"] = "B1"
    return {
        "symbol": symbol,
        "trailing_1y_pct": round(one_year, 1),
        "cagr_3y_pct": round(cagr_3y, 1),
        "as_of": as_of,
        "evidence": evidence,
    }
