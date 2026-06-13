"""
serve_gptsovits_modal.py — fine-tuned GPT-SoVITS v2ProPlus inference endpoint for voiceMix.

A modal.Cls whose @modal.enter() loads, ONCE per warm container:
  - faster-whisper distil-large-v3 (request-time ASR for audio input)
  - the GPT-SoVITS v2ProPlus pipeline bound to our fine-tuned weights on tts-vol
    (/artifacts/<voice>/{gpt.ckpt,sovits.pth}) + the per-voice reference clip
This avoids serve_rvc_modal.py's mistake of reloading the model every request (~15s).

Contract (matches backend/app/engines.py::GptSoVitsModalEngine):
    POST /synthesize?voice=<id>
      - body = raw WAV bytes (Content-Type: audio/wav)  -> Whisper transcribes, then TTS
      - OR query/form `text=...`                          -> TTS directly (skips Whisper)
    -> 200 audio/mpeg (MP3), transcription echoed in the X-Transcript header

Deploy (first run pulls the big GPT-SoVITS image):
    MODAL_PROFILE=aaron-j-wms modal deploy serve_gptsovits_modal.py
Then set TTS_MODAL_ENDPOINT_URL on the box to the printed *.modal.run base URL.
"""
import io
import os
import re
import subprocess
import sys
import tempfile

import modal

REPO = "/workspace/GPT-SoVITS"
VOICE = "trump"  # single-voice service for now; per-voice migration keeps RVC for the rest

# seed Whisper with names/terms it tends to mangle (mirrors prep_tts_dataset.py)
GLOSSARY = (
    "Donald Trump, the United States of America, the American people, our southern "
    "border, the coronavirus, COVID-19, China, Mexico, the White House, God bless America."
)

image = (
    modal.Image.from_registry("xxxxrt666/gpt-sovits:latest-cu128")
    # torchaudio -> torchcodec needs ffmpeg's shared libs (libavutil.so.*) to load the
    # reference clip; also our wav->mp3 encode shells out to the ffmpeg binary.
    .apt_install("ffmpeg")
    .env({
        "PATH": "/root/conda/bin:/usr/local/sbin:/usr/local/bin:/usr/sbin:/usr/bin:/sbin:/bin",
        # both dirs: repo root resolves `tools.*`, inner GPT_SoVITS/ resolves `text.*`
        "PYTHONPATH": f"{REPO}:{REPO}/GPT_SoVITS",
    })
    # this image ships the weights at /workspace/models but leaves the repo's
    # pretrained_models/ an empty dir — recreate the symlink install_wrapper.sh intended.
    .run_commands(
        f"rmdir {REPO}/GPT_SoVITS/pretrained_models 2>/dev/null || true",
        f"ln -s /workspace/models/pretrained_models {REPO}/GPT_SoVITS/pretrained_models",
        f"ln -sfn /workspace/models/G2PWModel {REPO}/GPT_SoVITS/text/G2PWModel || true",
    )
)

app = modal.App("voicemix-tts")
vol = modal.Volume.from_name("tts-vol", create_if_missing=True)

WHISPER_CACHE = "/vol/models/whisper"

# The AR (S1) model drifts/drops words when it has to generate one long sequence in a
# single pass (a 35-word run-on became a ~14s generation that swapped/skipped words).
# We pre-segment at natural pause points instead of leaning on GPT-SoVITS' built-in cut
# methods: cut1 keeps a run-on as one over-long chunk (drift), cut2 chops at arbitrary
# ~50-char points mid-clause (choppy). Splitting at sentence→comma boundaries, packed up
# to MAX_CHARS, keeps each chunk short enough to stay coherent while only ever breaking
# where a speaker would pause anyway — so it sounds continuous, not choppy.
MAX_CHARS = 120


def _segment(text: str, max_chars: int = MAX_CHARS) -> list[str]:
    text = text.strip()
    if len(text) <= max_chars:
        return [text]
    sents = [s.strip() for s in re.findall(r"[^.!?…]+[.!?…]?", text) if s.strip()]
    chunks: list[str] = []
    cur = ""
    for s in sents:
        # an over-long single sentence is sub-split at clause punctuation
        pieces = ([p.strip() for p in re.findall(r"[^,;:]+[,;:]?", s) if p.strip()]
                  if len(s) > max_chars else [s])
        for p in pieces:
            if cur and len(cur) + 1 + len(p) > max_chars:
                chunks.append(cur)
                cur = p
            else:
                cur = f"{cur} {p}".strip() if cur else p
    if cur:
        chunks.append(cur)
    # last resort: a clause still over the cap gets hard-wrapped at word boundaries
    out: list[str] = []
    for c in chunks:
        if len(c) <= max_chars:
            out.append(c)
            continue
        line = ""
        for w in c.split():
            if line and len(line) + 1 + len(w) > max_chars:
                out.append(line)
                line = w
            else:
                line = f"{line} {w}".strip() if line else w
        if line:
            out.append(line)
    return out


@app.cls(image=image, gpu="L4", volumes={"/vol": vol}, timeout=600, scaledown_window=300)
@modal.concurrent(max_inputs=1)  # GPU does one synth at a time; Modal autoscales containers
class TTSModel:
    @modal.enter()
    def load(self):
        # GPT-SoVITS needs both the repo root and the inner GPT_SoVITS/ dir on sys.path and
        # expects to run from the repo root (weight paths in configs are repo-relative).
        for p in (os.path.join(REPO, "GPT_SoVITS"), REPO):
            if p not in sys.path:
                sys.path.insert(0, p)
        os.chdir(REPO)

        from faster_whisper import WhisperModel
        from GPT_SoVITS.TTS_infer_pack.TTS import TTS, TTS_Config

        art = f"/vol/artifacts/{VOICE}_v4"   # v4 LoRA fine-tune (48kHz, reference-faithful)
        # GPT_CKPT/SOVITS_PTH let us A/B specific checkpoints (e.g. candidates/gpt/trump-e12.ckpt)
        # without code edits; default to the run's chosen weights.
        gpt_ckpt = os.environ.get("GPT_CKPT", f"{art}/gpt.ckpt")
        sovits_pth = os.environ.get("SOVITS_PTH", f"{art}/sovits.pth")
        cfg = TTS_Config({
            "custom": {
                "device": "cuda",
                "is_half": True,
                "version": "v4",
                "t2s_weights_path": gpt_ckpt,
                "vits_weights_path": sovits_pth,
                "cnhuhbert_base_path": "GPT_SoVITS/pretrained_models/chinese-hubert-base",
                "bert_base_path": "GPT_SoVITS/pretrained_models/chinese-roberta-wwm-ext-large",
            }
        })
        self.tts = TTS(cfg)

        ref_dir = f"/vol/references/{VOICE}"
        self.ref_wav = f"{ref_dir}/ref.wav"
        with open(f"{ref_dir}/ref.txt", encoding="utf8") as f:
            self.ref_text = f.read().strip()

        self.whisper = WhisperModel("distil-large-v3", device="cuda",
                                    compute_type="float16", download_root=WHISPER_CACHE)
        print(f"loaded GPT-SoVITS v4 + distil-large-v3 for voice={VOICE!r}", flush=True)

    def _transcribe(self, wav_bytes: bytes) -> str:
        with tempfile.NamedTemporaryFile(suffix=".wav") as tmp:
            tmp.write(wav_bytes)
            tmp.flush()
            segments, _ = self.whisper.transcribe(
                tmp.name, language="en", beam_size=5,
                condition_on_previous_text=False, initial_prompt=GLOSSARY,
            )
            return "".join(s.text for s in segments).strip()

    def _synthesize(self, text: str, top_k: int = 20, top_p: float = 0.9,
                    temperature: float = 1.1, speed: float = 1.0,
                    max_chars: int = MAX_CHARS, split: str | None = None) -> bytes:
        import numpy as np
        import soundfile as sf

        # Sampling defaults (temp 1.1 / top_k 20 / top_p 0.9) were picked by ear in the
        # live knob tuner — they were the best of the sweep for energy without tipping the
        # AR model into stutters/early end-of-speech. Earlier we ran a more conservative
        # 0.7/10/0.8 to stop truncation on number-heavy lines; the wider menu here holds up
        # because _segment hands the model short, boundary-aware chunks. Exposed as params
        # so they can still be swept without a redeploy.
        # We do our own boundary-aware segmentation (see _segment) and hand each chunk to
        # the model with cut0 (no further internal splitting), then stitch the audio with a
        # short pause at the joins — which is also where a speaker would naturally breathe.
        # `split` (cut0..cut5) is a testing override that bypasses the segmenter and lets the
        # model use one of GPT-SoVITS' built-in split methods on the whole text instead.
        chunks = [text] if split else _segment(text, max_chars)
        method = split or "cut0"
        sr = None
        parts: list = []
        for chunk in chunks:
            sr, audio = next(self.tts.run({
                "text": chunk,
                "text_lang": "en",
                "ref_audio_path": self.ref_wav,
                "prompt_text": self.ref_text,
                "prompt_lang": "en",
                "top_k": top_k,
                "top_p": top_p,
                "temperature": temperature,
                "speed_factor": speed,
                "text_split_method": method,
                "batch_size": 1,
                "return_fragment": False,
                "parallel_infer": True,
            }))
            parts.append(audio)
        if len(parts) == 1:
            audio = parts[0]
        else:
            gap = np.zeros(int(0.18 * sr), dtype=parts[0].dtype)
            stitched: list = []
            for i, p in enumerate(parts):
                stitched.append(p)
                if i < len(parts) - 1:
                    stitched.append(gap)
            audio = np.concatenate(stitched)
        buf = io.BytesIO()
        sf.write(buf, audio, sr, format="WAV", subtype="PCM_16")
        mp3 = subprocess.run(
            ["ffmpeg", "-hide_banner", "-loglevel", "error", "-i", "pipe:0",
             "-f", "mp3", "-b:a", "192k", "pipe:1"],
            input=buf.getvalue(), stdout=subprocess.PIPE, check=True,
        ).stdout
        return mp3

    @modal.asgi_app()
    def web(self):
        from fastapi import FastAPI, HTTPException, Request, Response
        from starlette.concurrency import run_in_threadpool

        api = FastAPI()

        @api.get("/health")
        async def health():
            return {"ok": True, "voice": VOICE}

        @api.post("/synthesize")
        async def synthesize(request: Request, voice: str = VOICE, text: str | None = None,
                             top_k: int = 20, top_p: float = 0.9, temperature: float = 1.1,
                             speed: float = 1.0, max_chars: int = MAX_CHARS,
                             split: str | None = None):
            if voice != VOICE:
                raise HTTPException(404, f"this endpoint serves {VOICE!r}, not {voice!r}")
            text = (text or "").strip() or None
            if text is None:
                wav = await request.body()
                if not wav:
                    raise HTTPException(400, "send either ?text= or a WAV body")
                text = await run_in_threadpool(self._transcribe, wav)
                if not text:
                    raise HTTPException(422, "couldn't hear any words in that recording")
            mp3 = await run_in_threadpool(
                self._synthesize, text, top_k, top_p, temperature, speed, max_chars, split)
            # HTTP headers are latin-1; em-dashes/smart quotes in the transcript would
            # raise UnicodeEncodeError. The audio is unaffected — only sanitize the echo.
            safe = text[:500].encode("latin-1", "replace").decode("latin-1")
            return Response(content=mp3, media_type="audio/mpeg",
                            headers={"X-Transcript": safe})

        return api
