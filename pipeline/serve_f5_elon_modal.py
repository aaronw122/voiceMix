"""
serve_f5_elon_modal.py — fine-tuned F5-TTS inference endpoint for voiceMix (Elon voice).

A SEPARATE Modal app from the Trump/Dwarkesh F5 servers — its own container + URL, so
deploying/redeploying Elon never touches the live Trump or Dwarkesh endpoints. SAME HTTP contract
as serve_f5_dwarkesh_modal.py, so the backend's GptSoVitsModalEngine works unchanged — the backend
just points a per-voice base_url (ELON_TTS_MODAL_ENDPOINT_URL) at this app's *.modal.run URL.

Chosen config (elon run, June 2026 — picked by ear over a checkpoint/speed sweep):
  elonv2/model_16000 NON-EMA, ref = elon_jre2404_0653 (clean, energetic),
  nfe_step=32, cfg_strength=2.0, speed default 0.8 (per-request overridable).
  (v2 = ~133 min / 4 sources; 16k won the ear-A/B over v1@12k and v2@12k/14k/18k/20k.)

Deploy (own app; profile = aaronmodal, where the elon model + tts-vol live):
    MODAL_PROFILE=aaronmodal modal deploy pipeline/serve_f5_elon_modal.py
Then set the backend env ELON_TTS_MODAL_ENDPOINT_URL to this app's *.modal.run URL.
"""
import difflib
import io
import os
import re
import subprocess
import tempfile

import modal

F5_DIR = "/opt/F5-TTS"
VOICE = "elon"

# source artifacts (read-only) we bootstrap the slim serving assets from, once:
CKPT_SRC = "/vol/ft_f5/ckpts/elonv2/model_16000.pt"
VOCAB_SRC = "/vol/ft_f5/data/elonv2_pinyin/vocab.txt"
REF_SRC = "/vol/datasets/elon/clips_v3/elon_jre2404_0653.wav"
REF_TEXT = ("in a benign scenario universal high income, not just universal basic income, "
            "universal high income, meaning anyone can have any products or services that "
            "they want.")

# slim serving assets (built once, then loaded fast on every cold start):
SERVE_DIR = "/vol/ft_f5/serve"
NOEMA_CKPT = f"{SERVE_DIR}/elonv2_16k_noema.pt"   # raw (non-EMA) weights, no optimizer state (renamed -> rebuilds from v2 ckpt)
SERVE_VOCAB = f"{SERVE_DIR}/elonv2_vocab.txt"     # v2 vocab is size 68 (v1 was 66) -> must rebuild
SERVE_REF = f"{SERVE_DIR}/elon_ref.wav"           # ref unchanged (still 0653)

WHISPER_CACHE = "/vol/models/whisper"
# ASR runs on the USER's input recording (impersonate flow), NOT on Elon content — keep it
# NEUTRAL (no glossary/hotwords) so arbitrary user speech transcribes faithfully. Biasing the
# decoder toward a domain glossary risks hallucinating those terms into unrelated user speech,
# and tested ineffective at fixing the one word we care about anyway.
GLOSSARY = ""

# Surgical proper-noun repair, applied AFTER transcription. distil-large-v3 reliably mangles the
# speaker's own name and decoder biasing didn't fix it, so instead we correct only tokens that are
# near-homophones of a known name — leaving all other user speech untouched. Extend NAME_FIXES per
# voice. (Edge case it won't catch: a name fused with an adjacent word, which drifts too far to
# match.)
NAME_FIXES = ("Elon",)
NAME_MATCH_RATIO = 0.72

def _canon_names(text: str) -> str:
    """Replace tokens that are near-homophones of a known name with its canonical spelling.
    Operates per whitespace token, preserving surrounding punctuation and any '.com'-style
    suffix (so 'elahn.com' -> 'Elon.com'). No-op when NAME_FIXES is empty."""
    if not NAME_FIXES:
        return text

    def fix(tok: str) -> str:
        lead = re.match(r"^\W*", tok).group()
        trail = re.search(r"\W*$", tok).group()
        core = tok[len(lead): len(tok) - len(trail)] if trail else tok[len(lead):]
        if not core:
            return tok
        head = core.split(".", 1)[0]            # match on the word before any '.com'
        for name in NAME_FIXES:
            if difflib.SequenceMatcher(None, head.lower(), name.lower()).ratio() >= NAME_MATCH_RATIO:
                return lead + name + core[len(head):] + trail
        return tok

    return " ".join(fix(t) for t in text.split())


# default render knobs (chosen by ear; all overridable per request)
NFE_STEP, CFG_STRENGTH, SPEED = 32, 2.0, 0.8
# hard cap on synthesized text for the public endpoint (one sentence/clip is the use case)
MAX_TEXT_CHARS = 600

image = (
    modal.Image.debian_slim(python_version="3.10")
    .apt_install("git", "ffmpeg", "build-essential")
    .pip_install(
        "torch==2.4.1", "torchaudio==2.4.1",
        extra_index_url="https://download.pytorch.org/whl/cu121",
    )
    .run_commands(
        f"git clone --depth 1 https://github.com/SWivid/F5-TTS {F5_DIR}",
        "pip install uv",
        f"cd {F5_DIR} && uv pip install --system -e .",
    )
    .pip_install("faster-whisper==1.0.3", "soundfile")
    # protobuf LAST so the big ML installs don't pull a version that breaks the in-container
    # Modal client (crash at import: EnvironmentRole.ValueType).
    .pip_install("protobuf==4.25.5")
    .env({"HF_HOME": "/vol/models/f5/hf", "PYTHONPATH": F5_DIR})
)

# App name (= public URL) comes from the env, never hardcoded: keeps the unauthenticated
# endpoint off the public repo. Deploy with `ELON_APP_NAME=<secret> modal deploy ...`.
app = modal.App(os.environ.get("ELON_APP_NAME", "voicemix-tts-elon"))
vol = modal.Volume.from_name("tts-vol", create_if_missing=False)


def _ensure_serve_assets():
    """One-time: repackage the non-EMA step-16000 weights into a slim inference checkpoint and
    stage the reference clip + vocab under SERVE_DIR. Idempotent — skips if already built."""
    import shutil

    import torch
    os.makedirs(SERVE_DIR, exist_ok=True)
    if not os.path.exists(NOEMA_CKPT):
        ck = torch.load(CKPT_SRC, map_location="cpu", weights_only=False)
        raw = ck["model_state_dict"]
        # store the raw (fully fine-tuned) weights in BOTH slots so the loader picks them up
        # whether it reads model_state_dict or ema_model_state_dict (use_ema True or False).
        ema = {f"ema_model.{k}": v for k, v in raw.items()}
        ema["initted"] = torch.tensor(True)
        ema["step"] = torch.tensor(int(ck.get("update", ck.get("step", 0))))
        torch.save({"model_state_dict": raw, "ema_model_state_dict": ema}, NOEMA_CKPT)
        print(f"wrote slim non-EMA ckpt -> {NOEMA_CKPT}", flush=True)
    if not os.path.exists(SERVE_VOCAB):
        shutil.copyfile(VOCAB_SRC, SERVE_VOCAB)
    if not os.path.exists(SERVE_REF):
        shutil.copyfile(REF_SRC, SERVE_REF)
    vol.commit()


# No HF secret: F5TTS_v1_Base + Vocos vocoder + distil-large-v3 are all PUBLIC on HF, so weight
# downloads need no token.
@app.cls(image=image, gpu="L4", volumes={"/vol": vol}, timeout=600, scaledown_window=300)
@modal.concurrent(max_inputs=1)
class TTSModel:
    @modal.enter()
    def load(self):
        _ensure_serve_assets()
        from f5_tts.api import F5TTS
        from faster_whisper import WhisperModel

        # F5TTS loads the base DiT arch then our fine-tuned weights; vocab must match the ckpt.
        self.f5 = F5TTS(model="F5TTS_v1_Base", ckpt_file=NOEMA_CKPT, vocab_file=SERVE_VOCAB)
        self.ref_wav, self.ref_text = SERVE_REF, REF_TEXT

        # CPU whisper (int8) — short recordings, avoids GPU-cuDNN dep hell; GPU stays for F5.
        self.whisper = WhisperModel("distil-large-v3", device="cpu", compute_type="int8",
                                    download_root=WHISPER_CACHE)
        print(f"loaded F5-TTS (12k non-EMA, ref=0653) + distil-large-v3 for {VOICE!r}", flush=True)

    def _transcribe(self, wav_bytes: bytes) -> str:
        with tempfile.NamedTemporaryFile(suffix=".wav") as tmp:
            tmp.write(wav_bytes)
            tmp.flush()
            # Neutral ASR (no glossary/hotwords) so arbitrary user speech transcribes faithfully;
            # the speaker's-name fix is a targeted post-pass (see _canon_names) that leaves all
            # other words untouched.
            segments, _ = self.whisper.transcribe(
                tmp.name, language="en", beam_size=5,
                condition_on_previous_text=False,
                initial_prompt=GLOSSARY or None,
            )
            return _canon_names("".join(s.text for s in segments).strip())

    def _synthesize(self, text: str, speed: float = SPEED, nfe_step: int = NFE_STEP,
                    cfg_strength: float = CFG_STRENGTH, remove_silence: bool = False) -> bytes:
        import soundfile as sf

        wav, sr, _ = self.f5.infer(
            ref_file=self.ref_wav, ref_text=self.ref_text, gen_text=text,
            nfe_step=nfe_step, cfg_strength=cfg_strength, speed=speed,
            remove_silence=remove_silence,
        )
        buf = io.BytesIO()
        sf.write(buf, wav, sr, format="WAV", subtype="PCM_16")
        return subprocess.run(
            ["ffmpeg", "-hide_banner", "-loglevel", "error", "-i", "pipe:0",
             "-f", "mp3", "-b:a", "192k", "pipe:1"],
            input=buf.getvalue(), stdout=subprocess.PIPE, check=True,
        ).stdout

    @modal.asgi_app()
    def web(self):
        from fastapi import FastAPI, HTTPException, Request, Response
        from starlette.concurrency import run_in_threadpool

        api = FastAPI()

        @api.get("/health")
        async def health():
            return {"ok": True, "voice": VOICE, "engine": "f5", "step": 16000}

        @api.post("/synthesize")
        async def synthesize(request: Request, voice: str = VOICE, text: str | None = None,
                             speed: float = SPEED, nfe_step: int = NFE_STEP,
                             cfg_strength: float = CFG_STRENGTH, remove_silence: bool = False):
            if voice != VOICE:
                raise HTTPException(404, f"this endpoint serves {VOICE!r}, not {voice!r}")
            # Bound the public, unauthenticated surface: cap text length and clamp the
            # inference knobs to sane ranges so a stray/abusive caller can't tie up the GPU
            # worker with a pathological prompt or absurd nfe/cfg/speed.
            speed = min(max(speed, 0.3), 2.0)
            nfe_step = min(max(nfe_step, 8), 64)
            cfg_strength = min(max(cfg_strength, 0.0), 5.0)
            text = (text or "").strip() or None
            if text is None:
                wav = await request.body()
                if not wav:
                    raise HTTPException(400, "send either ?text= or a WAV body")
                text = await run_in_threadpool(self._transcribe, wav)
                if not text:
                    raise HTTPException(422, "couldn't hear any words in that recording")
            if len(text) > MAX_TEXT_CHARS:
                raise HTTPException(413, f"text too long (max {MAX_TEXT_CHARS} chars)")
            mp3 = await run_in_threadpool(
                self._synthesize, text, speed, nfe_step, cfg_strength, remove_silence)
            safe = text[:500].encode("latin-1", "replace").decode("latin-1")
            return Response(content=mp3, media_type="audio/mpeg",
                            headers={"X-Transcript": safe})

        return api
