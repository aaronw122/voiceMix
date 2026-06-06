// Mic capture, ported from the original dev-console recorder.
// Keeps the proven bits: warm-stream reuse (mic spin-up eats the head of a take),
// device persistence with an OverconstrainedError fallback, mime negotiation, and a
// 128kbps floor (default ~48kbps opus smears consonants). Adds an AnalyserNode tap so
// the neon waveform can react to the live mic.

export const MAX_SECONDS = 60;

export interface Take {
  blob: Blob;
  ext: string;
}

let stream: MediaStream | null = null; // kept warm between takes
let mediaRecorder: MediaRecorder | null = null;
let chunks: Blob[] = [];
let audioCtx: AudioContext | null = null;
let stopResolve: ((t: Take | null) => void) | null = null;

function pickMime(): string {
  // Chrome/Firefox record webm/opus; Safari records mp4/aac. Server normalizes either.
  for (const t of ["audio/webm", "audio/mp4"]) {
    if (window.MediaRecorder && MediaRecorder.isTypeSupported(t)) return t;
  }
  return ""; // let the browser choose
}

export function getSavedMicId(): string {
  return localStorage.getItem("micId") ?? "";
}

export function setMicId(id: string): void {
  if (id) localStorage.setItem("micId", id);
  else localStorage.removeItem("micId");
  // release the old device so the next take spins up the new one
  if (stream) {
    stream.getTracks().forEach((t) => t.stop());
    stream = null;
  }
}

async function getMicStream(): Promise<MediaStream> {
  const audio: MediaTrackConstraints & { voiceIsolation?: boolean } = {
    noiseSuppression: true,
    echoCancellation: true,
    autoGainControl: true,
    voiceIsolation: true, // best-effort: ignored where unsupported
  };
  const savedId = getSavedMicId();
  if (savedId) audio.deviceId = { exact: savedId };
  try {
    return await navigator.mediaDevices.getUserMedia({ audio });
  } catch (err) {
    if (savedId && err instanceof DOMException && err.name === "OverconstrainedError") {
      setMicId(""); // saved mic unplugged — fall back to default
      delete audio.deviceId;
      return navigator.mediaDevices.getUserMedia({ audio });
    }
    throw err;
  }
}

export async function listMics(): Promise<MediaDeviceInfo[]> {
  const devices = await navigator.mediaDevices.enumerateDevices();
  return devices.filter((d) => d.kind === "audioinput" && d.deviceId !== "default");
}

export interface StartResult {
  analyser: AnalyserNode | null; // null when an AudioContext can't be created
  live: boolean; // true when capturing a real mic
}

export async function startRecording(): Promise<StartResult> {
  if (!stream || !stream.active) stream = await getMicStream();

  chunks = [];
  const mime = pickMime();
  mediaRecorder = new MediaRecorder(stream, {
    ...(mime ? { mimeType: mime } : {}),
    audioBitsPerSecond: 128000,
  });
  mediaRecorder.ondataavailable = (e) => {
    if (e.data.size) chunks.push(e.data);
  };
  mediaRecorder.onstop = () => {
    const type = mediaRecorder?.mimeType || "audio/webm";
    const blob = new Blob(chunks, { type });
    const take = blob.size ? { blob, ext: type.includes("mp4") ? "m4a" : "webm" } : null;
    closeAnalyser();
    stopResolve?.(take);
    stopResolve = null;
  };

  let analyser: AnalyserNode | null = null;
  let live = false;
  try {
    const Ctx = window.AudioContext || (window as unknown as { webkitAudioContext: typeof AudioContext }).webkitAudioContext;
    audioCtx = new Ctx();
    const src = audioCtx.createMediaStreamSource(stream);
    analyser = audioCtx.createAnalyser();
    analyser.fftSize = 2048;
    analyser.smoothingTimeConstant = 0.75;
    src.connect(analyser);
    live = true;
  } catch {
    analyser = null;
    live = false;
  }

  mediaRecorder.start();
  return { analyser, live };
}

export function stopRecording(): Promise<Take | null> {
  return new Promise((resolve) => {
    if (mediaRecorder && mediaRecorder.state === "recording") {
      stopResolve = resolve;
      mediaRecorder.stop();
    } else {
      closeAnalyser();
      resolve(null);
    }
  });
}

function closeAnalyser(): void {
  if (audioCtx) {
    try {
      audioCtx.close();
    } catch {
      /* already closed */
    }
    audioCtx = null;
  }
}

// release the warm mic when leaving the page
export function releaseMic(): void {
  closeAnalyser();
  if (stream) {
    stream.getTracks().forEach((t) => t.stop());
    stream = null;
  }
}
