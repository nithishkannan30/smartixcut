"""
One-time patch for YOUR api.py (it keeps your Cloudinary changes, it only adds 4 small things):
  - a `quality` option ("hd" or "fast") and a `captions` style block on new jobs
  - the app writes them to the job folder as options.json, which render.py reads

Run it next to api.py:
    python patch_api.py            (edits api.py, keeps a copy as api.py.bak)

If an anchor line is not found it changes NOTHING and tells you which one, so you can send me api.py.
"""
import sys
from pathlib import Path

TARGET = Path(sys.argv[1] if len(sys.argv) > 1 else "api.py")

CAPTION_CLASS = '''class CaptionOpts(BaseModel):
    enabled: bool = True
    style: Literal["outline", "box", "karaoke"] = "outline"
    size: Literal["small", "medium", "large"] = "medium"
    position: Literal["bottom", "middle", "top"] = "bottom"
    color: str = Field(default="#FFFFFF", pattern=r"^#[0-9a-fA-F]{6}$")
    highlight: str = Field(default="#FFE600", pattern=r"^#[0-9a-fA-F]{6}$")
    uppercase: bool = False


'''

EDITS = [
    ("from dotenv import load_dotenv\n",
     "from typing import Literal\n\nfrom dotenv import load_dotenv\n"),
    ("class JobIn(BaseModel):\n",
     CAPTION_CLASS + "class JobIn(BaseModel):\n"),
    ("    num_clips: int = Field(default=3, ge=1, le=5)\n",
     "    num_clips: int = Field(default=3, ge=1, le=5)\n"
     "    quality: Literal[\"hd\", \"fast\"] = \"hd\"\n"
     "    captions: CaptionOpts = Field(default_factory=CaptionOpts)\n"),
    ("    executor.submit(run_job, job_id)\n",
     "    job_dir = JOBS_DIR / job_id\n"
     "    job_dir.mkdir(parents=True, exist_ok=True)\n"
     "    (job_dir / \"options.json\").write_text(\n"
     "        json.dumps({\"quality\": body.quality, \"captions\": body.captions.model_dump()}),\n"
     "        encoding=\"utf-8\")\n"
     "    executor.submit(run_job, job_id)\n"),
]


def main():
    if not TARGET.exists():
        raise SystemExit("Can't find {}. Run this in the folder that has api.py.".format(TARGET))
    text = TARGET.read_text(encoding="utf-8")
    if "class CaptionOpts" in text:
        raise SystemExit("api.py is already patched. Nothing to do.")
    for old, _ in EDITS:
        n = text.count(old)
        if n != 1:
            raise SystemExit("Not patched. Expected exactly one copy of this line in api.py "
                             "but found {}:\n    {}\nSend me your api.py and I will merge it.".format(n, old.strip()))
    for old, new in EDITS:
        text = text.replace(old, new, 1)
    TARGET.with_suffix(".py.bak").write_text(TARGET.read_text(encoding="utf-8"), encoding="utf-8")
    TARGET.write_text(text, encoding="utf-8")
    print("api.py patched (backup saved as api.py.bak). Restart the server.")


if __name__ == "__main__":
    main()