"""
One command, whole pipeline:

    python run_all.py myvideo.mp4 ta

(ta = Tamil, hi = Hindi, mr = Marathi, en = English)

Runs transcribe_chunked.py -> find_moments.py -> render.py,
times every stage, estimates the API cost, and writes run_report.json.
"""
import sys
import os
import json
import time
import subprocess
from dotenv import load_dotenv
from pricing import estimate_cost, usd_to_inr, STT_USD_PER_AUDIO_HOUR, LLM_USD_PER_MILLION_TOKENS

load_dotenv()

if len(sys.argv) < 3:
    raise SystemExit("Usage: python run_all.py <video> <language code>   e.g. python run_all.py test.mp4 ta")

VIDEO, LANG = sys.argv[1], sys.argv[2]

USD_TO_INR = usd_to_inr()


def stage(name, cmd):
    print("\n" + "=" * 12 + " " + name + " " + "=" * 12)
    t = time.time()
    r = subprocess.run([sys.executable] + cmd)
    secs = time.time() - t
    if r.returncode != 0:
        raise SystemExit("\nStage '{}' failed (exit code {}). Fix it, then rerun.".format(name, r.returncode))
    return secs


def main():
    if not os.path.exists(VIDEO):
        raise SystemExit("Video not found: " + VIDEO)

    t0 = time.time()
    times = {}
    times["transcribe"] = stage("1/3 TRANSCRIBE", ["transcribe_chunked.py", VIDEO, LANG])
    times["find_moments"] = stage("2/3 FIND MOMENTS", ["find_moments.py"])
    times["render"] = stage("3/3 RENDER", ["render.py", VIDEO])
    total = time.time() - t0

    result = json.load(open("result.json", encoding="utf-8"))
    clips = json.load(open("clips.json", encoding="utf-8"))
    audio_secs = result.get("audio_seconds", 0)
    billed_secs = result.get("billed_audio_seconds", audio_secs)
    usage = clips.get("usage", {"input_tokens": 0, "output_tokens": 0})

    stt_model = result.get("stt_model", "whisper-large-v3")
    llm_model = os.getenv("GROQ_MODEL", "openai/gpt-oss-120b")
    provider = clips.get("provider", "groq")

    cost = estimate_cost(stt_model, billed_secs, llm_model, provider, usage)
    cost_stt, cost_llm = cost["stt"], cost["llm"]

    known = cost_stt is not None and cost_llm is not None
    cost_total = (cost_stt + cost_llm) if known else None

    report = {
        "video": VIDEO, "language": LANG,
        "audio_seconds": audio_secs,
        "stage_seconds": {k: round(v, 1) for k, v in times.items()},
        "total_seconds": round(total, 1),
        "clips_made": len(clips["clips"]),
        "stt_model": stt_model, "llm_model": llm_model, "llm_tokens": usage,
        "cost_usd": {
            "speech_to_text": None if cost_stt is None else round(cost_stt, 5),
            "llm": None if cost_llm is None else round(cost_llm, 5),
            "total": None if cost_total is None else round(cost_total, 5),
        },
        "cost_inr_total": None if cost_total is None else round(cost_total * USD_TO_INR, 2),
        "usd_to_inr_used": USD_TO_INR,
    }
    with open("run_report.json", "w", encoding="utf-8") as f:
        json.dump(report, f, indent=2)

    print("\n" + "=" * 12 + " SUMMARY " + "=" * 12)
    print("Video length:   {:.0f}s".format(audio_secs))
    for k, v in times.items():
        print("{:<14} {:>6.1f}s".format(k, v))
    print("TOTAL:         {:>6.1f}s   (target: under 60s)".format(total))
    print("Clips made:     {}  -> clips_out/".format(len(clips["clips"])))
    print("LLM tokens:     {} in / {} out".format(usage["input_tokens"], usage["output_tokens"]))
    print("\nAPI cost for this job ({} + {}):".format(stt_model, llm_model))
    if cost_stt is not None:
        print("  speech-to-text  ${:.4f}  ({:.0f}s billed)".format(cost_stt, billed_secs))
    else:
        print("  speech-to-text  unknown model '{}': add it to STT_USD_PER_AUDIO_HOUR".format(stt_model))
    if cost_llm is not None:
        print("  clip picking    ${:.4f}".format(cost_llm))
    else:
        print("  clip picking    unknown model '{}': add it to LLM_USD_PER_MILLION_TOKENS".format(llm_model))
    if known:
        print("  TOTAL           ${:.4f}  = about Rs {:.2f}  (at Rs {:.0f}/USD)".format(
            cost_total, cost_total * USD_TO_INR, USD_TO_INR))
        print("  Per minute of video: about Rs {:.2f}".format(
            cost_total * USD_TO_INR / max(audio_secs / 60, 0.1)))
        print("  (API only. Servers, storage, payment fees and retries are extra.)")
    print("Saved: run_report.json")


if __name__ == "__main__":
    main()