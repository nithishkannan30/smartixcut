"""
Usage:
    python transcribe_chunked.py                      (uses the defaults below)
    python transcribe_chunked.py tamil_audio.mp3 ta   (file, language code)
    python transcribe_chunked.py myvideo.mp4 hi       (video files work too)

Language codes: ta = Tamil, hi = Hindi, mr = Marathi, en = English

New: every caption line gets a confidence check. Lines that look like
hallucinated / garbled text are flagged "low_conf" so the next steps can
avoid putting them into clips.
"""
import os
import re
import sys
import json
import io
import time
import wave
import subprocess
from concurrent.futures import ThreadPoolExecutor
from dotenv import load_dotenv
from groq import Groq

try:
    import numpy as np
except ImportError:
    raise SystemExit("numpy is missing. Run:  pip install numpy")

load_dotenv()
API_KEY = os.getenv("GROQ_API_KEY")
if not API_KEY:
    raise ValueError("GROQ_API_KEY not found in .env")
client = Groq(api_key=API_KEY, max_retries=0, timeout=90)   # we do our own retries below

# ---------------- settings ----------------
INPUT_FILE = sys.argv[1] if len(sys.argv) > 1 else "tamil_audio.mp3"
LANGUAGE = sys.argv[2] if len(sys.argv) > 2 else "ta"
MODEL = os.getenv("GROQ_STT_MODEL", "whisper-large-v3")  # or whisper-large-v3-turbo
WORKERS = int(os.getenv("STT_WORKERS", "12"))            # parallel requests
STT_PROMPT = os.getenv("STT_PROMPT", "")                 # optional hint for Whisper

SR = 16000            # samples per second sent to Whisper
WIN = 800             # loudness window: 800 samples = 50 ms
MIN_CHUNK = 5.0       # seconds
BASE_MAX_CHUNK = float(os.getenv("STT_CHUNK_SECS", "25"))   # normal longest chunk
CHUNK_CAP = float(os.getenv("STT_CHUNK_CAP", "75"))         # never longer than this
# Groq limits how many requests you can send per minute (Whisper: about 20/min, check
# console.groq.com/settings/limits). Long videos would blow past that with 25 s chunks,
# so chunks grow just enough to keep the request count under this number.
MAX_REQUESTS = int(os.getenv("STT_MAX_REQUESTS", "18"))
# Chunk cutting: we measure loudness every 50 ms and cut each chunk at the quietest
# moment between MIN_CHUNK and MAX_CHUNK. This works even with background music,
# where there is no true silence. Cuts closer to MAX_CHUNK get a small bonus so we
# don't make lots of tiny chunks.
EARLY_CUT_PENALTY_DB_PER_SEC = 0.6

# Confidence thresholds (starting points, tune them on your own videos)
LOGPROB_BAD = -1.0        # average log-probability below this = unsure
NOSPEECH_BAD = 0.6        # probability the segment is not speech
# The repetition check was built for English; Tamil/Hindi text in UTF-8 compresses
# differently and trips it on perfectly good lines, so it is OFF for those languages
# until you tune it. Look at the cr= numbers in the output, then set COMPRESSION_BAD in .env.
COMPRESSION_BAD = float(os.getenv("COMPRESSION_BAD", "2.4" if LANGUAGE == "en" else "999"))

SCRIPT_RANGES = {"ta": (0x0B80, 0x0BFF), "hi": (0x0900, 0x097F), "mr": (0x0900, 0x097F)}


def decode_pcm(src):
    """Decode the audio ONCE straight into memory: mono, 16 kHz, 16-bit."""
    r = subprocess.run(["ffmpeg", "-v", "error", "-i", src, "-vn", "-ac", "1",
                        "-ar", str(SR), "-f", "s16le", "-"], capture_output=True)
    if r.returncode != 0 or not r.stdout:
        raise RuntimeError("could not read audio: " + r.stderr.decode("utf-8", "replace")[-400:])
    return r.stdout


def get_energy(pcm):
    """Loudness (dB) of every 50 ms window: (times, db) as numpy arrays."""
    x = np.frombuffer(pcm, dtype=np.int16)
    n = len(x) // WIN
    if n == 0:
        return np.zeros(0), np.zeros(0)
    f = x[:n * WIN].astype(np.float32).reshape(n, WIN)
    rms = np.sqrt((f * f).mean(axis=1)) / 32768.0
    db = 20 * np.log10(np.maximum(rms, 1e-5))                # floor at -100 dB
    times = (np.arange(n) + 0.5) * WIN / SR                  # middle of each window
    return times, db


def smooth(db, k=6):
    """Moving average over the last k windows (6 x 50 ms = 0.3 s)."""
    c = np.concatenate(([0.0], np.cumsum(db)))
    i = np.arange(1, len(db) + 1)
    lo = np.maximum(i - k, 0)
    return (c[i] - c[lo]) / (i - lo)


def make_chunks(duration, times, db, max_chunk):
    """Cut each chunk at the quietest moment between MIN_CHUNK and max_chunk."""
    level = smooth(db) if len(db) else db
    chunks, start = [], 0.0
    while start < duration - 0.05:
        limit = start + max_chunk
        if limit >= duration:
            end = duration
        else:
            i0 = int(np.searchsorted(times, start + MIN_CHUNK, side="left"))
            i1 = int(np.searchsorted(times, limit, side="right"))
            if i1 > i0:
                cost = level[i0:i1] + EARLY_CUT_PENALTY_DB_PER_SEC * (limit - times[i0:i1])
                end = float(times[i0 + int(np.argmin(cost))])
            else:
                end = limit
        chunks.append((start, end))
        start = end
    return chunks


def wav_bytes(pcm, start, end):
    """A small in-memory .wav for one chunk (no temp files, no extra ffmpeg runs)."""
    a, b = int(round(start * SR)) * 2, int(round(end * SR)) * 2
    buf = io.BytesIO()
    with wave.open(buf, "wb") as w:
        w.setnchannels(1)
        w.setsampwidth(2)
        w.setframerate(SR)
        w.writeframes(pcm[a:b])
    return buf.getvalue()


def retry_after(err):
    """Seconds Groq asks us to wait (it sends a retry-after header on 429), else None."""
    try:
        return float(err.response.headers.get("retry-after"))
    except Exception:
        return None


def transcribe_chunk(job):
    name, data = job
    extra = {"prompt": STT_PROMPT} if STT_PROMPT else {}
    for attempt in range(6):
        try:
            return client.audio.transcriptions.create(
                file=(name, data),
                model=MODEL,
                language=LANGUAGE,
                response_format="verbose_json",
                timestamp_granularities=["word", "segment"],
                temperature=0.0,
                **extra,
            )
        except Exception as e:
            if attempt == 5:
                raise RuntimeError("Groq failed after 6 tries on {}: {}".format(name, str(e)[:200]))
            wait = min(retry_after(e) or 2 * (attempt + 1), 30)
            print("   retry {} for {} in {:.0f}s: {}".format(attempt + 1, name, wait, str(e)[:100]))
            time.sleep(wait)


def get(obj, key, default=None):
    if isinstance(obj, dict):
        return obj.get(key, default)
    return getattr(obj, key, default)


def clean_text(text):
    """Remove Whisper's internal tags like <|ar|> or <|tl|> that sometimes leak into the text."""
    return re.sub(r"<\|[^|>]*\|>", "", text).strip()


# ---------------- quality checks ----------------
def is_allowed_char(ch, lang):
    o = ord(ch)
    if o < 128:
        return True
    if 0x2000 <= o <= 0x206F or 0x00A0 <= o <= 0x00BF or 0x20A0 <= o <= 0x20CF:
        return True   # punctuation, nbsp, currency
    rng = SCRIPT_RANGES.get(lang)
    return bool(rng and rng[0] <= o <= rng[1])


def script_problem(text, lang):
    """Catch garbage like Arabic/Greek letters or Latin letters stuck inside a Tamil word."""
    bad = sorted(set(ch for ch in text if not is_allowed_char(ch, lang)))
    if bad:
        return "foreign characters " + "".join(bad)[:6]
    rng = SCRIPT_RANGES.get(lang)
    if rng:
        lo, hi = chr(rng[0]), chr(rng[1])
        if re.search("[{0}-{1}][A-Za-z]+[{0}-{1}]".format(lo, hi), text):
            return "latin letters inside a word"
    return None


def attach_quality(words, segments):
    """Give each word the confidence numbers of the segment it falls in."""
    segs = [(get(s, "start", 0.0), get(s, "end", 0.0), get(s, "avg_logprob"),
             get(s, "no_speech_prob"), get(s, "compression_ratio")) for s in segments]
    for w in words:
        w["lp"] = w["ns"] = w["cr"] = None
        if not segs:
            continue
        mid = (w["start"] + w["end"]) / 2
        seg = next((s for s in segs if s[0] <= mid <= s[1]), None)
        if seg is None:
            seg = min(segs, key=lambda s: min(abs(mid - s[0]), abs(mid - s[1])))
        w["lp"], w["ns"], w["cr"] = seg[2], seg[3], seg[4]


def words_to_lines(words, max_words=7, max_secs=3.5, max_gap=0.8):
    """Group words into caption-sized lines, with no overlaps, and judge each line."""
    lines, cur = [], []
    for w in words:
        if cur:
            too_long = len(cur) >= max_words
            too_slow = w["end"] - cur[0]["start"] > max_secs
            big_gap = w["start"] - cur[-1]["end"] > max_gap
            if too_long or too_slow or big_gap:
                lines.append(cur)
                cur = []
        cur.append(w)
    if cur:
        lines.append(cur)

    out = []
    for l in lines:
        text = " ".join(x["word"] for x in l)
        lps = [x["lp"] for x in l if x.get("lp") is not None]
        nss = [x["ns"] for x in l if x.get("ns") is not None]
        crs = [x["cr"] for x in l if x.get("cr") is not None]
        lp = round(sum(lps) / len(lps), 2) if lps else None
        ns = round(max(nss), 2) if nss else None
        cr = round(max(crs), 2) if crs else None

        reasons = []
        if lp is not None and lp < LOGPROB_BAD:
            reasons.append("unsure")
        if ns is not None and ns > NOSPEECH_BAD:
            reasons.append("maybe not speech")
        if cr is not None and cr > COMPRESSION_BAD:
            reasons.append("repetitive")
        sp = script_problem(text, LANGUAGE)
        if sp:
            reasons.append(sp)

        out.append({"start": l[0]["start"], "end": l[-1]["end"], "text": text,
                    "lp": lp, "ns": ns, "cr": cr,
                    "low_conf": bool(reasons), "reason": ", ".join(reasons)})

    for i in range(len(out) - 1):
        if out[i]["end"] > out[i + 1]["start"]:
            out[i]["end"] = out[i + 1]["start"]
    return out


def main():
    t_total = time.time()
    all_words = []

    t = time.time()
    pcm = decode_pcm(INPUT_FILE)
    duration = len(pcm) / 2 / SR
    times, db = get_energy(pcm)
    max_chunk = min(CHUNK_CAP, max(BASE_MAX_CHUNK, duration / MAX_REQUESTS * 1.15))
    chunks = make_chunks(duration, times, db, max_chunk)
    t_prep = time.time() - t
    workers = max(1, min(WORKERS, len(chunks)))
    print("Audio: {:.1f}s -> {} chunks (up to {:.0f}s each, cut at the quietest moments; "
          "prep {:.1f}s, {} parallel workers)\n".format(
              duration, len(chunks), max_chunk, t_prep, workers))

    # transcribe in parallel; map() keeps the original order
    t = time.time()
    jobs = [("chunk_{}.wav".format(i), wav_bytes(pcm, s, e)) for i, (s, e) in enumerate(chunks, 1)]
    with ThreadPoolExecutor(max_workers=workers) as pool:
        results = list(pool.map(transcribe_chunk, jobs))
    t_stt = time.time() - t

    # stitch back together with each chunk's time offset
    for i, ((s, e), result) in enumerate(zip(chunks, results), 1):
        got = get(result, "words", None) or []
        chunk_words = []
        for w in got:
            text = clean_text(str(get(w, "word", "")))
            if text:
                chunk_words.append({
                    "word": text,
                    "start": float(get(w, "start", 0.0)),
                    "end": float(get(w, "end", 0.0)),
                })
        attach_quality(chunk_words, get(result, "segments", None) or [])
        for w in chunk_words:
            w["start"] = round(s + w["start"], 2)
            w["end"] = round(s + w["end"], 2)
        all_words.extend(chunk_words)
        print("chunk {}/{} [{:.1f}s - {:.1f}s] -> {} words".format(
            i, len(chunks), s, e, len(chunk_words)))

    lines = words_to_lines(all_words)

    print("\n========== CAPTION LINES ==========\n")
    for l in lines:
        mark = ""
        if l["low_conf"]:
            mark = "    <-- LOW CONFIDENCE ({}; lp={} ns={} cr={})".format(
                l["reason"], l["lp"], l["ns"], l["cr"])
        print("[{:.2f}s - {:.2f}s] {}{}".format(l["start"], l["end"], l["text"], mark))

    flagged = [l for l in lines if l["low_conf"]]
    flagged_secs = sum(l["end"] - l["start"] for l in flagged)
    print("\nFlagged {} of {} lines as low confidence ({:.0f}s of {:.0f}s). "
          "Compare the flags with the lines you know are garbled.".format(
              len(flagged), len(lines), flagged_secs, duration))

    with open("result.json", "w", encoding="utf-8") as f:
        json.dump({"source": INPUT_FILE, "language": LANGUAGE,
                   "audio_seconds": round(duration, 2),
                   "stt_model": MODEL, "stt_requests": len(chunks),
                   "billed_audio_seconds": round(sum(max(10.0, e - s) for s, e in chunks), 1),
                   "words": all_words, "lines": lines},
                  f, ensure_ascii=False, indent=2)

    total = time.time() - t_total
    print("\nPrep: {:.1f}s | Speech-to-text: {:.1f}s | Total: {:.1f}s "
          "for {:.1f}s of audio".format(t_prep, t_stt, total, duration))
    print("Saved: result.json")


if __name__ == "__main__":
    main()