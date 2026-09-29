"""Collect High Court orders from the public AWS dataset (CC-BY-4.0, Dattam Labs) onto the Modal volume.

  modal run --detach modal/collect.py

Two pools, split later by CNR so no case is on both sides of train and test:
  - daily: Delhi High Court orders (notices, appearance, exemptions, interim orders, withdrawals): the High Court
    orders closest in shape to a trial court's order sheet. No disposal label in the metadata.
  - disposal: final orders and judgments from every court whose metadata fills `disposal_nature`, sampled across
    courts and outcomes (capped per outcome so "dismissed" does not drown the rest).
Text comes from the PDFs (pdftotext); the metadata `description` is only the first ~290 characters.
"""
import concurrent.futures as cf
import io
import json
import os
import random
import re
import subprocess
import urllib.parse
import urllib.request

import modal

BUCKET = "https://indian-high-court-judgments.s3.amazonaws.com"
image = modal.Image.debian_slim(python_version="3.12").apt_install("poppler-utils").pip_install("pandas", "pyarrow")
app = modal.App("nyaya-collect", image=image)
vol = modal.Volume.from_name("nyaya-data", create_if_missing=True)

YEARS = (2023, 2024)
DAILY_TARGET, DISPOSAL_TARGET = 2500, 4200
PER_OUTCOME_CAP = 60


def ls(prefix: str) -> tuple[list[str], list[str]]:
    q = urllib.parse.urlencode({"list-type": "2", "prefix": prefix, "delimiter": "/", "max-keys": 1000})
    body = urllib.request.urlopen(f"{BUCKET}/?{q}", timeout=60).read().decode()
    return (re.findall(r"<CommonPrefixes><Prefix>(.*?)</Prefix></CommonPrefixes>", body), re.findall(r"<Key>(.*?)</Key>", body))


def fetch(key: str) -> bytes:
    return urllib.request.urlopen(f"{BUCKET}/{urllib.parse.quote(key)}", timeout=120).read()


def metadata(year: int) -> list:
    import pandas as pd
    frames = []
    courts, _ = ls(f"metadata/parquet/year={year}/")
    for court in courts:
        benches, _ = ls(court)
        for bench in benches:
            _, files = ls(bench)
            name = next((f for f in files if f.endswith("/metadata.parquet")), None) or next((f for f in files if f.endswith(".parquet")), None)
            if not name:
                continue
            try:
                df = pd.read_parquet(io.BytesIO(fetch(name)))
            except Exception as e:  # noqa: BLE001
                print("skip", name, e, flush=True)
                continue
            m = re.search(r"court=([^/]+)/bench=([^/]+)/", name)
            df["court_part"], df["bench_part"], df["year_part"] = m.group(1), m.group(2), year
            frames.append(df[[c for c in ("title", "cnr", "decision_date", "disposal_nature", "pdf_link", "court",
                                           "court_part", "bench_part", "year_part", "judge") if c in df.columns]])
            print(f"{year} {m.group(1)}/{m.group(2)}: {len(df)} rows", flush=True)
    return frames


def case_type(title: str) -> str:
    m = re.match(r"\s*([A-Z][A-Z\.\(\)&\- ]*?)\s*/\s*\d", title or "")
    return m.group(1).strip() if m else ""


def text_of(row: dict) -> dict | None:
    key = f"data/pdf/year={row['year_part']}/court={row['court_part']}/bench={row['bench_part']}/{os.path.basename(row['pdf_link'])}"
    try:
        pdf = fetch(key)
        out = subprocess.run(["pdftotext", "-q", "-", "-"], input=pdf, capture_output=True, timeout=60).stdout.decode("utf-8", "ignore")
    except Exception:  # noqa: BLE001
        return None
    text = re.sub(r"[ \t]+", " ", out).strip()
    if len(text) < 300:
        return None
    return {**row, "case_type": case_type(row["title"]), "text": text[:60000], "full_chars": len(text)}


@app.function(cpu=8, memory=16384, timeout=4 * 3600, volumes={"/vol": vol})
def collect() -> dict:
    import pandas as pd
    rng = random.Random(7)
    meta = pd.concat([f for y in YEARS for f in metadata(y)], ignore_index=True)
    meta = meta[meta.pdf_link.notna() & (meta.pdf_link.str.len() > 0)]
    meta["disposal_nature"] = meta.disposal_nature.fillna("").str.strip()
    daily = meta[meta.court_part == "7_26"].sample(frac=1, random_state=1).head(DAILY_TARGET * 2)
    disp = meta[(meta.court_part != "7_26") & (meta.disposal_nature != "")]
    picks = []
    for (court, outcome), g in disp.groupby(["court_part", disp.disposal_nature.str.lower()]):
        picks.append(g.sample(min(len(g), PER_OUTCOME_CAP), random_state=1))
    disp = pd.concat(picks).sample(frac=1, random_state=2).head(DISPOSAL_TARGET * 2)
    print(f"candidates: daily {len(daily)}, disposal {len(disp)} from {disp.court_part.nunique()} courts", flush=True)

    out = {}
    for pool, frame, target in (("daily", daily, DAILY_TARGET), ("disposal", disp, DISPOSAL_TARGET)):
        rows = [dict(r, decision_date=str(r["decision_date"])[:10], pool=pool) for r in frame.to_dict("records")]
        kept = []
        with cf.ThreadPoolExecutor(48) as ex:
            for doc in ex.map(text_of, rows):
                if doc:
                    kept.append(doc)
                if len(kept) >= target:
                    break
        path = f"/vol/hc/{pool}.jsonl"
        os.makedirs("/vol/hc", exist_ok=True)
        with open(path, "w") as h:
            for d in kept:
                h.write(json.dumps(d, ensure_ascii=False) + "\n")
        vol.commit()
        out[pool] = len(kept)
        print(f"{pool}: kept {len(kept)} documents -> {path}", flush=True)
    return out


@app.local_entrypoint()
def main():
    print(collect.remote())
