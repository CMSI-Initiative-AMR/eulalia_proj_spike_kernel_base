"""Central settings for the Investment Advicer Tool.

Everything tunable lives here so the other modules stay free of magic numbers.
"""
import os

from dotenv import load_dotenv

load_dotenv()  # reads OPENROUTER_API_KEY / OPENROUTER_MODEL from a local .env file

# --- LLM: OpenRouter is OpenAI-compatible, so only the base URL differs ---
OPENROUTER_BASE_URL = "https://openrouter.ai/api/v1"
DEFAULT_MODEL = "openai/gpt-4o-mini"  # override with the OPENROUTER_MODEL env var

# --- Public-market proxy used as a sanity benchmark, keyed by Wide Eye domain ---
DOMAIN_BENCHMARKS = {
    "finance": "XLF",     # Financial Select Sector SPDR
    "energy": "XLE",      # Energy Select Sector SPDR
    "technology": "XLK",  # Technology Select Sector SPDR
    "healthcare": "XLV",  # Health Care Select Sector SPDR
    "any": "SPY",         # broad US market
}

# --- Plausibility thresholds (ASSUMPTIONS - tune them to your own risk view) ---
VENTURE_PREMIUM_PCT = 10.0   # extra annual return tolerated over the public benchmark
EXTREME_RATIO = 2.0          # annualised claim > 2x the ceiling => "extreme"
ARITHMETIC_TOLERANCE = 0.01  # 1% tolerance when re-computing profit = amount * pct

# --- Evidence collection ---
RESULTS_PER_QUERY = 4    # web hits kept per search query
MIN_SNIPPET_CHARS = 40   # shorter snippets are treated as noise
MAX_SNIPPET_CHARS = 400  # snippet length sent to the LLM (keeps tokens low)
SEARCH_WORKERS = 3       # parallel firms searched; keep low to avoid rate limits

# The four allowed verdicts, in the order shown in the UI
VERDICTS = ("Consistent", "Inconsistent", "Uncertain", "Non-accessible")
