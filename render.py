"""
Turns clips.json + result.json + your video into finished vertical (9:16) clips
with burned-in captions.

Usage:
    python render.py myvideo.mp4

Needs (in the same folder): clips.json, result.json, and a fonts/ folder
(run `python get_fonts.py` once to create it).
Optional: options.json (written by the web app) with the user's caption style and quality:
    {"quality": "hd" | "fast",
     "captions": {"enabled": true, "style": "outline" | "box" | "karaoke",
                  "size": "small" | "medium" | "large", "position": "bottom" | "middle" | "top",
                  "color": "#FFFFFF", "highlight": "#FFE600", "uppercase": false}}
Output: clips_out/clip_1.mp4, clip_2.mp4, ...
"""
import os
import re
import sys
import json
import time
import subprocess
from concurrent.futures import ThreadPoolExecutor

# ---------------- settings ----------------
VIDEO = sys.argv[1] if len(sys.argv) > 1 else "video.mp4"
CLIPS_FILE = "clips.json"
RESULT_FILE = "result.json"
OPTIONS_FILE = "options.json"
FONTS_DIR = "fonts"
WORK_DIR = "work"
OUT_DIR = "clips_out"

# Captions are designed on a 1080x1920 canvas; libass rescales them to whatever size we encode.
PLAY_W, PLAY_H = 1080, 1920

# Output quality. HD = 1080x1920. Fast = 720x1280: renders about 2x quicker, softer picture.
QUALITY = {"hd": (1920, "21"), "fast": (1280, "23")}       # (height, x264 crf)
PRESET = os.getenv("RENDER_PRESET", "veryfast")             # ultrafast = quicker but files ~2x bigger
RENDER_WORKERS = int(os.getenv("RENDER_WORKERS", "3"))

# Which font draws the main script of each language
SCRIPT_FONT = {
    "ta": "Noto Sans Tamil",
    "hi": "Noto Sans Devanagari",
    "mr": "Noto Sans Devanagari",
}
LATIN_FONT = "Noto Sans"   # used for English words/numbers inside any language

# ---------------- caption options ----------------
DEFAULT_CAPTIONS = {"enabled": True, "style": "outline", "size": "medium", "position": "bottom",
                    "color": "#FFFFFF", "highlight": "#FFE600", "uppercase": False}
FONT_SIZES = {"small": 54, "medium": 66, "large": 82}
HEX_RE = re.compile(r"^#[0-9a-fA-F]{6}$")


def load_options():
    """Read options.json and fall back to safe defaults for anything missing or invalid."""
    raw = {}
    if os.path.exists(OPTIONS_FILE):
        try:
            with open(OPTIONS_FILE, encoding="utf-8") as f:
                raw = json.load(f)
        except (OSError, ValueError):
            raw = {}
    cap = dict(DEFAULT_CAPTIONS)
    given = raw.get("captions") if isinstance(raw.get("captions"), dict) else {}
    for k, default in DEFAULT_CAPTIONS.items():
        v = given.get(k, default)
        if k in ("color", "highlight"):
            v = v if isinstance(v, str) and HEX_RE.match(v) else default
        elif k in ("enabled", "uppercase"):
            v = bool(v)
        cap[k] = v
    if cap["style"] not in ("outline", "box", "karaoke"):
        cap["style"] = "outline"
    if cap["size"] not in FONT_SIZES:
        cap["size"] = "medium"
    if cap["position"] not in ("bottom", "middle", "top"):
        cap["position"] = "bottom"
    quality = raw.get("quality") if raw.get("quality") in QUALITY else "hd"
    return quality, cap


def ass_color(hex_rgb, alpha=0):
    """'#RRGGBB' -> ASS '&HAABBGGRR' (alpha 0 = solid, 255 = invisible)."""
    r, g, b = hex_rgb[1:3], hex_rgb[3:5], hex_rgb[5:7]
    return "&H{:02X}{}{}{}".format(alpha, b, g, r).upper()


# ---------------- helpers ----------------
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


def karaoke_text(line, words, event_start, main_font, upper):
    """Word-by-word highlight: each word gets a {\\kf} tag as long as it is spoken."""
    mine = [w for w in words if w["end"] > event_start and w["start"] >= line["start"] - 0.05
            and w["end"] <= line["end"] + 0.05]
    if not mine:
        return None
    parts, cursor = [], event_start
    for w in mine:
        gap = w["start"] - cursor
        if gap > 0.02:
            parts.append("{{\\k{}}}".format(int(round(gap * 100))))
        begin = max(w["start"], cursor)
        dur = max(w["end"] - begin, 0.02)
        text = w["word"].upper() if upper else w["word"]
        parts.append("{{\\kf{}}}{} ".format(max(1, int(round(dur * 100))), tag_runs(text, main_font)))
        cursor = max(cursor, w["end"])
    return "".join(parts).rstrip()


def build_ass(lines, words, clip_start, clip_end, language, cap, path):
    main_font = SCRIPT_FONT.get(language, LATIN_FONT)
    size = FONT_SIZES[cap["size"]]
    align, margin_v = {"bottom": (2, 380), "middle": (5, 0), "top": (8, 260)}[cap["position"]]
    base, hi = ass_color(cap["color"]), ass_color(cap["highlight"])

    if cap["style"] == "box":
        # a thick dark outline merges into one soft box behind the text (BorderStyle 3 draws a
        # separate box per font run, which looks patchy with mixed Tamil + English)
        border, outline, shadow, outline_col = 1, 20, 0, ass_color("#000000", 70)
    else:
        border, outline, shadow, outline_col = 1, 5, 1, ass_color("#000000")        # black outline
    primary, secondary = (hi, base) if cap["style"] == "karaoke" else (base, base)

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
        "Style: Default,{font},{size},{pri},{sec},{out},&H80000000,-1,0,0,0,"
        "100,100,0,0,{border},{outline},{shadow},{align},90,90,{mv},1".format(
            font=main_font, size=size, pri=primary, sec=secondary, out=outline_col,
            border=border, outline=outline, shadow=shadow, align=align, mv=margin_v),
        "",
        "[Events]",
        "Format: Layer, Start, End, Style, Name, MarginL, MarginR, MarginV, Effect, Text",
    ])

    events = []
    for l in lines:
        if l["end"] <= clip_start or l["start"] >= clip_end:
            continue
        s_abs = max(l["start"], clip_start)
        s = s_abs - clip_start
        e = min(l["end"], clip_end) - clip_start
        if e - s < 0.15:
            continue
        text = None
        if cap["style"] == "karaoke":
            text = karaoke_text(l, words, s_abs, main_font, cap["uppercase"])
        if text is None:
            plain = l["text"].upper() if cap["uppercase"] else l["text"]
            text = tag_runs(plain, main_font)
            if cap["style"] == "karaoke":                 # no word timing for this line: show it plain
                text = "{{\\1c{}}}".format(base) + text
        events.append("Dialogue: 0,{},{},Default,,0,0,0,,{}".format(ass_time(s), ass_time(e), text))

    with open(path, "w", encoding="utf-8") as f:
        f.write(header + "\n" + "\n".join(events) + "\n")
    return len(events)


def render_one(clip, lines, words, language, cap, out_w, out_h, crf):
    n = clip["rank"]
    ass_path = os.path.join(WORK_DIR, "clip_{}.ass".format(n)).replace("\\", "/")
    out_path = os.path.join(OUT_DIR, "clip_{}.mp4".format(n))

    # crop to 9:16 FIRST, then scale: far fewer pixels go through the scaler
    vf = "crop='min(iw,ih*9/16)':'min(ih,iw*16/9)',scale={}:{}:flags=lanczos".format(out_w, out_h)
    count = 0
    if cap["enabled"]:
        count = build_ass(lines, words, clip["start"], clip["end"], language, cap, ass_path)
        vf += ",ass={}:fontsdir={}".format(ass_path, FONTS_DIR)

    t = time.time()
    run(["ffmpeg", "-y",
         "-ss", "{:.3f}".format(clip["start"]),
         "-i", VIDEO,
         "-t", "{:.3f}".format(clip["end"] - clip["start"]),
         "-vf", vf,
         "-c:v", "libx264", "-preset", PRESET, "-crf", crf,
         "-pix_fmt", "yuv420p",
         "-c:a", "aac", "-b:a", "160k",
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
    words = result.get("words", [])
    language = result.get("language", "ta")

    quality, cap = load_options()
    out_h, crf = QUALITY[quality]
    out_w = out_h * 9 // 16 // 2 * 2
    print("Quality: {} ({}x{}) | captions: {}".format(
        quality, out_w, out_h, cap if cap["enabled"] else "off"))

    os.makedirs(WORK_DIR, exist_ok=True)
    os.makedirs(OUT_DIR, exist_ok=True)

    workers = max(1, min(RENDER_WORKERS, len(clips)))
    t0 = time.time()
    with ThreadPoolExecutor(max_workers=workers) as pool:
        list(pool.map(lambda c: render_one(c, lines, words, language, cap, out_w, out_h, crf), clips))

    print("\nRendered {} clip(s) at {}x{} in {:.1f}s ({} parallel). Open the {} folder.".format(
        len(clips), out_w, out_h, time.time() - t0, workers, OUT_DIR))


if __name__ == "__main__":
    main()