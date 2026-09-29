"""The demo's live run: Nyaya-S1 answers every demo decision on one GPU, each one timed.

  modal run modal/demo_run.py [--model /runs/nyaya-s1-v1]

JevK5's own runtime (CUDA graphs on, as it serves), the model's fitted temperature from jevk5_config.json.
Each decision is timed on its own (torch.cuda.synchronize around it) after a warm-up, so the latencies the demo
shows are measured, not estimated. Results go to data/demo/results.json.
"""
import json
import os
import time

import modal

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)
CAUSAL = ("https://github.com/Dao-AILab/causal-conv1d/releases/download/v1.7.0/"
          "causal_conv1d-1.7.0%2Bcu12torch2.8cxx11abiTRUE-cp313-cp313-linux_x86_64.whl")
image = (
    modal.Image.debian_slim(python_version="3.13")
    .apt_install("git", "build-essential")
    .pip_install("torch==2.8.0", "transformers>=5.17", "accelerate>=1.12", "huggingface-hub>=1.0", "numpy",
                 "jinja2>=3.1", "einops", "safetensors>=0.4", "peft")
    .run_commands("pip install -q 'flash-linear-attention==0.5.2' && pip install -q 'triton>=3.7.1'",
                  f"pip install -q --no-deps '{CAUSAL}'",
                  "git clone -q --depth 1 https://github.com/allebee/jevk5 /jevk5 && pip install -q --no-deps -e /jevk5")
    .add_local_file(os.path.join(ROOT, "data", "demo", "inputs.json"), "/demo/inputs.json")
)
app = modal.App("nyaya-demo-run", image=image)
runs = modal.Volume.from_name("tura-s1-jevk5-runs")


@app.function(gpu="L40S", timeout=3600, volumes={"/runs": runs})
def run(model: str) -> dict:
    import torch
    from jevk5.runtime import JevK5
    t0 = time.perf_counter()
    dm = JevK5(model)
    load_s = time.perf_counter() - t0
    inputs = json.load(open("/demo/inputs.json"))
    decisions = inputs["decisions"]
    for d in decisions[:8]:   # warm-up: first calls record CUDA graphs
        dm.probabilities(d["state"], d["question"])
    results, t_all = [], time.perf_counter()
    for d in decisions:
        torch.cuda.synchronize()
        t = time.perf_counter()
        probs, tokens = dm.probabilities(d["state"], d["question"])
        torch.cuda.synchronize()
        ms = (time.perf_counter() - t) * 1000
        best = max(probs, key=probs.get)
        results.append({**{k: v for k, v in d.items() if k != "state"}, "answer": best, "confidence": round(float(probs[best]), 4),
                        "probs": {k: round(float(v), 4) for k, v in probs.items()}, "ms": round(ms, 2), "tokens": int(tokens)})
    total_s = time.perf_counter() - t_all
    # Batched, as a court would run it: the trial file's questions in padded batches (JevK5's own evaluate path).
    import sys
    sys.path.insert(0, "/jevk5/training")
    from lora import encode_items, evaluate
    cbi_items = [{"state": d["state"], "question": d["question"], "expected": next(iter(d["question"]["criteria"])), "source": d["kind"]}
                 for d in decisions if d["group"] == "cbi"]
    enc = encode_items(dm, cbi_items, 16384)
    torch.cuda.synchronize()
    tb = time.perf_counter()
    evaluate(dm, enc)
    torch.cuda.synchronize()
    batched_s = time.perf_counter() - tb
    gpu = torch.cuda.get_device_name(0)
    print(f"[demo] batched: {len(enc)} trial-file decisions in {batched_s:.1f}s", flush=True)
    print(f"[demo] {len(results)} decisions in {total_s:.1f}s on {gpu} (model load {load_s:.0f}s, temperature {dm.temperature})", flush=True)
    return {"model": model, "gpu": gpu, "temperature": dm.temperature, "load_s": round(load_s, 1), "total_s": round(total_s, 2),
            "run_at_utc": time.strftime("%Y-%m-%d %H:%M UTC", time.gmtime()), "batched_cbi_s": round(batched_s, 2), "batched_cbi_n": len(enc),
            "cbi_orders": inputs["cbi_orders"], "results": results}


@app.local_entrypoint()
def main(model: str = "/runs/nyaya-s1-v1"):
    r = run.remote(model)
    json.dump(r, open(os.path.join(ROOT, "data", "demo", "results.json"), "w"), ensure_ascii=False)
    ms = sorted(x["ms"] for x in r["results"])
    print(f"saved; {len(ms)} decisions, median {ms[len(ms) // 2]:.1f} ms, p95 {ms[int(.95 * len(ms))]:.1f} ms, total {r['total_s']} s")
