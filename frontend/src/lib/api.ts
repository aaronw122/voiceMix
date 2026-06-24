// Served from the frontend origin (voicemix.awill.co); the API lives on a different
// origin, so /voices, /convert and /impersonate are addressed via API_BASE.
import type { Voice } from "./personas";
import type { Take } from "./recorder";

const API_BASE = import.meta.env.VITE_API_BASE_URL ?? "https://voiceapi.awill.co";

export interface ConvertResult {
  url: string; // shareable web link
  audioUrl: string; // direct audio URL
  title?: string;
  blob: Blob; // fetched audio bytes for local playback / share
}

export async function loadVoices(): Promise<Voice[]> {
  const resp = await fetch(`${API_BASE}/voices`);
  if (!resp.ok) throw new Error("couldn't load voices");
  return resp.json();
}

// Pre-warm the voice's GPU container the instant recording starts, so its ~20-60s Modal
// cold-start overlaps the recording instead of stacking onto the transform request. Only
// modal voices have a cold-start (ElevenLabs is always-on). Fire-and-forget: never await,
// never surface errors — warming is pure latency optimization, the flow works without it.
export function warm(voice: Voice): void {
  if (voice.engine !== "modal") return;
  const form = new FormData();
  form.append("voiceId", voice.id);
  fetch(`${API_BASE}/warm`, { method: "POST", body: form, keepalive: true }).catch(() => {});
}

export async function convert(voice: Voice, take: Take): Promise<ConvertResult> {
  const form = new FormData();
  form.append("audio", take.blob, `recording.${take.ext}`);
  form.append("voiceId", voice.id);
  const endpoint = voice.engine === "modal" ? "/impersonate" : "/convert";

  const resp = await fetch(`${API_BASE}${endpoint}`, { method: "POST", body: form });
  const body = await resp.json();
  if (!resp.ok) throw new Error(body.error || "something went wrong");
  const blob = await (await fetch(body.audioUrl)).blob();
  return { ...body, blob };
}
