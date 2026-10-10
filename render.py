"""
Turns clips.json + result.json + your video into finished vertical (9:16) clips
with burned-in captions.

Usage:
    python render.py myvideo.mp4

Needs (in the same folder): clips.json, result.json, and a fonts/ folder
(run `python get_fonts.py` once to create it).
Output: clips_out/clip_1.mp4, clip_2.mp4, ...
"""
import os
import sys
import json
import time
import subprocess
from concurrent.futures import ThreadPoolExecutor

# ---------------- settings ----------------
VIDEO = sys.argv[1] if len(sys.argv) > 1 else "video.mp4"
CLIPS_FILE = "clips.json"
RESULT_FILE = "result.json"
FONTS_DIR = "fonts"
WORK_DIR = "work"
OUT_DIR = "clips_out"

# Captions are designed on a 1080x1920 canvas; libass rescales them to whatever size we encode.
PLAY_W, PLAY_H = 1080, 1920
FONT_SIZE = 66
MARGIN_V = 380          # distance of captions from the bottom edge (px)

# Output size. 1280 (= 720x1280) renders about 2x faster than 1920 (= 1080x1920) and the
# files are smaller, which also makes uploads faster. Set RENDER_HEIGHT=1920 in .env for full HD.
OUT_H = int(os.getenv("RENDER_HEIGHT", "1280"))
OUT_W = OUT_H * 9 // 16 // 2 * 2
PRESET = os.getenv("RENDER_PRESET", "veryfast")   # ultrafast = quicker but files ~2x bigger
CRF = os.getenv("RENDER_CRF", "23")
RENDER_WORKERS = int(os.getenv("RENDER_WORKERS", "3"))

# Which font draws the main script of each language
SCRIPT_FONT = {
    "ta": "Noto Sans Tamil",
    "hi": "Noto Sans Devanagari",
    "mr": "Noto Sans Devanagari",
}
LATIN_FONT = "Noto Sans"   # used for English words/numbers inside any language


def run(cmd):
    r = subprocess.run(cmd, capture_output=True, text=True,
                       encoding="utf-8", errors="replace")
    if r.returncode != 0:
        raise RuntimeError("ffmpeg failed:\n" + r.stderr[-1200:])
    return r


def ass_time(t):
    t = max(t, 0.0)
    cs = int(round(t * 100))
    h, cs = divmod(cs, 360000)
    m, cs = divmod(cs, 6000)
    s, cs = divmod(cs, 100)
    return "{}:{:02d}:{:02d}.{:02d}".format(h, m, s, cs)


def escape_ass(text):
    return text.replace("\\", "").replace("{", "(").replace("}", ")").replace("\n", " ")


def tag_runs(text, main_font):
    """
    Split text into runs of ASCII (English/numbers) vs everything else, and
    give every run an explicit font. This avoids missing-glyph boxes when a
    Tamil/Hindi sentence has English words glued to it (e.g. 'timeஸ்').
    """
    text = escape_ass(text)
    runs, cur, cur_latin = [], "", None
    for ch in text:
        if ch == " ":
            cur += ch
            continue
        is_latin = ord(ch) < 128
        if cur_latin is None:
            cur_latin = is_latin
        if is_latin != cur_latin and cur.strip():
            runs.append((cur, cur_latin))
            cur = ""
            cur_latin = is_latin
        cur += ch
    if cur:
        runs.append((cur, cur_latin if cur_latin is not None else True))

    out = []
    for chunk, latin in runs:
        font = LATIN_FONT if latin else main_font
        out.append("{{\\fn{}}}{}".format(font, chunk))
    return "".join(out)


def build_ass(lines, clip_start, clip_end, language, path):
    main_font = SCRIPT_FONT.get(language, LATIN_FONT)
    header = "\n".join([
        "[Script Info]",
        "ScriptType: v4.00+",
        "PlayResX: {}".format(PLAY_W),
        "PlayResY: {}".format(PLAY_H),
        "WrapStyle: 0",
        "ScaledBorderAndShadow: yes",
        "",
        "[V4+ Styles]",
        "Format: Name, Fontname, Fontsize, PrimaryColour, SecondaryColour, OutlineColour, "
        "BackColour, Bold, Italic, Underline, StrikeOut, ScaleX, ScaleY, Spacing, Angle, "
        "BorderStyle, Outline, Shadow, Alignment, MarginL, MarginR, MarginV, Encoding",
        "Style: Default,{},{},&H00FFFFFF,&H00FFFFFF,&H00000000,&H80000000,-1,0,0,0,"
        "100,100,0,0,1,5,1,2,90,90,{},1".format(main_font, FONT_SIZE, MARGIN_V),
        "",
        "[Events]",
        "Format: Layer, Start, End, Style, Name, MarginL, MarginR, MarginV, Effect, Text",
    ])

    events = []
    for l in lines:
        if l["end"] <= clip_start or l["start"] >= clip_end:
            continue
        s = max(l["start"], clip_start) - clip_start
        e = min(l["end"], clip_end) - clip_start
        if e - s < 0.15:
            continue
        events.append("Dialogue: 0,{},{},Default,,0,0,0,,{}".format(
            ass_time(s), ass_time(e), tag_runs(l["text"], main_font)))

    with open(path, "w", encoding="utf-8") as f:
        f.write(header + "\n" + "\n".join(events) + "\n")
    return len(events)


def render_one(clip, lines, language):
    n = clip["rank"]
    ass_path = os.path.join(WORK_DIR, "clip_{}.ass".format(n)).replace("\\", "/")
    out_path = os.path.join(OUT_DIR, "clip_{}.mp4".format(n))
    count = build_ass(lines, clip["start"], clip["end"], language, ass_path)

    # crop to 9:16 FIRST, then scale: far fewer pixels go through the scaler
    vf = ("crop='min(iw,ih*9/16)':'min(ih,iw*16/9)',"
          "scale={w}:{h},"
          "ass={ass}:fontsdir={fonts}").format(
              w=OUT_W, h=OUT_H, ass=ass_path, fonts=FONTS_DIR)

    t = time.time()
    run(["ffmpeg", "-y",
         "-ss", "{:.3f}".format(clip["start"]),
         "-i", VIDEO,
         "-t", "{:.3f}".format(clip["end"] - clip["start"]),
         "-vf", vf,
         "-c:v", "libx264", "-preset", PRESET, "-crf", CRF,
         "-pix_fmt", "yuv420p",
         "-c:a", "aac", "-b:a", "128k",
         "-movflags", "+faststart",
         out_path])
    secs = time.time() - t
    print("clip {}: {:.0f}s long, {} caption lines, rendered in {:.1f}s -> {}".format(
        n, clip["end"] - clip["start"], count, secs, out_path))
    return out_path


def main():
    if not os.path.exists(VIDEO):
        raise SystemExit("Video not found: {}".format(VIDEO))
    if not os.path.isdir(FONTS_DIR):
        raise SystemExit("No fonts folder. Run:  python get_fonts.py")

    with open(CLIPS_FILE, encoding="utf-8") as f:
        clips = json.load(f)["clips"]
    with open(RESULT_FILE, encoding="utf-8") as f:
        result = json.load(f)
    lines = result["lines"]
    language = result.get("language", "ta")

    os.makedirs(WORK_DIR, exist_ok=True)
    os.makedirs(OUT_DIR, exist_ok=True)

    workers = max(1, min(RENDER_WORKERS, len(clips)))
    t0 = time.time()
    with ThreadPoolExecutor(max_workers=workers) as pool:
        list(pool.map(lambda c: render_one(c, lines, language), clips))

    print("\nRendered {} clip(s) at {}x{} in {:.1f}s ({} parallel). Open the {} folder.".format(
        len(clips), OUT_W, OUT_H, time.time() - t0, workers, OUT_DIR))


if __name__ == "__main__":
    main()