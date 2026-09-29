"""Record the demo walkthrough: Playwright opens the page at #play, records until the walkthrough ends, and
ffmpeg turns the recording into an MP4 that plays anywhere.

  ~/Desktop/Plank/.venv/bin/python demo/record.py
"""
import glob
import os
import shutil
import subprocess

from playwright.sync_api import sync_playwright

HERE = os.path.dirname(os.path.abspath(__file__))
PAGE = os.path.join(HERE, "manu_case_desk.html")
OUT = os.path.join(HERE, "recording")
W, H = 1440, 900

shutil.rmtree(OUT, ignore_errors=True)
os.makedirs(OUT)
with sync_playwright() as p:
    browser = p.chromium.launch()
    ctx = browser.new_context(viewport={"width": W, "height": H}, device_scale_factor=1, color_scheme="light",
                              record_video_dir=OUT, record_video_size={"width": W, "height": H})
    page = ctx.new_page()
    page.goto("file://" + PAGE + "#play")
    page.wait_for_function("window.__playDone === true", timeout=240_000, polling=500)
    page.wait_for_timeout(1500)
    ctx.close()
    browser.close()
webm = glob.glob(os.path.join(OUT, "*.webm"))[0]
mp4 = os.path.join(HERE, "manu_s1_walkthrough.mp4")
subprocess.run(["ffmpeg", "-y", "-loglevel", "error", "-i", webm, "-c:v", "libx264", "-pix_fmt", "yuv420p", "-crf", "20",
                "-preset", "slow", "-movflags", "+faststart", mp4], check=True)
print("recorded", mp4, f"{os.path.getsize(mp4) / 1e6:.1f} MB")
