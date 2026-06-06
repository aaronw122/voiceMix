import { useCallback, useEffect, useRef, useState } from "react";
import { PersonaScroller } from "./components/PersonaScroller";
import { RecordPage } from "./components/RecordPage";
import { ReviewPage } from "./components/ReviewPage";
import { NavBar, type NavConfig } from "./components/NavBar";
import { decorate, type Persona } from "./lib/personas";
import { convert, loadVoices, type ConvertResult } from "./lib/api";
import {
  MAX_SECONDS,
  getSavedMicId,
  listMics,
  releaseMic,
  setMicId as persistMicId,
  startRecording,
  stopRecording,
  type Take,
} from "./lib/recorder";

const RECORD_ACCENT = "#ff9500";
const SEND_COLOR = "#0a84ff";
const GLOW = 1;

type Step = "persona" | "record" | "transforming" | "review";
const STEP_INDEX: Record<Step, number> = { persona: 0, record: 1, transforming: 1, review: 2 };

const TRANSFORM_STATUS = [
  "Uploading your voice…",
  "Analyzing tone & cadence…",
  "Applying voice model…",
  "Rendering new audio…",
];

export function App() {
  const [personas, setPersonas] = useState<Persona[]>([]);
  const [personaId, setPersonaId] = useState("");
  const [step, setStep] = useState<Step>("persona");
  const [recording, setRecording] = useState(false);
  const [live, setLive] = useState(false);
  const [seconds, setSeconds] = useState(0);
  const [statusIdx, setStatusIdx] = useState(0);
  const [playing, setPlaying] = useState(false);
  const [playProg, setPlayProg] = useState(0);
  const [dur, setDur] = useState(1);
  const [toast, setToast] = useState("");
  const [mics, setMics] = useState<MediaDeviceInfo[]>([]);
  const [micId, setMicId] = useState(getSavedMicId());

  const capturedRef = useRef<number[]>([]);
  const analyserRef = useRef<AnalyserNode | null>(null);
  const timerRef = useRef(0);
  const autoStopRef = useRef(0);
  const playRafRef = useRef(0);
  const audioRef = useRef<HTMLAudioElement | null>(null);
  const resultRef = useRef<ConvertResult | null>(null);
  const takeRef = useRef<Take | null>(null);

  const persona = personas.find((p) => p.id === personaId);

  const showToast = useCallback((msg: string) => {
    setToast(msg);
    window.setTimeout(() => setToast(""), 2600);
  }, []);

  // load voices + mic list
  useEffect(() => {
    loadVoices()
      .then((vs) => {
        const decorated = vs.map(decorate);
        setPersonas(decorated);
        setPersonaId((id) => id || decorated[0]?.id || "");
      })
      .catch(() => showToast("couldn't load voices — is the backend up?"));
    listMics().then(setMics).catch(() => {});
    return () => releaseMic();
  }, [showToast]);

  useEffect(() => {
    const onHide = () => releaseMic();
    window.addEventListener("pagehide", onHide);
    return () => window.removeEventListener("pagehide", onHide);
  }, []);

  // ---- recording ----
  async function onStart() {
    setSeconds(0);
    capturedRef.current = [];
    setLive(false);
    setRecording(true);
    timerRef.current = window.setInterval(() => setSeconds((s) => s + 0.1), 100);
    autoStopRef.current = window.setTimeout(onStop, MAX_SECONDS * 1000);
    try {
      const { analyser, live: isLive } = await startRecording();
      analyserRef.current = analyser;
      setLive(isLive);
      listMics().then(setMics).catch(() => {}); // labels appear after a grant
    } catch {
      clearInterval(timerRef.current);
      clearTimeout(autoStopRef.current);
      setRecording(false);
      showToast("voiceMix needs your mic — check the address-bar permission");
    }
  }

  async function onStop() {
    clearInterval(timerRef.current);
    clearTimeout(autoStopRef.current);
    const take = await stopRecording();
    analyserRef.current = null;
    setRecording(false);
    if (!take) {
      showToast("that was too short — tap and speak for a second");
      return;
    }
    takeRef.current = take;
    // ensure 'transforming' has bars to shimmer even if the mic was silent/denied
    if (!capturedRef.current.length) {
      capturedRef.current = Array.from({ length: 54 }, (_, i) => 0.2 + 0.6 * Math.abs(Math.sin(i * 0.7) * Math.cos(i * 0.31)));
    }
    setStep("transforming");
    transform(take);
  }

  // ---- real transform (replaces the prototype's simulated delay) ----
  async function transform(take: Take) {
    if (!persona) return;
    setStatusIdx(0);
    const cycle = window.setInterval(() => setStatusIdx((i) => Math.min(i + 1, TRANSFORM_STATUS.length - 1)), 850);
    try {
      const res = await convert(persona, take);
      resultRef.current = res;
      const url = URL.createObjectURL(res.blob);
      if (audioRef.current) URL.revokeObjectURL(audioRef.current.src);
      const a = new Audio(url);
      a.onloadedmetadata = () => setDur(Math.max(1, Math.round(a.duration || seconds)));
      a.onended = () => {
        cancelAnimationFrame(playRafRef.current);
        setPlaying(false);
        window.setTimeout(() => setPlayProg(0), 400);
      };
      audioRef.current = a;
      setDur(Math.max(1, Math.round(seconds)));
      setStep("review");
    } catch (err) {
      setStep("record");
      showToast(err instanceof Error ? err.message : "conversion failed");
    } finally {
      clearInterval(cycle);
    }
  }

  // ---- playback (drives the waveform from the real audio element) ----
  function onPlay() {
    const a = audioRef.current;
    if (!a) return;
    if (playing) {
      a.pause();
      a.currentTime = 0;
      cancelAnimationFrame(playRafRef.current);
      setPlaying(false);
      setPlayProg(0);
      return;
    }
    a.currentTime = 0;
    a.play().catch(() => {});
    setPlaying(true);
    setPlayProg(0);
    const tick = () => {
      const p = a.duration ? a.currentTime / a.duration : 0;
      setPlayProg(Math.min(1, p));
      if (!a.paused && !a.ended) playRafRef.current = requestAnimationFrame(tick);
    };
    playRafRef.current = requestAnimationFrame(tick);
  }

  function stopPlayback() {
    const a = audioRef.current;
    if (a) {
      a.pause();
      a.currentTime = 0;
    }
    cancelAnimationFrame(playRafRef.current);
    setPlaying(false);
    setPlayProg(0);
  }

  // ---- nav actions ----
  function goRecord() {
    stopPlayback();
    setStep("record");
    setRecording(false);
    setSeconds(0);
  }

  function backToPersona() {
    clearInterval(timerRef.current);
    clearTimeout(autoStopRef.current);
    setRecording(false);
    analyserRef.current = null;
    setStep("persona");
  }

  async function share() {
    const res = resultRef.current;
    if (!res) return;
    const file = new File([res.blob], "voicemix.mp3", { type: "audio/mpeg" });
    if (navigator.canShare?.({ files: [file] })) {
      try {
        await navigator.share({ files: [file], title: res.title });
      } catch {
        /* user cancelled the share sheet */
      }
    } else {
      copyLink();
    }
  }

  async function copyLink() {
    const res = resultRef.current;
    if (!res) return;
    try {
      await navigator.clipboard.writeText(res.url);
      showToast("link copied");
    } catch {
      showToast(res.url);
    }
  }

  useEffect(
    () => () => {
      clearInterval(timerRef.current);
      clearTimeout(autoStopRef.current);
      cancelAnimationFrame(playRafRef.current);
    },
    [],
  );

  const idx = STEP_INDEX[step];

  const nav: NavConfig = {
    persona: { title: "Choose a Voice", left: null, right: { label: "Next", onClick: () => setStep("record"), disabled: !personaId, strong: true } },
    record: { title: persona ? persona.name : "Record", left: { back: true, onClick: backToPersona }, right: null },
    transforming: { title: "Transforming", left: null, right: null },
    review: { title: "Preview", left: { back: true, onClick: goRecord }, right: { label: "Share", onClick: share, strong: true, color: SEND_COLOR } },
  }[step];

  return (
    <div className="app-bg">
      <div className="frame">
        {/* ambient glow */}
        <div
          style={{
            position: "absolute",
            top: -100,
            left: "50%",
            transform: "translateX(-50%)",
            width: 340,
            height: 220,
            borderRadius: "50%",
            background: persona ? `radial-gradient(circle, ${persona.c2}3a, transparent 70%)` : "radial-gradient(circle, rgba(91,134,229,0.16), transparent 70%)",
            filter: "blur(26px)",
            pointerEvents: "none",
            transition: "background .4s",
          }}
        />

        <NavBar nav={nav} accent={RECORD_ACCENT} />

        {/* pager */}
        <div style={{ flex: 1, position: "relative", overflow: "hidden" }}>
          <div
            style={{
              display: "flex",
              width: "300%",
              height: "100%",
              transform: `translateX(-${idx * 33.3333}%)`,
              transition: "transform .42s cubic-bezier(.3,.9,.3,1)",
            }}
          >
            {/* PAGE 1 — persona */}
            <Page>
              <div style={{ height: "100%", display: "flex", flexDirection: "column", justifyContent: "center", paddingBottom: 24 }}>
                <p style={{ fontSize: 13.5, color: "rgba(255,255,255,0.5)", textAlign: "center", margin: "0 0 18px", lineHeight: 1.45, padding: "0 34px" }}>
                  Pick a voice. Your recording will be re-voiced in this persona.
                </p>
                {personas.length > 0 ? (
                  <PersonaScroller personas={personas} value={personaId} onChange={setPersonaId} />
                ) : (
                  <p style={{ textAlign: "center", color: "rgba(255,255,255,0.35)", fontSize: 14 }}>Loading voices…</p>
                )}
              </div>
            </Page>

            {/* PAGE 2 — record / transforming */}
            <Page>
              {persona && (
                <RecordPage
                  transforming={step === "transforming"}
                  recording={recording}
                  live={live}
                  seconds={seconds}
                  persona={persona}
                  accent={RECORD_ACCENT}
                  glow={GLOW}
                  statusText={TRANSFORM_STATUS[statusIdx]}
                  analyserRef={analyserRef}
                  capturedRef={capturedRef}
                  onStart={onStart}
                  onStop={onStop}
                  mics={mics}
                  micId={micId}
                  onMicChange={(id) => {
                    persistMicId(id);
                    setMicId(id);
                  }}
                />
              )}
            </Page>

            {/* PAGE 3 — review */}
            <Page>
              {persona && (
                <ReviewPage
                  persona={persona}
                  dur={dur}
                  playing={playing}
                  playProg={playProg}
                  capturedRef={capturedRef}
                  glow={GLOW}
                  accent={RECORD_ACCENT}
                  onPlay={onPlay}
                  onRedo={goRecord}
                  onCopyLink={copyLink}
                />
              )}
            </Page>
          </div>
        </div>

        {toast && (
          <div
            style={{
              position: "absolute",
              bottom: 22,
              left: "50%",
              transform: "translateX(-50%)",
              background: "rgba(28,28,32,0.96)",
              border: "1px solid rgba(255,255,255,0.1)",
              borderRadius: 11,
              padding: "10px 16px",
              fontSize: 13.5,
              color: "#fff",
              maxWidth: "85%",
              textAlign: "center",
              animation: "vtoast-in .25s ease",
              zIndex: 50,
            }}
          >
            {toast}
          </div>
        )}
      </div>
    </div>
  );
}

function Page({ children }: { children: React.ReactNode }) {
  return <div style={{ width: "33.3333%", height: "100%", overflowY: "auto", flexShrink: 0 }}>{children}</div>;
}
