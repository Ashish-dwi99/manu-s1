"""Train Nyaya-S1 v0 on one Modal H100 and evaluate it, before and after, on every test set.

  modal run --detach modal/train.py

1. Base selection on the Nyaya dev set (never a test set): Plumb-4B as released vs our Tura-S1 fine-tune of it.
2. JevK5's own trainer (training/lora.py): LoRA rank 16, one epoch, lr 2e-5, 4096-token questions; the adapter is
   saved every SAVE_EVERY steps and pushed to Kaggle, so running out of credit loses at most one interval.
3. One temperature fitted on dev; written to jevk5_config.json next to the merged weights.
4. Base and trained model on test_rules, test_hc (held-out CNRs) and test_cbi (the owner's real case, never trained on).
"""
import json
import os
import subprocess
import threading
import time

import modal

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)
CAUSAL = ("https://github.com/Dao-AILab/causal-conv1d/releases/download/v1.7.0/"
          "causal_conv1d-1.7.0%2Bcu12torch2.8cxx11abiTRUE-cp313-cp313-linux_x86_64.whl")
# v0 picks its base on dev between these two; v1 (NYAYA_VERSION=v1) continues from the merged v0 model.
VERSION = os.environ.get("NYAYA_VERSION", "v0")
BASES = ({"plumb-4b": "crh225/plumb-4b", "tura-s1-4b": "/runs/plumb-pick"} if VERSION == "v0"
         else {"nyaya-s1-v0": "/runs/nyaya-s1-v0"})
SAVE_EVERY, OUT = 300, f"/runs/nyaya-s1-{VERSION}"
DATA_DIR = "final" if VERSION == "v0" else f"final_{VERSION}"
TESTS = ("test_rules", "test_hc", "test_cbi")

image = (
    modal.Image.debian_slim(python_version="3.13")
    .apt_install("git", "build-essential")
    .pip_install("torch==2.8.0", "transformers>=5.17", "accelerate>=1.12", "huggingface-hub>=1.0", "numpy",
                 "jinja2>=3.1", "einops", "safetensors>=0.4", "peft", "kaggle")
    .run_commands("pip install -q 'flash-linear-attention==0.5.2' && pip install -q 'triton>=3.7.1'",
                  f"pip install -q --no-deps '{CAUSAL}'",
                  "git clone -q --depth 1 https://github.com/allebee/jevk5 /jevk5 && pip install -q --no-deps -e /jevk5")
    .env({"NYAYA_VERSION": VERSION})
    .add_local_dir(os.path.join(ROOT, "data", DATA_DIR), "/data")
)
app = modal.App(f"nyaya-train-{VERSION}", image=image)
runs = modal.Volume.from_name("tura-s1-jevk5-runs")
kaggle = modal.Secret.from_dict({"KAGGLE_USERNAME": os.environ.get("KAGGLE_USERNAME", ""), "KAGGLE_KEY": os.environ.get("KAGGLE_KEY", "")})


def patch_trainer() -> None:
    p = "/jevk5/training/lora.py"
    s = open(p).read()
    step = "        scheduler.step()\n"
    assert s.count(step) == 1 and "merged = model.merge_and_unload()" in s
    s = s.replace(step, step + f"        if (step + 1) % {SAVE_EVERY} == 0:\n"
                  "            model.save_pretrained(args.out / f\"adapter-step{step + 1}\")\n"
                  "            print(f\"saved adapter at step {step + 1}\", flush=True)\n")
    s = s.replace("    merged = model.merge_and_unload()",
                  "    model.save_pretrained(args.out / \"adapter-final\")\n    print(\"saved adapter-final\", flush=True)\n"
                  "    merged = model.merge_and_unload()")
    open(p, "w").write(s)


def push(path: str, slug: str, msg: str) -> None:
    import shutil
    if not os.environ.get("KAGGLE_KEY"):
        return
    stage = f"/tmp/push-{slug}"
    shutil.rmtree(stage, ignore_errors=True)
    shutil.copytree(path, f"{stage}/{os.path.basename(path)}")
    json.dump({"title": slug, "id": f"{os.environ['KAGGLE_USERNAME']}/{slug}", "licenses": [{"name": "apache-2.0"}]},
              open(f"{stage}/dataset-metadata.json", "w"))
    if subprocess.run(f"cd {stage} && kaggle datasets create -p . -r zip -q", shell=True).returncode != 0:
        subprocess.run(f"cd {stage} && kaggle datasets version -p . -r zip -q -m '{msg}'", shell=True)
    print(f"[nyaya] pushed {path} to kaggle {slug}", flush=True)


def scores(model: str, sets: tuple[str, ...]) -> dict:
    """JevK5's own evaluate() at T=1, plus per-bank-entry accuracy and the probabilities for temperature fitting."""
    import sys
    import numpy as np
    import torch
    sys.path.insert(0, "/jevk5/training")
    from lora import encode_items, evaluate
    from jevk5.runtime import JevK5
    dm = JevK5(model, graphs=False, temperature=1.0)
    res = {}
    for s in sets:
        raw = [json.loads(x) for x in open(f"/data/{s}.jsonl")]
        for r in raw:   # evaluate() reports by `source`; report by bank entry instead
            r["source"] = r.get("bank_id", r["source"])
        data = encode_items(dm, raw, 16384)
        out = evaluate(dm, data)
        res[s] = {"report": out["report"], "targets": [r["target"].tolist() for r in data], "probs": [p.tolist() for p in out["probs"]]}
        print(f"[eval] {model} {s} {out['report']['ALL']}", flush=True)
    del dm
    torch.cuda.empty_cache()
    return res


def fit_temperature(targets, probs) -> float:
    import numpy as np
    logp = [np.log(np.clip(np.array(p), 1e-12, 1)) for p in probs]
    gold = [int(np.argmax(t)) for t in targets]

    def nll(T):
        tot = 0.0
        for z, g in zip(logp, gold):
            z = z / T
            z = z - z.max()
            tot -= z[g] - np.log(np.exp(z).sum())
        return tot / len(gold)
    return min([round(0.5 + 0.02 * i, 2) for i in range(176)], key=nll)


@app.function(gpu="H100", timeout=10 * 3600, volumes={"/runs": runs}, secrets=[kaggle])
def train() -> dict:
    patch_trainer()
    result = {"bases": {}, "version": VERSION}
    for name, path in BASES.items():
        if len(BASES) == 1:
            result["bases"][name] = {"acc": 0.0, "note": "single base; no selection"}
            continue
        result["bases"][name] = scores(path, ("dev",))["dev"]["report"]["ALL"]
    base_name = max(result["bases"], key=lambda n: result["bases"][n]["acc"])
    base = BASES[base_name]
    result["base"] = base_name
    print(f"[nyaya] base chosen on dev: {base_name} {result['bases']}", flush=True)
    result["base_tests"] = {k: v["report"] for k, v in scores(base, TESTS).items()}

    os.makedirs(OUT, exist_ok=True)
    stop = threading.Event()

    def keep_committing():
        pushed = set()
        while not stop.wait(240):
            runs.commit()
            for d in sorted(os.listdir(OUT)):
                if d.startswith("adapter-step") and d not in pushed:
                    pushed.add(d)
                    push(f"{OUT}/{d}", f"nyaya-s1-{VERSION}-ckpt", d)
    threading.Thread(target=keep_committing, daemon=True).start()
    t0 = time.time()
    rc = subprocess.run(f"python lora.py /data {OUT} --base {base} --epochs 1 --lr 2e-5 --warmup 20 --rank 16 --max-len 4096 "
                        f"--token-budget 16384 2>&1 | tee {OUT}/train.log", shell=True, cwd="/jevk5/training").returncode
    stop.set()
    runs.commit()
    result["train_rc"], result["train_minutes"] = rc, round((time.time() - t0) / 60, 1)
    if os.path.isdir(f"{OUT}/adapter-final"):
        push(f"{OUT}/adapter-final", f"nyaya-s1-{VERSION}", "adapter after one epoch")

    after = scores(OUT, ("dev",) + TESTS)
    T = fit_temperature(after["dev"]["targets"], after["dev"]["probs"])
    cfg_path = f"{OUT}/jevk5_config.json"
    try:
        from huggingface_hub import hf_hub_download
        cfg = json.load(open(hf_hub_download(BASES["plumb-4b"], "jevk5_config.json")))
    except Exception:  # noqa: BLE001
        cfg = {}
    cfg.update({"temperature": T, "note": f"Nyaya-S1 {VERSION}: {base_name} + Indian court procedure LoRA; T fitted on the Nyaya dev set"})
    json.dump(cfg, open(cfg_path, "w"), indent=1)
    runs.commit()
    result["temperature"] = T
    result["after_tests"] = {k: v["report"] for k, v in after.items()}
    json.dump(result, open(f"{OUT}/results.json", "w"), indent=1)
    runs.commit()
    print("=====RESULTS=====\n" + json.dumps({k: v for k, v in result.items() if k not in ("base_tests", "after_tests")}, indent=1), flush=True)
    for split in TESTS:
        print(f"[result] {split}: base {result['base_tests'][split]['ALL']} -> nyaya {result['after_tests'][split]['ALL']}", flush=True)
    return result


@app.local_entrypoint()
def main():
    r = train.remote()
    out = os.path.join(ROOT, "data", DATA_DIR, "results.json")
    json.dump(r, open(out, "w"), indent=1)
    print("saved", out)
