"""Teacher labels for High Court orders: open-weight gpt-oss-120b (Apache-2.0) on one Modal H100 with vLLM.

  modal run --detach modal/teach.py

Every question comes from the bank (bank/*.yaml). Each document is answered twice, the second time with the
questions and options in another order; a label is kept only when both passes agree. The first SMOKE documents
are a gate: if fewer than 90% of their answers parse into valid labels, the run stops before spending more.
No hosted API is used and no Claude output becomes a label.
"""
import json
import os
import random
import re
import time

import modal

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)
MODEL = "openai/gpt-oss-120b"
SMOKE = 24

# vLLM 0.30 runs on torch 2.13 / CUDA 13.0, and FlashInfer compiles kernels at start-up, so the image needs nvcc 13.0.
image = (modal.Image.from_registry("nvidia/cuda:13.0.1-devel-ubuntu24.04", add_python="3.12")
         .env({"CUDA_HOME": "/usr/local/cuda"})
         .pip_install("vllm>=0.11", "hf_transfer", "pyyaml")
         .env({"HF_HUB_ENABLE_HF_TRANSFER": "1", "HF_HOME": "/cache/hf"})
         .add_local_dir(os.path.join(ROOT, "bank"), "/bank"))
app = modal.App("nyaya-teach", image=image)
data = modal.Volume.from_name("nyaya-data")
cache = modal.Volume.from_name("nyaya-hf-cache", create_if_missing=True)

DOC_QUESTIONS = {"daily": ["ORD.TYP.01", "ORD.INT.01", "ORD.COS.01", "SRV.APR.01"],
                 "disposal": ["ORD.TYP.01", "ORD.OUT.01", "ORD.INT.01", "ORD.COS.01"]}
CITATION = re.compile(r"\(\d{4}\)\s*\d+\s*SCC\s*\d+|AIR\s*\d{4}\s*[A-Z][A-Za-z]*\s*\d+|\d{4}\s*SCC\s*OnLine\s*[A-Z][A-Za-z]*\s*\d+|\[\d{4}\]\s*\d+\s*S\.?C\.?R\.?\s*\d+")
CASE_NAME = re.compile(r"([A-Z][A-Za-z\.&' ]{2,60}?)\s+(?:v\.|vs\.?|versus)\s+([A-Z][A-Za-z\.&' ]{2,60}?)[,\s]*$")
PARTY_NOTE = {"SRV.APR.01": "Party asked about: the respondent (respondent No. 1 where there are several)."}
SYSTEM = ("You are a careful registry officer of an Indian court. Answer only from the document given, never from outside "
          "knowledge. When the document does not show the answer, choose cannot_tell.\nReasoning: medium")


def head_tail(text: str, head: int = 5000, tail: int = 4000) -> str:
    return text if len(text) <= head + tail else text[:head] + "\n[...]\n" + text[-tail:]


def citation_passage(text: str) -> tuple[str, str] | None:
    for m in CITATION.finditer(text):
        before = text[max(0, m.start() - 900):m.start()]
        name = CASE_NAME.search(before[-220:].replace("\n", " "))
        if name:
            case = f"{name.group(1).strip()} v. {name.group(2).strip()}"
            return text[max(0, m.start() - 900):m.end() + 400], case
    return None


def prompt(doc: str, qids: list[str], bank: dict, rng: random.Random | None) -> tuple[str, list[tuple[str, list[str]]]]:
    order = qids[:]
    if rng:
        rng.shuffle(order)
    lines, spec = [], []
    for i, qid in enumerate(order, 1):
        e = bank[qid]
        labels = list(e["labels"])
        if rng:
            rng.shuffle(labels)
        spec.append((qid, labels))
        note = f" {PARTY_NOTE[qid]}" if qid in PARTY_NOTE else ""
        opts = "\n".join(f"   - {k}: {e['labels'][k]}" for k in labels)
        lines.append(f"Q{i}. {e['question']}{note}\n  Options:\n{opts}")
    body = (f"DOCUMENT:\n{doc}\n\nQUESTIONS:\n" + "\n".join(lines) +
            "\n\nAnswer every question with exactly one option name. Return only JSON: {\"Q1\": \"option\", ...}")
    return body, spec


def parse(text: str, spec: list[tuple[str, list[str]]]) -> dict:
    text = text.split("assistantfinal")[-1]
    m = None
    for m in re.finditer(r"\{[^{}]*\}", text, re.S):
        pass
    if not m:
        return {}
    try:
        raw = json.loads(m.group(0))
    except json.JSONDecodeError:
        return {}
    out = {}
    for i, (qid, labels) in enumerate(spec, 1):
        v = str(raw.get(f"Q{i}", "")).strip().strip("'\"")
        if v in labels:
            out[qid] = v
    return out


@app.function(gpu="H100", timeout=6 * 3600, volumes={"/vol": data, "/cache": cache})
def teach(pools: str = "daily,disposal", only: str = "", out: str = "teacher.jsonl", cite: bool = True) -> dict:
    """`only`: ask just these bank ids (comma-separated) instead of each pool's full question set."""
    import yaml
    from vllm import LLM, SamplingParams
    bank = {e["id"]: e for p in sorted(os.listdir("/bank")) if p.endswith(".yaml") for e in yaml.safe_load(open(f"/bank/{p}"))}
    docs = []
    for pool in pools.split(","):
        for line in open(f"/vol/hc/{pool}.jsonl"):
            d = json.loads(line)
            docs.append(d)
    random.Random(3).shuffle(docs)
    jobs = []   # (doc_key, doc_text_for_state, qids)
    for d in docs:
        key = f"{d['pool']}:{d['cnr']}:{d.get('decision_date', '')}"
        qids = [q for q in DOC_QUESTIONS[d["pool"]] if not only or q in only.split(",")] or only.split(",")
        jobs.append((key, head_tail(d["text"]), qids, d))
        cp = citation_passage(d["text"]) if cite else None
        if cp:
            passage, case = cp
            jobs.append((key + ":cite", f"{passage}\n\nCited judgment asked about: {case}", ["RSR.TRT.01"], d))
    print(f"{len(docs)} documents, {len(jobs)} prompts", flush=True)

    t0 = time.time()
    llm = LLM(MODEL, max_model_len=12288, gpu_memory_utilization=0.92, enable_prefix_caching=True)
    cache.commit()
    print(f"model loaded in {time.time() - t0:.0f}s", flush=True)
    sp = SamplingParams(temperature=0.8, top_p=1.0, max_tokens=2048)

    def run(batch):
        msgs, specs = [], []
        for key, doc, qids, _ in batch:
            for pass_ in ("a", "b"):
                body, spec = prompt(doc, qids, bank, random.Random(f"{key}:{pass_}") if pass_ == "b" else None)
                msgs.append([{"role": "system", "content": SYSTEM}, {"role": "user", "content": body}])
                specs.append(spec)
        outs = llm.chat(msgs, sp, use_tqdm=False)
        res = []
        for i, (key, doc, qids, d) in enumerate(batch):
            a, b = parse(outs[2 * i].outputs[0].text, specs[2 * i]), parse(outs[2 * i + 1].outputs[0].text, specs[2 * i + 1])
            res.append({"key": key, "pool": d["pool"], "cnr": d["cnr"], "court": d.get("court_part"), "case_type": d.get("case_type"),
                        "disposal_raw": d.get("disposal_nature", ""), "state": doc, "qids": qids, "a": a, "b": b})
        return res

    smoke = run(jobs[:SMOKE])
    asked = sum(len(r["qids"]) * 2 for r in smoke)
    parsed = sum(len(r["a"]) + len(r["b"]) for r in smoke)
    agree = sum(1 for r in smoke for q in r["qids"] if q in r["a"] and r["a"].get(q) == r["b"].get(q))
    print(f"SMOKE: parsed {parsed}/{asked} answers, agreement {agree}/{sum(len(r['qids']) for r in smoke)}", flush=True)
    if parsed < 0.9 * asked:
        print("SMOKE FAILED: answers do not parse; stopping before the full run.", flush=True)
        return {"smoke_parsed": parsed, "smoke_asked": asked}

    path = f"/vol/hc/{out}"
    n = 0
    with open(path, "w") as h:
        for r in smoke:
            h.write(json.dumps(r, ensure_ascii=False) + "\n")
        for start in range(SMOKE, len(jobs), 512):
            for r in run(jobs[start:start + 512]):
                h.write(json.dumps(r, ensure_ascii=False) + "\n")
                n += 1
            h.flush()
            data.commit()
            print(f"labelled {start + 512}/{len(jobs)} prompts ({time.time() - t0:.0f}s)", flush=True)
    data.commit()
    return {"prompts": len(jobs), "written": n + len(smoke)}


@app.local_entrypoint()
def main(pools: str = "daily,disposal", only: str = "", out: str = "teacher.jsonl", cite: bool = True):
    print(teach.remote(pools, only, out, cite))
