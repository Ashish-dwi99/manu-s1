"""Print Nyaya-S1 v0's answers on the real-case test set, next to the expected label, to see why it fails there.

  modal run modal/diagnose.py
"""
import json
import os

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
    .add_local_file(os.path.join(ROOT, "data", "final", "test_cbi.jsonl"), "/data/test_cbi.jsonl")
)
app = modal.App("nyaya-diagnose", image=image)
runs = modal.Volume.from_name("tura-s1-jevk5-runs")


@app.function(gpu="L40S", timeout=1800, volumes={"/runs": runs})
def diagnose() -> list[dict]:
    import sys
    sys.path.insert(0, "/jevk5/training")
    from lora import encode_items, evaluate
    from jevk5.runtime import JevK5
    dm = JevK5("/runs/nyaya-s1-v0", graphs=False, temperature=1.0)
    raw = [json.loads(x) for x in open("/data/test_cbi.jsonl")]
    data = encode_items(dm, raw, 16384)
    probs = evaluate(dm, data)["probs"]
    out = []
    for r, p in zip(raw, probs):
        keys = list(r["question"]["criteria"])
        top = int(p.argmax())
        out.append({"id": r["id"], "bank_id": r["bank_id"], "expected": r["label_name"],
                    "predicted_key": keys[top], "predicted_text": r["question"]["criteria"][keys[top]][:70], "p": round(float(p[top]), 3),
                    "note": r["question"]["instructions"][-70:]})
    return out


@app.local_entrypoint()
def main():
    rows = diagnose.remote()
    json.dump(rows, open(os.path.join(ROOT, "data", "final", "cbi_predictions.json"), "w"), indent=1)
    from collections import Counter
    for bid in sorted({r["bank_id"] for r in rows}):
        c = Counter(r["predicted_text"] for r in rows if r["bank_id"] == bid)
        print(bid, dict(c.most_common(5)))
