"""The ONLY module that talks to OpenRouter.

Keeping one call site makes cost, retries and model swaps trivial to manage.
"""
import json
import os

from langchain_openai import ChatOpenAI

from config import DEFAULT_MODEL, OPENROUTER_BASE_URL


def _parse_json(text: str) -> dict:
    """Extract a JSON object from a model reply, tolerating ``` fences and stray prose."""
    start, end = text.find("{"), text.rfind("}")
    if start == -1 or end <= start:
        raise ValueError(f"LLM reply contained no JSON object: {text[:200]!r}")
    return json.loads(text[start : end + 1])


def ask_llm(system_prompt: str, user_prompt: str) -> dict:
    """Send one system+user prompt pair via OpenRouter and return the parsed JSON dict.

    Env is read at call time so the UI can change the key/model without a restart.
    """
    api_key = os.getenv("OPENROUTER_API_KEY")
    if not api_key:
        raise RuntimeError("OPENROUTER_API_KEY is not set (put it in .env or the UI sidebar).")

    llm = ChatOpenAI(
        model=os.getenv("OPENROUTER_MODEL", DEFAULT_MODEL),
        api_key=api_key,
        base_url=OPENROUTER_BASE_URL,
        temperature=0,  # deterministic classification
        timeout=90,
        max_retries=2,
    )
    reply = llm.invoke([("system", system_prompt), ("user", user_prompt)])
    return _parse_json(reply.content)
