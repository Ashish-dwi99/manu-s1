"""Record the film (#film) with spoken narration.

  ~/Desktop/Plank/.venv/bin/python demo/record_film.py [--voice Tara]

1. Narration per scene, spoken by macOS's Indian-English voice, with every number and every verdict taken from the
   run's data (page_data.json), so the voice can never claim something the model did not do.
2. Scene lengths follow the narration (passed to the page before it loads).
3. The page records when each scene starts; each clip is placed at that moment and mixed under the video.
"""
import argparse
import glob
import json
import os
import shutil
import subprocess

from playwright.sync_api import sync_playwright

HERE = os.path.dirname(os.path.abspath(__file__))
PAGE = os.path.join(HERE, "manu_case_desk.html")
WORK = os.path.join(HERE, "film_work")
W, H = 1920, 1080
PLAIN = {"in_time": "on time", "late": "late", "premature": "filed too early: the complaint is premature",
         "late_condonation_sought": "late, but with an application to condone the delay", "cannot_tell": "can't tell",
         "within_validity": "presented within validity", "after_validity": "presented after validity"}


def narration(d: dict) -> dict:
    o = d["cbi"]["orders"]
    years = int(o[-1]["date"][:4]) - int(o[0]["date"][:4])
    pages, secs = d["cbi"]["pages"], sum(x["ms"] for x in o) / 1000
    hours = round(pages * 2 / 60)
    gaps = sum(1 for x in o if x["next"] and x["next"]["answer"] == "differs")
    hc = d["hc"]
    text = {
        "hook": f"This is a real criminal trial. {len(o)} court orders. {pages} pages. {years} years in court.",
        "race": f"What happened in this case? Reading it by hand would take about {hours} hours. Watch Manu read every order.",
        "race_done": f"Every order read, every question answered, in {secs:.0f} seconds, on one G P U.",
        "attend": f"Who came to court, on every date, for {years} years. In person, or only through counsel. Where an order records an accused in person, Manu agreed {d['cbi']['inperson_check']}.",
        "ground": "Every answer rests on a line in the order. Manu answers only from the record, and never writes its own text.",
        "gaps": (f"And it finds what is missing. In {gaps} places, the order fixed one date, but the next order on file is from another. "
                 "Worth checking before the next hearing.") if gaps else "It also checks that every date fixed was kept on file.",
        "scale": (f"{hc['n']} real High Court orders from across India, sorted in {hc['ms'] / 1000:.0f} seconds. "
                  f"Where the court's own database records a different outcome, Manu flags it for a person to check."),
        "speed": (f"How fast? {d['run']['median_ms']:.0f} milliseconds for a decision, measured. {d['run']['n']:,} decisions in "
                  f"{d['run']['total_s']:.0f} seconds, on one G P U. No internet needed."),
        "work": ("What can it do for a court today? Check deadlines and limitation. Turn order sheets into a docket. "
                 "Track who appeared. Clean up pendency. Route cases to the right special court. And audit the court's own records."),
        "close": "Manu. It runs inside the court, so nothing leaves the building. It checks procedure, never the merits. And when the record is silent, it says so.",
    }
    intro = "Now, a cheque bounce complaint. Three legal deadlines. The court calculator does the dates, and Manu reads the complaint. "
    for i, s in enumerate(d["ni"]):
        final = next(a for a in s["answers"] if a["question"].startswith("Complaint"))
        verdict = PLAIN.get(final["answer"], final["answer"].replace("_", " "))
        line = f"Manu's answer: {verdict}."
        if final["answer"] == "cannot_tell":
            line = "The record does not say when the notice was received. So Manu's answer is: can't tell. Ask for the postal tracking report."
        if final["answer"] != final["expected"]:
            line += " That is not what the Act says; a person would catch it."
        text[f"ni{i}"] = (intro if i == 0 else "") + line
    return text


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--voice", default="Tara")
    ap.add_argument("--rate", type=int, default=172)
    a = ap.parse_args()
    d = json.load(open(os.path.join(HERE, "page_data.json")))
    shutil.rmtree(WORK, ignore_errors=True)
    os.makedirs(WORK)
    clips, lengths = {}, {}
    for k, t in narration(d).items():
        aiff, wav = os.path.join(WORK, f"{k}.aiff"), os.path.join(WORK, f"{k}.wav")
        subprocess.run(["say", "-v", a.voice, "-r", str(a.rate), "-o", aiff, t], check=True)
        subprocess.run(["ffmpeg", "-y", "-loglevel", "error", "-i", aiff, "-ar", "48000", "-ac", "2", wav], check=True)
        dur = float(subprocess.run(["ffprobe", "-v", "error", "-show_entries", "format=duration", "-of", "csv=p=0", wav],
                                   capture_output=True, text=True).stdout.strip())
        clips[k], lengths[k] = wav, dur
    json.dump({"text": narration(d), "lengths": lengths}, open(os.path.join(WORK, "narration.json"), "w"), indent=1)

    with sync_playwright() as p:
        browser = p.chromium.launch()
        ctx = browser.new_context(viewport={"width": W, "height": H}, device_scale_factor=1, color_scheme="light",
                                  record_video_dir=WORK, record_video_size={"width": W, "height": H})
        ctx.add_init_script(f"window.__narr = {json.dumps(lengths)};")
        page = ctx.new_page()
        page.goto("file://" + PAGE + "#film")
        page.wait_for_function("window.__playDone === true", timeout=600_000, polling=500)
        times = page.evaluate("window.__sceneTimes")
        page.wait_for_timeout(1500)
        ctx.close()
        browser.close()
    video = glob.glob(os.path.join(WORK, "*.webm"))[0]
    order = [k for k in clips if k in times]
    inputs, filters = ["-i", video], []
    for i, k in enumerate(order, start=1):
        inputs += ["-i", clips[k]]
        ms = int(times[k] * 1000) + 250
        filters.append(f"[{i}:a]adelay={ms}|{ms}[a{i}]")
    mix = "".join(f"[a{i}]" for i in range(1, len(order) + 1))
    filters.append(f"{mix}amix=inputs={len(order)}:normalize=0[aout]")
    out = os.path.join(HERE, "manu_s1_demo.mp4")
    subprocess.run(["ffmpeg", "-y", "-loglevel", "error", *inputs, "-filter_complex", ";".join(filters), "-map", "0:v", "-map", "[aout]",
                    "-c:v", "libx264", "-pix_fmt", "yuv420p", "-crf", "19", "-preset", "slow", "-c:a", "aac", "-b:a", "160k",
                    "-movflags", "+faststart", "-shortest", out], check=True)
    missing = [k for k in clips if k not in times]
    print("film", out, f"{os.path.getsize(out) / 1e6:.1f} MB", "| scenes timed:", len(order), "| not shown:", missing)


if __name__ == "__main__":
    main()
