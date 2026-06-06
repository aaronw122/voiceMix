"""
train_rvc_modal.py — train an RVC voice model on Modal using Applio's headless CLI.

Pipeline (all on one GPU container): preprocess → extract (f0+content) → train → index,
then the {<name>.pth, <name>.index} pair is copied to a Modal Volume so it survives the
container. Pretrained weights (hubert/rmvpe/pretrained_v2) are baked into the image at
build time via Applio's `prerequisites`, so cold starts don't re-download them.

────────────────────────────────────────────────────────────────────────────
RUNBOOK
  1. one-time auth (you must do this — I can't):
        pip install modal && modal setup
  2. push the Obama dataset into the volume (the two raw wavs):
        modal volume create rvc-vol
        modal volume put rvc-vol \
          data/raw/A_Promised_Land_by_Barack_Obama_Audiobook_Excerpt.wav /datasets/obama/
        modal volume put rvc-vol \
          data/raw/Barack_Obama_describes_his_experience_writing_A_Promised_Land.wav /datasets/obama/
  3. train (builds the image first run — ~10-15 min — then trains):
        modal run train_rvc_modal.py --epochs 50
     train several voices in parallel and wait for results:
        modal run train_rvc_modal.py --model-names obama,jobs,attenborough,rogan,freeman --epochs 50
     submit several voices in the background:
        modal run --detach train_rvc_modal.py --model-names obama,jobs,attenborough,rogan,freeman --epochs 50 --background
  4. grab the artifact pair:
        modal volume get rvc-vol /artifacts/obama/obama.pth ./
        modal volume get rvc-vol /artifacts/obama/added_*.index ./
────────────────────────────────────────────────────────────────────────────
The {.pth, .index} pair is just files → trivially portable to MinIO / a real service later.
"""
import os
import json
import shutil
import subprocess
from pathlib import Path

import modal

# ── tunables ────────────────────────────────────────────────────────────────
DEFAULT_MODEL_NAME = "obama"
SAMPLE_RATE = 48000          # v2 / 48k = max fidelity
TOTAL_EPOCH = 250            # ~sweet spot for ~11 min; overtrain-detector may stop earlier
SAVE_EVERY = 50
BATCH_SIZE = 8               # conservative on H100; raise only after validating throughput
F0_METHOD = "rmvpe"          # best pitch extractor for speech
GPU = os.environ.get("MODAL_GPU", "H100")

APPLIO = "/Applio"

# ── image: Applio + CUDA torch + baked pretrained weights ─────────────────────
image = (
    modal.Image.debian_slim(python_version="3.11")  # Applio reqs (numpy 2.4 / torch 2.3+) need >=3.11
    .apt_install("git", "ffmpeg")
    .run_commands("git clone --depth 1 https://github.com/IAHispano/Applio.git /Applio")
    # Applio pins torch; the cu121 extra-index pulls the CUDA build of those pins.
    .run_commands(
        "cd /Applio && pip install -r requirements.txt "
        "--extra-index-url https://download.pytorch.org/whl/cu128"  # Applio pins torch==2.7.1+cu128
    )
    # bake hubert + rmvpe + pretrained_v2 into the image (no exe/ffmpeg dl — apt has it)
    .run_commands(
        "cd /Applio && python core.py prerequisites "
        "--models True --pretraineds_hifigan True --exe False"
    )
)

app = modal.App("rvc-train")
vol = modal.Volume.from_name("rvc-vol", create_if_missing=True)


def _run(cmd: str) -> None:
    """Run an Applio CLI step from the Applio dir, streaming output, fail loud."""
    print(f"\n$ {cmd}", flush=True)
    subprocess.run(cmd, shell=True, cwd=APPLIO, check=True)


def _ensure_applio_config() -> None:
    """Applio's exporter expects this UI config even in headless CLI runs."""
    config_path = Path(APPLIO) / "assets" / "config.json"
    if config_path.exists():
        return

    config_path.parent.mkdir(parents=True, exist_ok=True)
    config = {
        "theme": {"file": "Applio.py", "class": "Applio"},
        "plugins": [],
        "discord_presence": False,
        "lang": {"override": False, "selected_lang": "en_US"},
        "version": "headless",
        "model_author": "None",
        "precision": "fp32",
    }
    config_path.write_text(json.dumps(config, indent=2), encoding="utf-8")


def _canonical_model_name(model_name: str) -> str:
    allowed = set("abcdefghijklmnopqrstuvwxyzABCDEFGHIJKLMNOPQRSTUVWXYZ0123456789_-")
    if not model_name or any(ch not in allowed for ch in model_name):
        raise ValueError("model_name may only contain letters, digits, underscores, and hyphens")
    return model_name


def _parse_model_names(model_name: str, model_names: str) -> list[str]:
    names = [part.strip() for part in model_names.replace("\n", ",").split(",") if part.strip()]
    if not names:
        names = [model_name]

    seen = set()
    canonical_names = []
    for name in names:
        canonical = _canonical_model_name(name)
        if canonical not in seen:
            seen.add(canonical)
            canonical_names.append(canonical)
    return canonical_names


def _print_retrieval_commands(model_names: list[str]) -> None:
    print("\nretrieve with:")
    for model_name in model_names:
        print(f"  modal volume get rvc-vol /artifacts/{model_name}/{model_name}.pth ./")
        print(f"  modal volume get rvc-vol /artifacts/{model_name}/added_*.index ./")


def _copy_artifacts(logs: Path, vol_artifacts: Path, model_name: str) -> list[tuple[str, int]]:
    """Copy all useful outputs and normalize the final inference model name."""
    vol_artifacts.mkdir(parents=True, exist_ok=True)
    found = []

    for pat in ("*.pth", "*.index"):
        for f in sorted(logs.glob(pat)):
            dst = vol_artifacts / f.name
            shutil.copy2(f, dst)
            found.append((f.name, f.stat().st_size))

    inference_models = [
        f for f in logs.glob("*.pth")
        if not f.name.startswith(("G_", "D_"))
    ]
    final_models = [f for f in inference_models if not f.stem.endswith("_best_epoch")]
    selected = max(final_models or inference_models, key=lambda f: f.stat().st_mtime, default=None)
    if selected is None:
        raise SystemExit("no extracted inference .pth produced — check the train log above")

    canonical_dst = vol_artifacts / f"{model_name}.pth"
    shutil.copy2(selected, canonical_dst)
    if selected.name != canonical_dst.name:
        found.append((canonical_dst.name, canonical_dst.stat().st_size))

    return found


@app.function(image=image, gpu=GPU, volumes={"/vol": vol}, timeout=3600)
def train(model_name: str = DEFAULT_MODEL_NAME, epochs: int = TOTAL_EPOCH, save_every: int = SAVE_EVERY) -> dict:
    model_name = _canonical_model_name(model_name)
    if epochs < 1:
        raise ValueError("epochs must be at least 1")
    if save_every < 1:
        raise ValueError("save_every must be at least 1")

    n_cpu = os.cpu_count() or 8
    logs = Path(APPLIO) / "logs" / model_name
    vol_dataset = Path("/vol") / "datasets" / model_name
    vol_artifacts = Path("/vol") / "artifacts" / model_name
    _ensure_applio_config()

    if not vol_dataset.exists() or not any(vol_dataset.glob("*.wav")):
        raise SystemExit(
            f"no wavs in {vol_dataset} — upload first:\n"
            f"  modal volume put rvc-vol <{model_name}.wav> /datasets/{model_name}/"
        )

    # 1) preprocess: slice (Automatic = silence-aware), resample 48k, normalize
    _run(
        f"python core.py preprocess --model_name {model_name} "
        f"--dataset_path {vol_dataset} --sample_rate {SAMPLE_RATE} "
        f"--cpu_cores {n_cpu} --cut_preprocess Automatic"
    )
    # 2) extract: f0 (rmvpe) + content (contentvec) features, on GPU
    _run(
        f"python core.py extract --model_name {model_name} "
        f"--sample_rate {SAMPLE_RATE} --f0_method {F0_METHOD} --gpu 0 --cpu_cores {n_cpu} "
        f"--include_mutes 2"
    )
    # 3) train: fine-tune from baked pretrained_v2; Applio exports a final inference model
    # when it reaches total_epoch.
    _run(
        f"python core.py train --model_name {model_name} --sample_rate {SAMPLE_RATE} "
        f"--save_every_epoch {min(save_every, epochs)} --total_epoch {epochs} "
        f"--batch_size {BATCH_SIZE} --gpu 0 --overtraining_detector True"
    )

    # Persist the finished inference model before indexing, so a later index failure
    # does not lose the expensive part of the run.
    found = _copy_artifacts(logs, vol_artifacts, model_name)
    vol.commit()

    # 4) build the FAISS retrieval index
    _run(f"python core.py index --model_name {model_name}")

    # collect index + final artifacts → volume
    found = _copy_artifacts(logs, vol_artifacts, model_name)
    vol.commit()  # persist before the container dies

    print("\n=== artifacts written to volume ===")
    for name, size in found:
        print(f"  {name:40s} {size/1e6:6.1f} MB")
    return {"model": model_name, "epochs": epochs, "artifacts": found}


@app.local_entrypoint()
def main(
    model_name: str = DEFAULT_MODEL_NAME,
    model_names: str = "",
    epochs: int = TOTAL_EPOCH,
    save_every: int = SAVE_EVERY,
    background: bool = False,
) -> None:
    names = _parse_model_names(model_name, model_names)

    if len(names) == 1 and not background:
        result = train.remote(names[0], epochs, save_every)
        print("\nDONE:", result)
        _print_retrieval_commands(names)
        return

    print(f"\nLaunching {len(names)} training runs on {GPU}: {', '.join(names)}")
    if background:
        train.spawn_map(names, kwargs={"epochs": epochs, "save_every": save_every})
        print("Submitted background jobs. Use `modal run --detach` so they keep running if you disconnect.")
        _print_retrieval_commands(names)
        return

    had_error = False
    for name, result in zip(
        names,
        train.map(names, kwargs={"epochs": epochs, "save_every": save_every}, return_exceptions=True),
    ):
        if isinstance(result, BaseException):
            had_error = True
            print(f"\nFAILED {name}: {result!r}")
        else:
            print(f"\nDONE {name}: {result}")

    _print_retrieval_commands(names)
    if had_error:
        raise SystemExit("one or more training runs failed")


# ── inference ────────────────────────────────────────────────────────────────
# Reuses the SAME image (Applio + baked rmvpe/hubert) and the trained {pth,index}
# already on the volume. Light job → cheap GPU. Convert a source clip → target timbre.
#   1. upload a (non-target) source clip:
#        modal volume put rvc-vol <clip.wav> /sources/<name>.wav
#   2. run:
#        modal run train_rvc_modal.py::infer_main --source-name <name>.wav
#   3. download + play:
#        modal volume get rvc-vol /outputs/<name>__as_<model>.wav ./
INFER_GPU = os.environ.get("MODAL_INFER_GPU", "L4")  # inference is light; H100 would be waste


@app.function(image=image, gpu=INFER_GPU, volumes={"/vol": vol}, timeout=600)
def infer(model_name: str = DEFAULT_MODEL_NAME, source_name: str = "source.wav",
          index_rate: float = 0.5, pitch: int = 0, f0_method: str = "rmvpe") -> dict:
    """Voice-convert /sources/<source_name> into <model_name>'s timbre via RVC."""
    model_name = _canonical_model_name(model_name)
    _ensure_applio_config()

    art = Path("/vol") / "artifacts" / model_name
    pth = art / f"{model_name}.pth"
    indexes = sorted(art.glob("*.index"), key=lambda f: f.stat().st_size, reverse=True)
    src = Path("/vol") / "sources" / source_name
    if not pth.exists():
        raise SystemExit(f"no model at {pth} — train first")
    if not indexes:
        raise SystemExit(f"no .index in {art} — train's index step must run first")
    if not src.exists():
        raise SystemExit(f"no source at {src} — upload:\n"
                         f"  modal volume put rvc-vol <clip.wav> /sources/{source_name}")
    index = indexes[0]  # the added_* retrieval index is the largest

    out_dir = Path("/vol") / "outputs"
    out_dir.mkdir(parents=True, exist_ok=True)
    out = out_dir / f"{Path(source_name).stem}__as_{model_name}.wav"

    _run(
        f"python core.py infer --input_path {src} --output_path {out} "
        f"--pth_path {pth} --index_path {index} "
        f"--f0_method {f0_method} --index_rate {index_rate} --pitch {pitch} --export_format WAV"
    )
    vol.commit()
    print(f"\n=== wrote {out.name} ({out.stat().st_size/1e6:.1f} MB) "
          f"| index_rate={index_rate} pitch={pitch} ===")
    return {"output": out.name, "pth": pth.name, "index": index.name}


@app.local_entrypoint()
def infer_main(model_name: str = DEFAULT_MODEL_NAME, source_name: str = "source.wav",
               index_rate: float = 0.5, pitch: int = 0, f0_method: str = "rmvpe") -> None:
    r = infer.remote(model_name, source_name, index_rate, pitch, f0_method)
    print("\nDONE:", r)
    print(f"download + listen:\n  modal volume get rvc-vol /outputs/{r['output']} ./")
