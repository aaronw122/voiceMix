// voiceMix recorder — record first, then tap voices to convert the same take.
const MAX_SECONDS = 60;

const recordBtn = document.getElementById("record-btn");
const statusEl = document.getElementById("status");
const voicesEl = document.getElementById("voices");
const resultEl = document.getElementById("result");
const player = document.getElementById("player");
const shareBtn = document.getElementById("share-btn");
const againBtn = document.getElementById("again-btn");
const toastEl = document.getElementById("toast");

let voices = [];
let mediaRecorder = null;
let starting = false; // re-entry guard: taps during the getUserMedia gap must not spawn a 2nd recorder
let take = null; // {blob, ext} — the current recording
let results = {}; // voiceId -> {url, audioUrl, blob} (cache per take)
let current = null; // result currently in the player
let timerId = null;
let autoStopId = null;

const EMOJI = { "old-man": "👴", "young-woman": "👩", "jfk": "🎩" };

function toast(msg) {
  toastEl.textContent = msg;
  toastEl.classList.add("visible");
  setTimeout(() => toastEl.classList.remove("visible"), 2600);
}

function pickMime() {
  // Chrome/Firefox record webm/opus; Safari records mp4/aac. Server normalizes either.
  for (const t of ["audio/webm", "audio/mp4"]) {
    if (window.MediaRecorder && MediaRecorder.isTypeSupported(t)) return t;
  }
  return ""; // let the browser choose
}

async function loadVoices() {
  const resp = await fetch("/voices");
  voices = await resp.json();
  voicesEl.innerHTML = "";
  for (const v of voices) {
    const btn = document.createElement("button");
    btn.className = "voice";
    btn.dataset.id = v.id;
    btn.textContent = `${EMOJI[v.id] ?? "🎤"} ${v.name}`;
    btn.onclick = () => convert(v, btn);
    voicesEl.appendChild(btn);
  }
}

async function startRecording() {
  if (starting) return; // a start is already in flight
  starting = true;
  let stream;
  try {
    stream = await navigator.mediaDevices.getUserMedia({ audio: true });
  } catch {
    starting = false;
    statusEl.textContent = "voiceMix needs your mic — check the address-bar permission";
    return;
  }
  const chunks = []; // scoped per session — a stray recorder can never pollute another take
  const mime = pickMime();
  mediaRecorder = new MediaRecorder(stream, mime ? { mimeType: mime } : undefined);
  mediaRecorder.ondataavailable = (e) => e.data.size && chunks.push(e.data);
  mediaRecorder.onstop = () => {
    stream.getTracks().forEach((t) => t.stop());
    const type = mediaRecorder.mimeType || "audio/webm";
    recordBtn.classList.remove("recording");
    recordBtn.textContent = "🎙️";
    const blob = new Blob(chunks, { type });
    if (blob.size === 0) {
      statusEl.textContent = "that was too short — tap and speak for a second";
      return;
    }
    take = { blob, ext: type.includes("mp4") ? "m4a" : "webm" };
    results = {}; // new take invalidates old conversions
    statusEl.textContent = "pick a voice";
    voicesEl.classList.add("visible");
  };
  mediaRecorder.start();
  starting = false;
  recordBtn.classList.add("recording");
  recordBtn.textContent = "⏹";
  resultEl.classList.remove("visible");
  voicesEl.classList.remove("visible");

  const startedAt = Date.now();
  timerId = setInterval(() => {
    const s = Math.floor((Date.now() - startedAt) / 1000);
    statusEl.textContent = `recording… 0:${String(s).padStart(2, "0")} (tap to stop)`;
  }, 250);
  autoStopId = setTimeout(stopRecording, MAX_SECONDS * 1000);
}

function stopRecording() {
  clearInterval(timerId);
  clearTimeout(autoStopId);
  if (mediaRecorder && mediaRecorder.state === "recording") mediaRecorder.stop();
}

recordBtn.onclick = () => {
  if (mediaRecorder && mediaRecorder.state === "recording") stopRecording();
  else startRecording();
};

async function convert(voice, btn) {
  if (!take) return;
  if (results[voice.id]) return showResult(voice.id, btn); // same take, already converted

  const form = new FormData();
  form.append("audio", take.blob, `recording.${take.ext}`);
  form.append("voiceId", voice.id);
  const endpoint = voice.engine === "modal" ? "/impersonate" : "/convert";

  btn.classList.add("busy");
  statusEl.textContent = `cooking ${voice.name}…`;
  try {
    const resp = await fetch(endpoint, { method: "POST", body: form });
    const body = await resp.json();
    if (!resp.ok) throw new Error(body.error || "something went wrong");
    const audioBlob = await (await fetch(body.audioUrl)).blob();
    results[voice.id] = { ...body, blob: audioBlob };
    showResult(voice.id, btn);
  } catch (err) {
    statusEl.textContent = "pick a voice";
    toast(err.message);
  } finally {
    btn.classList.remove("busy");
  }
}

function showResult(voiceId, btn) {
  current = results[voiceId];
  document.querySelectorAll(".voice").forEach((b) => b.classList.remove("active"));
  btn.classList.add("active");
  player.src = URL.createObjectURL(current.blob);
  resultEl.classList.add("visible");
  statusEl.textContent = "tap another voice to compare";
  player.play().catch(() => {}); // autoplay may be blocked; controls are visible anyway
}

shareBtn.onclick = async () => {
  if (!current) return;
  const file = new File([current.blob], "voicemix.mp3", { type: "audio/mpeg" });
  if (navigator.canShare && navigator.canShare({ files: [file] })) {
    try {
      await navigator.share({ files: [file], title: current.title });
    } catch {
      /* user cancelled the share sheet */
    }
  } else {
    await navigator.clipboard.writeText(current.url);
    toast("link copied");
  }
};

againBtn.onclick = () => {
  take = null;
  current = null;
  results = {};
  resultEl.classList.remove("visible");
  voicesEl.classList.remove("visible");
  statusEl.textContent = "tap to record (max 1:00)";
};

loadVoices().catch(() => toast("couldn't load voices — is the backend up?"));
