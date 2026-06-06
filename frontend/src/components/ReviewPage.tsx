import { type MutableRefObject } from "react";
import { NeonWaveform } from "./NeonWaveform";
import { PersonaAvatar } from "./PersonaAvatar";
import { fmtTime } from "../lib/format";
import type { Persona } from "../lib/personas";

interface Props {
  persona: Persona;
  dur: number;
  playing: boolean;
  playProg: number;
  capturedRef: MutableRefObject<number[]>;
  glow: number;
  accent: string;
  onPlay: () => void;
  onRedo: () => void;
  onCopyLink: () => void;
}

export function ReviewPage({ persona, dur, playing, playProg, capturedRef, glow, onPlay, onRedo, onCopyLink }: Props) {
  const pc = persona.c2;
  return (
    <div
      style={{
        display: "flex",
        flexDirection: "column",
        alignItems: "center",
        height: "100%",
        padding: "10px 24px 32px",
        boxSizing: "border-box",
      }}
    >
      <div style={{ display: "flex", flexDirection: "column", alignItems: "center", gap: 8, paddingTop: 6 }}>
        <PersonaAvatar p={persona} size={56} selected />
        <span style={{ fontSize: 15, fontWeight: 600, color: "#fff" }}>{persona.name}</span>
      </div>

      <div style={{ flex: 1, width: "100%", display: "flex", alignItems: "center", justifyContent: "center", minHeight: 130 }}>
        <div style={{ width: "100%" }}>
          <NeonWaveform mode={playing ? "playing" : "ready"} capturedRef={capturedRef} progress={playProg} height={160} glow={glow} />
        </div>
      </div>

      <div style={{ fontSize: 13.5, color: "rgba(255,255,255,0.5)", marginBottom: 18 }}>Transformed · {fmtTime(dur)}</div>

      {/* redo · play · copy-link */}
      <div style={{ height: 92, display: "flex", alignItems: "center", justifyContent: "center", gap: 28 }}>
        <RoundIcon onClick={onRedo} title="Re-record">
          <svg width="22" height="22" viewBox="0 0 24 24" fill="none">
            <path d="M3 12a9 9 0 109-9" stroke="rgba(255,255,255,0.7)" strokeWidth="2" strokeLinecap="round" />
            <path d="M3 4v5h5" stroke="rgba(255,255,255,0.7)" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round" />
          </svg>
        </RoundIcon>

        <button
          onClick={onPlay}
          style={{
            width: 80,
            height: 80,
            borderRadius: "50%",
            border: "none",
            cursor: "pointer",
            background: `linear-gradient(145deg, ${persona.c1}, ${pc})`,
            display: "flex",
            alignItems: "center",
            justifyContent: "center",
            padding: 0,
            boxShadow: `0 0 28px ${pc}88`,
          }}
        >
          {playing ? (
            <svg width="26" height="26" viewBox="0 0 24 24">
              <rect x="6" y="5" width="4" height="14" rx="1.5" fill="#fff" />
              <rect x="14" y="5" width="4" height="14" rx="1.5" fill="#fff" />
            </svg>
          ) : (
            <svg width="28" height="28" viewBox="0 0 24 24">
              <path d="M8 5.5v13l11-6.5z" fill="#fff" />
            </svg>
          )}
        </button>

        <RoundIcon onClick={onCopyLink} title="Copy link">
          <svg width="20" height="20" viewBox="0 0 24 24" fill="none">
            <path
              d="M10 13a5 5 0 007.07 0l2.83-2.83a5 5 0 00-7.07-7.07L11.5 4.5M14 11a5 5 0 00-7.07 0L4.1 13.83a5 5 0 007.07 7.07L12.5 19.5"
              stroke="rgba(255,255,255,0.7)"
              strokeWidth="2"
              strokeLinecap="round"
              strokeLinejoin="round"
            />
          </svg>
        </RoundIcon>
      </div>
      <div style={{ display: "flex", gap: 28, marginTop: 10, fontSize: 11.5, color: "rgba(255,255,255,0.4)" }}>
        <span style={{ width: 54, textAlign: "center" }}>Redo</span>
        <span style={{ width: 80, textAlign: "center" }}>{playing ? "Playing" : "Preview"}</span>
        <span style={{ width: 54, textAlign: "center" }}>Link</span>
      </div>
    </div>
  );
}

function RoundIcon({ onClick, title, children }: { onClick: () => void; title: string; children: React.ReactNode }) {
  return (
    <button
      onClick={onClick}
      title={title}
      style={{
        width: 54,
        height: 54,
        borderRadius: "50%",
        border: "none",
        background: "rgba(255,255,255,0.1)",
        cursor: "pointer",
        display: "flex",
        alignItems: "center",
        justifyContent: "center",
        padding: 0,
        flexShrink: 0,
      }}
    >
      {children}
    </button>
  );
}
