// voiceMix recorder — record first, then tap voices to convert the same take.
const MAX_SECONDS = 60;

const recordBtn = document.getElementById("record-btn");
const statusEl = document.getElementById("status");
const micSelect = document.getElementById("mic-select");
const voicesEl = document.getElementById("voices");
const resultEl = document.getElementById("result");
const player = document.getElementById("player");
const shareBtn = document.getElementById("share-btn");
const linkBtn = document.getElementById("link-btn");
const againBtn = document.getElementById("again-btn");
const toastEl = document.getElementById("toast");

let voices = [];
let mediaRecorder = null;
let stream = null; // kept warm between takes — mic spin-up (1-3s on bluetooth) eats the head of recordings
let starting = false; // re-entry guard: taps during the getUserMedia gap must not spawn a 2nd recorder
let take = null; // {blob, ext} — the current recording
let takeGen = 0; // bumped per take; stale conversion results check it before landing
let results = {}; // voiceId -> {url, audioUrl, blob} (cache per take)
let failures = {}; // voiceId -> error message (tap to retry)
let wanted = null; // voiceId the user tapped while it was still converting
let current = null; // result currently in the player
let timerId = null;
let autoStopId = null;

const EMOJI = {
  "old-man": "👴", "young-woman": "👩", "femme-fatale": "💋",
  "jfk": "🎩", "trump": "🦅", "obama": "🇺🇸", "mlk": "✊", "queen_elizabeth": "👑",
};

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

async function getMicStream() {
  const audio = {
    noiseSuppression: true,
    echoCancellation: true,
    autoGainControl: true,
    voiceIsolation: true, // best-effort: ignored where unsupported
  };
  const savedId = localStorage.getItem("micId");
  if (savedId) audio.deviceId = { exact: savedId };
  let s;
  try {
    s = await navigator.mediaDevices.getUserMedia({ audio });
  } catch (err) {
    if (savedId && err.name === "OverconstrainedError") {
      localStorage.removeItem("micId"); // saved mic unplugged — fall back to default
      delete audio.deviceId;
      s = await navigator.mediaDevices.getUserMedia({ audio });
    } else {
      throw err;
    }
  }
  showActiveMic(s);
  refreshMicList(); // labels are only available after a grant
  return s;
}

function showActiveMic(s) {
  const label = s.getAudioTracks()[0]?.label;
  if (label) micSelect.title = `recording with: ${label}`;
}

async function refreshMicList() {
  const devices = await navigator.mediaDevices.enumerateDevices();
  const mics = devices.filter((d) => d.kind === "audioinput" && d.deviceId !== "default");
  if (!mics.length) return;
  const savedId = localStorage.getItem("micId");
  const activeLabel = stream?.getAudioTracks()[0]?.label;
  micSelect.innerHTML = "";
  for (const m of mics) {
    const opt = document.createElement("option");
    opt.value = m.deviceId;
    opt.textContent = `🎤 ${m.label || "microphone"}`;
    if (savedId ? m.deviceId === savedId : m.label === activeLabel) opt.selected = true;
    micSelect.appendChild(opt);
  }
}

micSelect.onchange = () => {
  localStorage.setItem("micId", micSelect.value);
  if (stream) {
    stream.getTracks().forEach((t) => t.stop()); // release old device; next take uses the new one
    stream = null;
  }
};

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
  statusEl.textContent = "getting mic ready…"; // honest state: capture has NOT begun yet
  try {
    if (!stream || !stream.active) {
      stream = await getMicStream();
    }
  } catch {
    starting = false;
    statusEl.textContent = "voiceMix needs your mic — check the address-bar permission";
    return;
  }
  const chunks = []; // scoped per session — a stray recorder can never pollute another take
  const mime = pickMime();
  mediaRecorder = new MediaRecorder(stream, {
    ...(mime ? { mimeType: mime } : {}),
    audioBitsPerSecond: 128000, // default ~48kbps opus smears consonants
  });
  mediaRecorder.ondataavailable = (e) => e.data.size && chunks.push(e.data);
  mediaRecorder.onstop = () => {
    // stream stays warm for the next take (released on pagehide)
    const type = mediaRecorder.mimeType || "audio/webm";
    recordBtn.classList.remove("recording");
    recordBtn.textContent = "🎙️";
    const blob = new Blob(chunks, { type });
    if (blob.size === 0) {
      statusEl.textContent = "that was too short — tap and speak for a second";
      return;
    }
    take = { blob, ext: type.includes("mp4") ? "m4a" : "webm" };
    takeGen++; // stale in-flight conversions from the previous take get ignored
    results = {};
    failures = {};
    wanted = null;
    statusEl.textContent = "pick a voice — converting all of them…";
    voicesEl.classList.add("visible");
    startAllConversions(); // parallel: every card becomes instant once its result lands
  };
  mediaRecorder.start();
  starting = false;
  recordBtn.classList.add("recording");
  recordBtn.textContent = "⏹";
  resultEl.classList.remove("visible");
  voicesEl.classList.remove("visible");

  const startedAt = Date.now();
  statusEl.textContent = "🔴 speak now! (tap to stop)";
  timerId = setInterval(() => {
    const s = Math.floor((Date.now() - startedAt) / 1000);
    statusEl.textContent = `🔴 recording 0:${String(s).padStart(2, "0")} (tap to stop)`;
  }, 250);
  autoStopId = setTimeout(stopRecording, MAX_SECONDS * 1000);
}

// release the warm mic when leaving the page
window.addEventListener("pagehide", () => {
  if (stream) stream.getTracks().forEach((t) => t.stop());
});

function stopRecording() {
  clearInterval(timerId);
  clearTimeout(autoStopId);
  if (mediaRecorder && mediaRecorder.state === "recording") mediaRecorder.stop();
}

recordBtn.onclick = () => {
  if (mediaRecorder && mediaRecorder.state === "recording") stopRecording();
  else startRecording();
};

async function convertRequest(voice) {
  const form = new FormData();
  form.append("audio", take.blob, `recording.${take.ext}`);
  form.append("voiceId", voice.id);
  const endpoint = voice.engine === "modal" ? "/impersonate" : "/convert";
  const resp = await fetch(endpoint, { method: "POST", body: form });
  const body = await resp.json();
  if (!resp.ok) throw new Error(body.error || "something went wrong");
  const audioBlob = await (await fetch(body.audioUrl)).blob();
  return { ...body, blob: audioBlob };
}

function startAllConversions() {
  for (const v of voices) prefetch(v);
}

function prefetch(voice) {
  const gen = takeGen;
  const btn = voicesEl.querySelector(`[data-id="${voice.id}"]`);
  btn.classList.remove("ready", "failed");
  btn.classList.add("busy");
  delete failures[voice.id];
  convertRequest(voice)
    .then((data) => {
      if (gen !== takeGen) return; // a newer take superseded this conversion
      results[voice.id] = data;
      btn.classList.remove("busy");
      btn.classList.add("ready");
      if (wanted === voice.id) showResult(voice.id, btn); // user was waiting on this card
    })
    .catch((err) => {
      if (gen !== takeGen) return;
      failures[voice.id] = err.message;
      btn.classList.remove("busy");
      btn.classList.add("failed");
      if (wanted === voice.id) {
        wanted = null;
        statusEl.textContent = "pick a voice";
        toast(err.message);
      }
    });
}

function convert(voice, btn) {
  if (!take) return;
  if (results[voice.id]) return showResult(voice.id, btn); // ready — instant
  if (failures[voice.id]) return prefetch(voice); // tap a failed card = retry
  wanted = voice.id; // still cooking — play it the moment it lands
  statusEl.textContent = `cooking ${voice.name}…`;
}

function showResult(voiceId, btn) {
  wanted = null;
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
    await copyLink();
  }
};

async function copyLink() {
  if (!current) return;
  try {
    await navigator.clipboard.writeText(current.url);
    toast("link copied");
  } catch {
    toast(current.url); // clipboard blocked (focus/permission) — at least show the link
  }
}

linkBtn.onclick = copyLink;

againBtn.onclick = () => {
  take = null;
  takeGen++; // in-flight conversions from the old take become no-ops
  current = null;
  wanted = null;
  results = {};
  failures = {};
  resultEl.classList.remove("visible");
  voicesEl.classList.remove("visible");
  statusEl.textContent = "tap to record (max 1:00)";
};

loadVoices().catch(() => toast("couldn't load voices — is the backend up?"));
refreshMicList().catch(() => {}); // shows labels if mic permission was already granted
