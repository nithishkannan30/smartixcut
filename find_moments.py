import os
import re
import json
import time
from dotenv import load_dotenv

load_dotenv()

# ---------------- settings ----------------
PROVIDER = "groq"                        # "groq" or "gemini"
GROQ_MODEL = os.getenv("GROQ_MODEL", "openai/gpt-oss-120b")   # set GROQ_MODEL in .env
GEMINI_MODEL = "gemini-2.5-flash"        # only used if PROVIDER = "gemini"

INPUT_FILE = "result.json"               # output of transcribe_chunked.py
OUTPUT_FILE = "clips.json"

USER_PROMPT = os.getenv("CLIP_PROMPT", "best hooks and interesting moments for Instagram Reels")
NUM_CLIPS = int(os.getenv("NUM_CLIPS", "3"))
MIN_LEN = float(os.getenv("MIN_LEN", "15"))   # seconds
MAX_LEN = float(os.getenv("MAX_LEN", "60"))   # seconds
MAX_GAP = 4.0                            # longest silence/missing speech allowed inside a clip
MAX_ATTEMPTS = 3

SYSTEM_PROMPT = (
    "You are an expert short-form video editor for Instagram Reels and "
    "YouTube Shorts. You always answer with valid JSON only."
)


# ---------------- LLM calls ----------------
def call_groq(prompt):
    from groq import Groq
    client = Groq(api_key=os.environ["GROQ_API_KEY"])
    kwargs = {}
    if "gpt-oss" in GROQ_MODEL:
        # reasoning model: keep thinking short so it still has room to answer
        kwargs["reasoning_effort"] = "low"
    resp = client.chat.completions.create(
        model=GROQ_MODEL,
        messages=[
            {"role": "system", "content": SYSTEM_PROMPT},
            {"role": "user", "content": prompt},
        ],
        temperature=0.3,
        max_completion_tokens=4000,
        **kwargs,
    )
    u = resp.usage
    usage = {"input_tokens": u.prompt_tokens, "output_tokens": u.completion_tokens}
    return resp.choices[0].message.content, usage


def call_gemini(prompt):
    from google import genai
    from google.genai import types
    client = genai.Client(api_key=os.environ["GEMINI_API_KEY"])
    resp = client.models.generate_content(
        model=GEMINI_MODEL,
        contents=SYSTEM_PROMPT + "\n\n" + prompt,
        config=types.GenerateContentConfig(
            response_mime_type="application/json", temperature=0.3
        ),
    )
    u = resp.usage_metadata
    usage = {
        "input_tokens": u.prompt_token_count,
        "output_tokens": u.candidates_token_count,
    }
    return resp.text, usage


def call_llm(prompt):
    return call_groq(prompt) if PROVIDER == "groq" else call_gemini(prompt)


# ---------------- prompt ----------------
def build_prompt(lines):
    numbered = "\n".join(
        "[{}] ({:.1f}s-{:.1f}s) {}{}".format(
            i, l["start"], l["end"], l["text"],
            "   <UNCLEAR AUDIO - never use this line>" if l.get("low_conf") else "")
        for i, l in enumerate(lines)
    )
    example = (
        '{"clips": [{"start_line": 0, "end_line": 5, "title": "...", '
        '"reason": "...", "hashtags": ["#a", "#b", "#c"]}]}'
    )
    request = USER_PROMPT.lower()
    theme_rules = [
        "Treat the creator's request as a hard content filter, not just a title suggestion.",
        "Every selected clip must clearly match the requested theme. Do not substitute generic clips that are merely well-spoken or motivational.",
    ]
    if any(word in request for word in ("funny", "funniest", "comedy", "humor", "humour", "joke")):
        theme_rules.extend([
            "For a funny request, select only moments containing an actual joke, punchline, playful exchange, absurdity, irony, or clearly humorous reaction.",
            "Do not select advice, life lessons, serious explanations, inspirational claims, or motivational speeches unless they are unmistakably used as a joke.",
            "If the transcript has no genuinely funny moments, return an empty clips list instead of returning motivational or unrelated clips.",
        ])

    parts = [
        'The creator wants: "{}"'.format(USER_PROMPT),
        "",
        "Below is a transcript. Each line has a line number in [brackets] and its time range.",
        "Pick the {} best clips, best first.".format(NUM_CLIPS),
        "",
        "Rules:",
        *theme_rules,
        "- A clip is a run of consecutive lines: start_line to end_line (inclusive).",
        "- Each clip must last between {:.0f} and {:.0f} seconds in total.".format(MIN_LEN, MAX_LEN),
        "- The first line must work as a strong hook (a question, a surprise, a bold claim).",
        "- The clip must make sense on its own and end at a complete thought.",
        "- Clips must not overlap each other.",
        "- Never include a line marked UNCLEAR AUDIO, and never span a big jump in time between lines.",
        '- Write "title" and "reason" in the same language as the transcript.',
        '- "hashtags" is a list of 3 to 5 short hashtags.',
        "",
        "Return ONLY a JSON object in exactly this shape:",
        example,
        "",
        "Transcript:",
        numbered,
    ]
    return "\n".join(parts)


# ---------------- parsing and validation ----------------
def parse_clips(text):
    try:
        data = json.loads(text)
    except json.JSONDecodeError:
        match = re.search(r"\{.*\}", text, re.DOTALL)
        if not match:
            return []
        try:
            data = json.loads(match.group(0))
        except json.JSONDecodeError:
            return []
    if isinstance(data, dict):
        data = data.get("clips", [])
    return data if isinstance(data, list) else []


def validate_and_fix(raw_clips, lines):
    """Turn the model's line numbers into real, safe timestamps."""
    n = len(lines)
    accepted = []

    for c in raw_clips:
        try:
            a = int(c["start_line"])
            b = int(c["end_line"])
        except (KeyError, TypeError, ValueError):
            print("Rejected (bad format):", c)
            continue

        if not (0 <= a <= b < n):
            print("Rejected (line numbers out of range):", c)
            continue

        # unclear (garbled) lines: trim them off the edges, reject if any are inside
        while a <= b and lines[a].get("low_conf"):
            a += 1
        while b >= a and lines[b].get("low_conf"):
            b -= 1
        if a > b:
            print("Rejected (only unclear audio):", c.get("title"))
            continue
        if any(lines[k].get("low_conf") for k in range(a, b + 1)):
            print("Rejected (contains unclear audio):", c.get("title"))
            continue
        if any(lines[k + 1]["start"] - lines[k]["end"] > MAX_GAP for k in range(a, b)):
            print("Rejected (big gap, speech missing):", c.get("title"))
            continue

        # too long -> pull the end back
        while b > a and lines[b]["end"] - lines[a]["start"] > MAX_LEN:
            b -= 1
        # too short -> push the end forward if it still fits and stays clean
        while (
            b < n - 1
            and lines[b]["end"] - lines[a]["start"] < MIN_LEN
            and lines[b + 1]["end"] - lines[a]["start"] <= MAX_LEN
            and not lines[b + 1].get("low_conf")
            and lines[b + 1]["start"] - lines[b]["end"] <= MAX_GAP
        ):
            b += 1

        start = lines[a]["start"]
        end = lines[b]["end"]
        duration = end - start

        if not (MIN_LEN <= duration <= MAX_LEN):
            print("Rejected (length {:.1f}s): {}".format(duration, c.get("title")))
            continue

        if any(start < x["end"] and end > x["start"] for x in accepted):
            print("Rejected (overlaps another clip):", c.get("title"))
            continue

        accepted.append({
            "rank": len(accepted) + 1,
            "start": round(start, 2),
            "end": round(end, 2),
            "duration": round(duration, 2),
            "title": str(c.get("title", "")).strip(),
            "reason": str(c.get("reason", "")).strip(),
            "hashtags": [str(h) for h in c.get("hashtags", [])][:5],
            "text": " ".join(l["text"] for l in lines[a:b + 1]),
        })

    return accepted[:NUM_CLIPS]


# ---------------- main ----------------
def main():
    with open(INPUT_FILE, encoding="utf-8") as f:
        lines = json.load(f)["lines"]
    if not lines:
        raise SystemExit("No lines found in result.json")

    total_audio = lines[-1]["end"]
    flagged = sum(1 for l in lines if l.get("low_conf"))
    print("Loaded {} lines ({:.0f}s), {} flagged unclear. Provider: {}\n".format(
        len(lines), total_audio, flagged, PROVIDER))

    prompt = build_prompt(lines)
    best, total_usage = [], {"input_tokens": 0, "output_tokens": 0}
    t0 = time.time()

    for attempt in range(1, MAX_ATTEMPTS + 1):
        try:
            text, usage = call_llm(prompt)
        except Exception as e:
            print("Attempt {}: API error: {}".format(attempt, e))
            time.sleep(2 * attempt)
            continue

        total_usage["input_tokens"] += usage["input_tokens"] or 0
        total_usage["output_tokens"] += usage["output_tokens"] or 0

        clips = validate_and_fix(parse_clips(text), lines)
        print("Attempt {}: {} valid clip(s)\n".format(attempt, len(clips)))
        if not clips:
            print("Raw model reply (first 600 chars):\n{}\n".format((text or "")[:600]))

        if len(clips) > len(best):
            best = clips
        if len(best) >= NUM_CLIPS:
            break

    elapsed = time.time() - t0

    if not best:
        raise SystemExit("No valid clips found. Try a different prompt or model.")

    with open(OUTPUT_FILE, "w", encoding="utf-8") as f:
        json.dump(
            {"prompt": USER_PROMPT, "provider": PROVIDER,
             "usage": total_usage, "clips": best},
            f, ensure_ascii=False, indent=2,
        )

    print("========== CLIPS ==========\n")
    for c in best:
        print("#{}  [{:.2f}s - {:.2f}s]  ({:.0f}s)".format(
            c["rank"], c["start"], c["end"], c["duration"]))
        print("   Title:    {}".format(c["title"]))
        print("   Why:      {}".format(c["reason"]))
        print("   Hashtags: {}\n".format(" ".join(c["hashtags"])))

    print("Time: {:.1f}s | Tokens in/out: {}/{}".format(
        elapsed, total_usage["input_tokens"], total_usage["output_tokens"]))
    print("Saved: {}".format(OUTPUT_FILE))


if __name__ == "__main__":
    main()