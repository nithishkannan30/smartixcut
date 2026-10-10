"""
API price tables and the cost estimate, shared by run_all.py and api.py.
Prices in USD. Source: Groq pricing page and price trackers, checked Oct 2026.
Prices change, so recheck https://groq.com/pricing now and then. Where sources
disagreed I used the higher number to stay on the safe side.
"""
import os

STT_USD_PER_AUDIO_HOUR = {            # Groq bills at least 10 s per request
    "whisper-large-v3": 0.111,
    "whisper-large-v3-turbo": 0.04,
}
LLM_USD_PER_MILLION_TOKENS = {        # (input, output)
    "openai/gpt-oss-120b": (0.15, 0.75),
    "openai/gpt-oss-20b": (0.10, 0.50),
    "llama-3.1-8b-instant": (0.05, 0.08),
    "llama-3.3-70b-versatile": (0.59, 0.79),
}


def usd_to_inr():
    return float(os.getenv("USD_TO_INR", "88"))   # approximate, set the current rate in .env


def estimate_cost(stt_model, billed_secs, llm_model, provider, usage):
    """Returns {"stt": usd or None, "llm": usd or None, "total": usd or None}."""
    rate = STT_USD_PER_AUDIO_HOUR.get(stt_model)
    stt = billed_secs / 3600 * rate if rate is not None else None

    llm = None
    prices = LLM_USD_PER_MILLION_TOKENS.get(llm_model) if provider == "groq" else None
    if prices:
        llm = (usage.get("input_tokens", 0) * prices[0]
               + usage.get("output_tokens", 0) * prices[1]) / 1_000_000

    total = stt + llm if (stt is not None and llm is not None) else None
    return {"stt": stt, "llm": llm, "total": total}