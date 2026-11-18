# Investment Advicer Tool

Validates Wide Eye venture-capital profit predictions against independent sources and labels each as
**Consistent**, **Inconsistent**, **Uncertain** or **Non-accessible**, with a provenance trail.

## Run
```bash
pip install -r requirements.txt
cp .env.example .env        # add OPENROUTER_API_KEY
streamlit run app.py        # UI
python graph.py S1          # or CLI: S1 | S2 | S3
```

## Files
| File | Role |
|---|---|
| `wide_eye_sample.json` / `wide_eye_client.py` | Mock Wide Eye API (3 inputs, 5 VCs each) |
| `sources.py` | Evidence: DuckDuckGo search, Wikipedia, yfinance benchmark |
| `analysis.py` | Deterministic checks (arithmetic, annualised return vs benchmark) |
| `prompts.py` | Strict verdict rubric |
| `llm.py` | The only OpenRouter call site |
| `graph.py` | LangGraph pipeline |
| `app.py` | Streamlit UI |

The sample data is fabricated for development. "Helios Peak Ventures" is fictional, to exercise the Non-accessible path.
