import os
import re
import json
import time
import tempfile
import subprocess
from dotenv import load_dotenv
from groq import Groq

load_dotenv()
API_KEY = os.getenv("GROQ_API_KEY")
if not API_KEY:
    raise ValueError("GROQ_API_KEY not found in .env")
client = Groq(api_key=API_KEY)

# ---------- settings ----------
INPUT_FILE = "tamil_audio.mp3"   # change to tamil_audio.mp3 for the long one
MODEL = "whisper-large-v3"            # also try "whisper-large-v3-turbo"
LANGUAGE = "ta"
MIN_CHUNK = 5.0      # seconds
MAX_CHUNK = 20.0     # seconds
SILENCE_DB = "-35dB"
SILENCE_MIN = 0.4    # seconds of quiet that counts as a pause


def run(cmd):
    r = subprocess.run(cmd, capture_output=True, text=True,
                       encoding="utf-8", errors="replace")
    if r.returncode != 0:
        raise RuntimeError(r.stderr[-500:])
    return r


def get_duration(path):
    r = run(["ffprobe", "-v", "error", "-show_entries", "format=duration",
             "-of", "default=nw=1:nk=1", path])
    return float(r.stdout.strip())


def to_wav(src, dst):
    run(["ffmpeg", "-y", "-i", src, "-vn", "-ac", "1", "-ar", "16000", dst])


def find_silence_cuts(wav):
    """Return the midpoint of every pause, these are safe places to cut."""
    r = subprocess.run(
        ["ffmpeg", "-i", wav, "-af",
         f"silencedetect=noise={SILENCE_DB}:d={SILENCE_MIN}", "-f", "null", "-"],
        capture_output=True, text=True, encoding="utf-8", errors="replace")
    starts = [float(x) for x in re.findall(r"silence_start: ([\d.]+)", r.stderr)]
    ends = [float(x) for x in re.findall(r"silence_end: ([\d.]+)", r.stderr)]
    return [(s + e) / 2 for s, e in zip(starts, ends)]


def make_chunks(duration, cuts):
    """Greedy: from each start, cut at the last pause before MAX_CHUNK."""
    chunks, start = [], 0.0
    while start < duration - 0.05:
        limit = start + MAX_CHUNK
        if limit >= duration:
            end = duration
        else:
            options = [c for c in cuts if start + MIN_CHUNK <= c <= limit]
            end = max(options) if options else limit
        chunks.append((start, end))
        start = end
    return chunks


def cut_chunk(wav, start, end, dst):
    run(["ffmpeg", "-y", "-ss", f"{start:.3f}", "-t", f"{end - start:.3f}",
         "-i", wav, "-ac", "1", "-ar", "16000", dst])


def transcribe_chunk(path):
    for attempt in range(3):
        try:
            with open(path, "rb") as f:
                return client.audio.transcriptions.create(
                    file=(os.path.basename(path), f.read()),
                    model=MODEL,
                    language=LANGUAGE,
                    response_format="verbose_json",
                    timestamp_granularities=["word"],
                )
        except Exception as e:
            print(f"   retry {attempt + 1}: {e}")
            time.sleep(2 * (attempt + 1))
    raise RuntimeError("Groq failed after 3 tries")


def val(obj, key):
    return obj[key] if isinstance(obj, dict) else getattr(obj, key)


def words_to_lines(words, max_words=7, max_secs=3.5, max_gap=0.8):
    """Group words into caption-sized lines."""
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
    return [{"start": l[0]["start"], "end": l[-1]["end"],
             "text": " ".join(x["word"] for x in l)} for l in lines]


def main():
    t0 = time.time()
    all_words = []

    with tempfile.TemporaryDirectory() as tmp:
        wav = os.path.join(tmp, "full.wav")
        to_wav(INPUT_FILE, wav)
        duration = get_duration(wav)
        chunks = make_chunks(duration, find_silence_cuts(wav))
        print(f"Audio: {duration:.1f}s -> {len(chunks)} chunks\n")

        for i, (s, e) in enumerate(chunks, 1):
            p = os.path.join(tmp, f"chunk_{i}.wav")
            cut_chunk(wav, s, e, p)
            result = transcribe_chunk(p)
            got = getattr(result, "words", None) or []
            for w in got:
                text = val(w, "word").strip()
                if text:
                    all_words.append({
                        "word": text,
                        "start": round(s + val(w, "start"), 2),
                        "end": round(s + val(w, "end"), 2),
                    })
            print(f"chunk {i}/{len(chunks)} [{s:.1f}s - {e:.1f}s] -> {len(got)} words")

    lines = words_to_lines(all_words)

    print("\n========== CAPTION LINES ==========\n")
    for l in lines:
        print(f"[{l['start']:.2f}s - {l['end']:.2f}s] {l['text']}")

    with open("result.json", "w", encoding="utf-8") as f:
        json.dump({"words": all_words, "lines": lines}, f,
                  ensure_ascii=False, indent=2)

    elapsed = time.time() - t0
    print(f"\nTotal time: {elapsed:.1f}s for {duration:.1f}s of audio")
    print("Saved: result.json")


if __name__ == "__main__":
    main()