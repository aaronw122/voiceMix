#!/usr/bin/env python3
"""
Tiny local RVC tester.

Open http://127.0.0.1:8765, record a short mic clip, choose a 50-epoch model,
then this server converts the recording to WAV, uploads it to the Modal volume,
runs train_rvc_modal.py::infer_main, downloads the output, and serves it back.
"""
from __future__ import annotations

import json
import mimetypes
import os
import shutil
import subprocess
import time
import uuid
from http import HTTPStatus
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import parse_qs, urlparse


ROOT = Path(__file__).resolve().parent
WORK_DIR = ROOT / "data" / "rvc_test_app"
UPLOAD_DIR = WORK_DIR / "uploads"
OUTPUT_DIR = WORK_DIR / "outputs"
VOLUME = os.environ.get("RVC_MODAL_VOLUME", "rvc-vol")
HOST = os.environ.get("RVC_TEST_HOST", "127.0.0.1")
PORT = int(os.environ.get("RVC_TEST_PORT", "8765"))
MAX_UPLOAD_BYTES = 25 * 1024 * 1024

MODELS = {
    "trump": "Donald Trump",
    "jfk": "JFK",
    "mlk": "MLK",
    "queen_elizabeth": "Queen Elizabeth II",
    "obama": "Obama",
}


HTML = """<!doctype html>
<html lang="en">
<head>
  <meta charset="utf-8">
  <meta name="viewport" content="width=device-width, initial-scale=1">
  <title>RVC Voice Tester</title>
  <style>
    :root {
      color-scheme: light;
      --bg: #f5f6f8;
      --panel: #ffffff;
      --ink: #17202a;
      --muted: #657181;
      --line: #d7dce3;
      --focus: #1967d2;
      --accent: #0f766e;
      --accent-dark: #0b5f59;
      --danger: #b3261e;
      --shadow: 0 16px 40px rgba(22, 31, 42, 0.10);
    }

    * {
      box-sizing: border-box;
    }

    body {
      margin: 0;
      min-height: 100vh;
      font-family: Inter, ui-sans-serif, system-ui, -apple-system, BlinkMacSystemFont, "Segoe UI", sans-serif;
      color: var(--ink);
      background:
        linear-gradient(180deg, #eef2f5 0%, var(--bg) 42%),
        var(--bg);
    }

    main {
      width: min(1060px, calc(100% - 32px));
      margin: 0 auto;
      padding: 28px 0 36px;
    }

    header {
      display: flex;
      align-items: end;
      justify-content: space-between;
      gap: 20px;
      margin-bottom: 18px;
    }

    h1 {
      margin: 0;
      font-size: 28px;
      line-height: 1.15;
      letter-spacing: 0;
    }

    .status-pill {
      min-width: 170px;
      padding: 9px 12px;
      border: 1px solid var(--line);
      border-radius: 8px;
      background: #ffffff;
      color: var(--muted);
      font-size: 13px;
      text-align: center;
    }

    .workspace {
      display: grid;
      grid-template-columns: minmax(0, 1fr) 320px;
      gap: 18px;
    }

    .surface {
      background: var(--panel);
      border: 1px solid var(--line);
      border-radius: 8px;
      box-shadow: var(--shadow);
    }

    .recorder {
      padding: 18px;
    }

    .controls {
      display: grid;
      grid-template-columns: repeat(3, minmax(0, 1fr));
      gap: 10px;
      margin-bottom: 14px;
    }

    button, select, input[type="range"], input[type="number"] {
      font: inherit;
    }

    button {
      min-height: 42px;
      border: 1px solid var(--line);
      border-radius: 8px;
      background: #ffffff;
      color: var(--ink);
      cursor: pointer;
      transition: border-color 120ms ease, background 120ms ease, color 120ms ease, transform 120ms ease;
    }

    button:hover:not(:disabled) {
      border-color: #aeb7c4;
      transform: translateY(-1px);
    }

    button:disabled {
      cursor: not-allowed;
      opacity: 0.48;
    }

    .primary {
      background: var(--accent);
      border-color: var(--accent);
      color: #ffffff;
    }

    .primary:hover:not(:disabled) {
      background: var(--accent-dark);
      border-color: var(--accent-dark);
    }

    .danger {
      color: var(--danger);
      border-color: #efc8c4;
      background: #fff8f7;
    }

    .audio-row {
      display: grid;
      grid-template-columns: 90px minmax(0, 1fr);
      gap: 12px;
      align-items: center;
      padding: 12px 0;
      border-top: 1px solid var(--line);
    }

    .audio-row:first-of-type {
      border-top: 0;
    }

    .label {
      color: var(--muted);
      font-size: 13px;
    }

    audio {
      width: 100%;
      min-width: 0;
    }

    .side {
      padding: 16px;
    }

    .field {
      display: grid;
      gap: 7px;
      margin-bottom: 14px;
    }

    .field label {
      font-size: 13px;
      color: var(--muted);
    }

    select, input[type="number"] {
      width: 100%;
      min-height: 40px;
      border: 1px solid var(--line);
      border-radius: 8px;
      padding: 0 10px;
      background: #ffffff;
      color: var(--ink);
    }

    input[type="range"] {
      width: 100%;
      accent-color: var(--accent);
    }

    .split {
      display: grid;
      grid-template-columns: 1fr 72px;
      gap: 10px;
      align-items: center;
    }

    .log {
      height: 190px;
      overflow: auto;
      padding: 12px;
      border: 1px solid var(--line);
      border-radius: 8px;
      background: #f9fafb;
      color: #344054;
      font-family: ui-monospace, SFMono-Regular, Menlo, Consolas, monospace;
      font-size: 12px;
      line-height: 1.55;
      white-space: pre-wrap;
    }

    .busy {
      position: relative;
      overflow: hidden;
    }

    .busy::after {
      content: "";
      position: absolute;
      inset: auto 0 0 0;
      height: 3px;
      background: linear-gradient(90deg, transparent, var(--accent), transparent);
      animation: sweep 1.1s infinite;
    }

    @keyframes sweep {
      from { transform: translateX(-100%); }
      to { transform: translateX(100%); }
    }

    @media (max-width: 820px) {
      main {
        width: min(100% - 22px, 680px);
        padding-top: 18px;
      }

      header {
        align-items: stretch;
        flex-direction: column;
      }

      .workspace {
        grid-template-columns: 1fr;
      }

      .controls {
        grid-template-columns: 1fr;
      }
    }
  </style>
</head>
<body>
  <main>
    <header>
      <h1>RVC Voice Tester</h1>
      <div class="status-pill" id="status">Ready</div>
    </header>

    <section class="workspace">
      <div class="surface recorder" id="recorderPanel">
        <div class="controls">
          <button class="primary" id="recordBtn">Record</button>
          <button class="danger" id="stopBtn" disabled>Stop</button>
          <button id="convertBtn" disabled>Convert</button>
        </div>

        <div class="audio-row">
          <div class="label">Input</div>
          <audio id="inputAudio" controls></audio>
        </div>
        <div class="audio-row">
          <div class="label">Output</div>
          <audio id="outputAudio" controls></audio>
        </div>
      </div>

      <aside class="surface side">
        <div class="field">
          <label for="modelSelect">Target voice</label>
          <select id="modelSelect">
            <option value="trump">Donald Trump</option>
            <option value="jfk">JFK</option>
            <option value="mlk">MLK</option>
            <option value="queen_elizabeth">Queen Elizabeth II</option>
            <option value="obama">Obama</option>
          </select>
        </div>

        <div class="field">
          <label for="indexRate">Index rate</label>
          <div class="split">
            <input id="indexRate" type="range" min="0" max="1" step="0.05" value="0.5">
            <input id="indexRateNumber" type="number" min="0" max="1" step="0.05" value="0.5">
          </div>
        </div>

        <div class="field">
          <label for="pitch">Pitch shift</label>
          <input id="pitch" type="number" min="-24" max="24" step="1" value="0">
        </div>

        <div class="log" id="log"></div>
      </aside>
    </section>
  </main>

  <script>
    const recordBtn = document.getElementById("recordBtn");
    const stopBtn = document.getElementById("stopBtn");
    const convertBtn = document.getElementById("convertBtn");
    const statusEl = document.getElementById("status");
    const panel = document.getElementById("recorderPanel");
    const inputAudio = document.getElementById("inputAudio");
    const outputAudio = document.getElementById("outputAudio");
    const modelSelect = document.getElementById("modelSelect");
    const indexRate = document.getElementById("indexRate");
    const indexRateNumber = document.getElementById("indexRateNumber");
    const pitch = document.getElementById("pitch");
    const logEl = document.getElementById("log");

    let recorder = null;
    let chunks = [];
    let inputBlob = null;
    let inputUrl = null;
    let outputUrl = null;

    function log(message) {
      const stamp = new Date().toLocaleTimeString();
      logEl.textContent += `[${stamp}] ${message}\\n`;
      logEl.scrollTop = logEl.scrollHeight;
    }

    function setStatus(text, busy = false) {
      statusEl.textContent = text;
      panel.classList.toggle("busy", busy);
    }

    function setBusy(busy) {
      recordBtn.disabled = busy || Boolean(recorder);
      stopBtn.disabled = busy || !recorder;
      convertBtn.disabled = busy || !inputBlob;
      modelSelect.disabled = busy;
      indexRate.disabled = busy;
      indexRateNumber.disabled = busy;
      pitch.disabled = busy;
    }

    function preferredMimeType() {
      const candidates = [
        "audio/webm;codecs=opus",
        "audio/webm",
        "audio/mp4",
        "audio/ogg;codecs=opus"
      ];
      return candidates.find(type => window.MediaRecorder && MediaRecorder.isTypeSupported(type)) || "";
    }

    indexRate.addEventListener("input", () => {
      indexRateNumber.value = indexRate.value;
    });

    indexRateNumber.addEventListener("input", () => {
      indexRate.value = indexRateNumber.value;
    });

    recordBtn.addEventListener("click", async () => {
      try {
        const stream = await navigator.mediaDevices.getUserMedia({ audio: true });
        chunks = [];
        inputBlob = null;
        outputAudio.removeAttribute("src");
        if (outputUrl) URL.revokeObjectURL(outputUrl);

        const mimeType = preferredMimeType();
        recorder = new MediaRecorder(stream, mimeType ? { mimeType } : undefined);
        recorder.ondataavailable = event => {
          if (event.data && event.data.size) chunks.push(event.data);
        };
        recorder.onstop = () => {
          stream.getTracks().forEach(track => track.stop());
          inputBlob = new Blob(chunks, { type: recorder.mimeType || "audio/webm" });
          if (inputUrl) URL.revokeObjectURL(inputUrl);
          inputUrl = URL.createObjectURL(inputBlob);
          inputAudio.src = inputUrl;
          recorder = null;
          setStatus("Recorded");
          setBusy(false);
          log(`Recorded ${(inputBlob.size / 1024).toFixed(1)} KB`);
        };

        recorder.start();
        setStatus("Recording");
        setBusy(false);
      } catch (err) {
        setStatus("Mic blocked");
        log(err.message || String(err));
      }
    });

    stopBtn.addEventListener("click", () => {
      if (recorder && recorder.state !== "inactive") {
        recorder.stop();
        setStatus("Saving");
      }
    });

    convertBtn.addEventListener("click", async () => {
      if (!inputBlob) return;

      const params = new URLSearchParams({
        model: modelSelect.value,
        index_rate: indexRate.value,
        pitch: pitch.value
      });

      setStatus("Converting", true);
      setBusy(true);
      log(`Sending to ${modelSelect.options[modelSelect.selectedIndex].text}`);

      try {
        const response = await fetch(`/api/convert?${params}`, {
          method: "POST",
          headers: { "Content-Type": inputBlob.type || "application/octet-stream" },
          body: inputBlob
        });

        const payload = await response.json();
        if (!response.ok) {
          throw new Error(payload.error || "Conversion failed");
        }

        if (outputUrl) URL.revokeObjectURL(outputUrl);
        outputUrl = payload.output_url;
        outputAudio.src = outputUrl;
        outputAudio.play().catch(() => {});
        setStatus("Ready");
        log(`Done in ${payload.elapsed_seconds.toFixed(1)}s: ${payload.output_name}`);
      } catch (err) {
        setStatus("Error");
        log(err.message || String(err));
      } finally {
        setBusy(false);
        panel.classList.remove("busy");
      }
    });

    setBusy(false);
    log("Ready");
  </script>
</body>
</html>
"""


def ensure_dirs() -> None:
    UPLOAD_DIR.mkdir(parents=True, exist_ok=True)
    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)


def extension_for(content_type: str) -> str:
    base = content_type.split(";", 1)[0].strip().lower()
    return {
        "audio/webm": ".webm",
        "audio/ogg": ".ogg",
        "audio/mp4": ".m4a",
        "audio/mpeg": ".mp3",
        "audio/wav": ".wav",
        "audio/x-wav": ".wav",
    }.get(base, ".webm")


def run_command(args: list[str], timeout: int) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        args,
        cwd=ROOT,
        text=True,
        capture_output=True,
        timeout=timeout,
        check=False,
    )


def checked_command(args: list[str], timeout: int) -> str:
    result = run_command(args, timeout)
    output = (result.stdout or "") + (result.stderr or "")
    if result.returncode != 0:
        raise RuntimeError(output.strip() or f"command failed: {' '.join(args)}")
    return output


def parse_float(value: str, default: float, low: float, high: float) -> float:
    try:
        parsed = float(value)
    except (TypeError, ValueError):
        parsed = default
    return max(low, min(high, parsed))


def parse_int(value: str, default: int, low: int, high: int) -> int:
    try:
        parsed = int(value)
    except (TypeError, ValueError):
        parsed = default
    return max(low, min(high, parsed))


class Handler(BaseHTTPRequestHandler):
    server_version = "RVCTestApp/1.0"

    def do_GET(self) -> None:
        parsed = urlparse(self.path)
        if parsed.path == "/":
            self.respond_bytes(HTML.encode("utf-8"), "text/html; charset=utf-8")
            return
        if parsed.path == "/api/models":
            self.respond_json({"models": MODELS})
            return
        if parsed.path.startswith("/outputs/"):
            self.serve_output(parsed.path.removeprefix("/outputs/"))
            return
        self.respond_json({"error": "not found"}, HTTPStatus.NOT_FOUND)

    def do_POST(self) -> None:
        parsed = urlparse(self.path)
        if parsed.path != "/api/convert":
            self.respond_json({"error": "not found"}, HTTPStatus.NOT_FOUND)
            return
        try:
            self.handle_convert(parsed.query)
        except Exception as exc:
            self.respond_json({"error": str(exc)}, HTTPStatus.INTERNAL_SERVER_ERROR)

    def handle_convert(self, query: str) -> None:
        params = parse_qs(query)
        model = params.get("model", [""])[0]
        if model not in MODELS:
            self.respond_json({"error": "unknown model"}, HTTPStatus.BAD_REQUEST)
            return

        content_length = int(self.headers.get("Content-Length") or "0")
        if content_length <= 0:
            self.respond_json({"error": "empty recording"}, HTTPStatus.BAD_REQUEST)
            return
        if content_length > MAX_UPLOAD_BYTES:
            self.respond_json({"error": "recording is too large"}, HTTPStatus.REQUEST_ENTITY_TOO_LARGE)
            return

        index_rate = parse_float(params.get("index_rate", ["0.5"])[0], 0.5, 0.0, 1.0)
        pitch = parse_int(params.get("pitch", ["0"])[0], 0, -24, 24)
        job_id = uuid.uuid4().hex[:12]
        raw_ext = extension_for(self.headers.get("Content-Type", ""))
        raw_path = UPLOAD_DIR / f"{job_id}{raw_ext}"
        wav_name = f"rvc_test_{model}_{job_id}.wav"
        wav_path = UPLOAD_DIR / wav_name
        output_name = f"{Path(wav_name).stem}__as_{model}.wav"
        output_path = OUTPUT_DIR / output_name

        raw_path.write_bytes(self.rfile.read(content_length))
        start = time.monotonic()

        checked_command(
            [
                "ffmpeg",
                "-hide_banner",
                "-loglevel",
                "error",
                "-y",
                "-i",
                str(raw_path),
                "-ac",
                "1",
                "-ar",
                "48000",
                "-acodec",
                "pcm_s16le",
                str(wav_path),
            ],
            timeout=60,
        )

        checked_command(
            ["modal", "volume", "put", "--force", VOLUME, str(wav_path), f"/sources/{wav_name}"],
            timeout=120,
        )

        checked_command(
            [
                "modal",
                "run",
                "train_rvc_modal.py::infer_main",
                "--model-name",
                model,
                "--source-name",
                wav_name,
                "--index-rate",
                str(index_rate),
                "--pitch",
                str(pitch),
            ],
            timeout=900,
        )

        if output_path.exists():
            output_path.unlink()

        checked_command(
            ["modal", "volume", "get", VOLUME, f"/outputs/{output_name}", str(OUTPUT_DIR)],
            timeout=180,
        )

        if not output_path.exists():
            raise RuntimeError(f"conversion finished, but output was not downloaded: {output_name}")

        self.respond_json(
            {
                "model": model,
                "output_name": output_name,
                "output_url": f"/outputs/{output_name}",
                "elapsed_seconds": time.monotonic() - start,
            }
        )

    def serve_output(self, name: str) -> None:
        clean_name = Path(name).name
        path = OUTPUT_DIR / clean_name
        if not path.exists() or not path.is_file():
            self.respond_json({"error": "output not found"}, HTTPStatus.NOT_FOUND)
            return
        content_type = mimetypes.guess_type(path.name)[0] or "audio/wav"
        self.respond_bytes(path.read_bytes(), content_type)

    def respond_json(self, payload: dict, status: HTTPStatus = HTTPStatus.OK) -> None:
        self.respond_bytes(
            json.dumps(payload).encode("utf-8"),
            "application/json; charset=utf-8",
            status,
        )

    def respond_bytes(
        self,
        body: bytes,
        content_type: str,
        status: HTTPStatus = HTTPStatus.OK,
    ) -> None:
        self.send_response(status)
        self.send_header("Content-Type", content_type)
        self.send_header("Content-Length", str(len(body)))
        self.send_header("Cache-Control", "no-store")
        self.end_headers()
        self.wfile.write(body)

    def log_message(self, fmt: str, *args: object) -> None:
        print(f"{self.address_string()} - {fmt % args}", flush=True)


def main() -> None:
    ensure_dirs()
    missing = [cmd for cmd in ("modal", "ffmpeg") if shutil.which(cmd) is None]
    if missing:
        raise SystemExit(f"missing required command(s): {', '.join(missing)}")

    server = ThreadingHTTPServer((HOST, PORT), Handler)
    print(f"RVC tester running at http://{HOST}:{PORT}")
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        print("\nStopping RVC tester")


if __name__ == "__main__":
    main()
