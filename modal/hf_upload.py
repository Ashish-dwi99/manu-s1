"""Upload Manu-S1 (the merged v1 model on the Modal volume) with its card and notices to Hugging Face.

  HF_TOKEN=... modal run modal/hf_upload.py --repo sankhya-ai-labs/manu-s1-4b [--public]

The weights go from the Modal volume straight to Hugging Face; they never pass through the local machine. The
token travels only as a Modal secret built from the local process environment. Private unless --public.
"""
import os

import modal

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)

image = (modal.Image.debian_slim(python_version="3.13").pip_install("huggingface_hub>=1.0", "hf_xet")
         .add_local_dir(os.path.join(ROOT, "hf"), "/card"))
app = modal.App("manu-s1-hf-upload", image=image)
runs = modal.Volume.from_name("tura-s1-jevk5-runs")
secret = modal.Secret.from_dict({"HF_TOKEN": os.environ.get("HF_TOKEN", "")})


@app.function(cpu=8, memory=16384, timeout=2 * 3600, volumes={"/runs": runs}, secrets=[secret])
def upload(repo: str, public: bool) -> str:
    import shutil
    import tempfile
    from huggingface_hub import HfApi
    src = "/runs/nyaya-s1-v1"
    stage = tempfile.mkdtemp()
    for f in os.listdir(src):   # the merged model and its config; not the adapters or checkpoints
        p = os.path.join(src, f)
        if os.path.isfile(p) and not f.startswith(("train", "results")):
            shutil.copy(p, stage)
    for f in os.listdir("/card"):
        shutil.copy(f"/card/{f}", stage)
    print("files:", sorted(os.listdir(stage)), flush=True)
    api = HfApi(token=os.environ["HF_TOKEN"])
    api.create_repo(repo, repo_type="model", exist_ok=True, private=not public)
    api.upload_folder(repo_id=repo, folder_path=stage, commit_message="Manu-S1: Indian court procedure decisions (v1)")
    sha = api.model_info(repo).sha
    print(f"uploaded {repo} at {sha} ({'public' if public else 'private'})", flush=True)
    return sha


@app.local_entrypoint()
def main(repo: str, public: bool = False):
    print(upload.remote(repo, public))
