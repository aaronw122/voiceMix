import { type MutableRefObject } from "react";
import { NeonWaveform } from "./NeonWaveform";
import { PersonaAvatar } from "./PersonaAvatar";
import { fmtTime } from "../lib/format";
import type { Persona } from "../lib/personas";

interface Props {
  transforming: boolean;
  recording: boolean;
  live: boolean;
  seconds: number;
  persona: Persona;
  accent: string;
  glow: number;
  statusText: string;
  analyserRef: MutableRefObject<AnalyserNode | null>;
  capturedRef: MutableRefObject<number[]>;
  onStart: () => void;
  onStop: () => void;
  mics: MediaDeviceInfo[];
  micId: string;
  onMicChange: (id: string) => void;
}

const subtitle: React.CSSProperties = {
  fontSize: 15,
  color: "rgba(255,255,255,0.4)",
  textAlign: "center",
  lineHeight: 1.45,
  margin: 0,
  maxWidth: 230,
};

export function RecordPage({
  transforming,
  recording,
  live,
  seconds,
  persona,
  accent,
  glow,
  statusText,
  analyserRef,
  capturedRef,
  onStart,
  onStop,
  mics,
  micId,
  onMicChange,
}: Props) {
  return (
    <div
      style={{
        display: "flex",
        flexDirection: "column",
        alignItems: "center",
        height: "100%",
        padding: "6px 24px 32px",
        boxSizing: "border-box",
      }}
    >
      {/* persona chip */}
      <div style={{ display: "flex", flexDirection: "column", alignItems: "center", gap: 8, paddingTop: 6 }}>
        <PersonaAvatar p={persona} size={56} selected />
        <div style={{ display: "flex", alignItems: "center", gap: 8 }}>
          <span style={{ fontSize: 15, fontWeight: 600, color: "#fff" }}>{persona.name}</span>
          {recording && (
            <span
              style={{
                fontSize: 10.5,
                fontWeight: 700,
                padding: "2px 6px",
                borderRadius: 5,
                letterSpacing: 0.4,
                background: live ? "rgba(52,211,153,0.16)" : "rgba(255,255,255,0.1)",
                color: live ? "#34d399" : "rgba(255,255,255,0.5)",
                whiteSpace: "nowrap",
              }}
            >
              {live ? "LIVE MIC" : "NO MIC"}
            </span>
          )}
        </div>
      </div>

      {/* waveform */}
      <div
        style={{
          flex: 1,
          width: "100%",
          display: "flex",
          alignItems: "center",
          justifyContent: "center",
          minHeight: 130,
        }}
      >
        {recording || transforming ? (
          <div style={{ width: "100%" }}>
            <NeonWaveform
              mode={transforming ? "transforming" : "recording"}
              analyserRef={analyserRef}
              capturedRef={capturedRef}
              height={160}
              glow={glow}
            />
          </div>
        ) : (
          <p style={subtitle}>Tap the button below and speak. Your voice becomes theirs.</p>
        )}
      </div>

      {/* status / timer */}
      <div style={{ minHeight: 26, marginBottom: 18 }}>
        {recording && (
          <span style={{ fontSize: 19, fontWeight: 600, color: "#fff", fontVariantNumeric: "tabular-nums", letterSpacing: 0.5 }}>
            <span
              style={{
                display: "inline-block",
                width: 9,
                height: 9,
                borderRadius: "50%",
                background: accent,
                marginRight: 9,
                verticalAlign: "middle",
                animation: "vpulse 1s infinite",
              }}
            />
            {fmtTime(seconds)}
          </span>
        )}
        {transforming && <span style={{ fontSize: 14.5, color: "rgba(255,255,255,0.7)", fontWeight: 500 }}>{statusText}</span>}
      </div>

      {/* control */}
      <div style={{ height: 92, display: "flex", alignItems: "center", justifyContent: "center" }}>
        {transforming ? (
          <Spinner accent={persona.c2} />
        ) : !recording ? (
          <RecordButton accent={accent} onClick={onStart} />
        ) : (
          <button
            onClick={onStop}
            style={{
              width: 76,
              height: 76,
              borderRadius: "50%",
              border: "4px solid rgba(255,255,255,0.5)",
              background: "transparent",
              cursor: "pointer",
              display: "flex",
              alignItems: "center",
              justifyContent: "center",
              padding: 0,
            }}
          >
            <div style={{ width: 28, height: 28, borderRadius: 7, background: accent, boxShadow: `0 0 18px ${accent}aa` }} />
          </button>
        )}
      </div>

      {!recording && !transforming && (
        <>
          <span style={{ fontSize: 12.5, color: "rgba(255,255,255,0.35)", marginTop: 10 }}>Tap to record · max 1:00</span>
          {mics.length > 0 && (
            <select
              value={micId}
              onChange={(e) => onMicChange(e.target.value)}
              style={{
                marginTop: 12,
                maxWidth: "85%",
                background: "rgba(255,255,255,0.06)",
                color: "rgba(255,255,255,0.55)",
                border: "1px solid rgba(255,255,255,0.12)",
                borderRadius: 8,
                padding: "5px 8px",
                fontSize: 12,
              }}
            >
              <option value="">Default microphone</option>
              {mics.map((m) => (
                <option key={m.deviceId} value={m.deviceId}>
                  {m.label || "Microphone"}
                </option>
              ))}
            </select>
          )}
        </>
      )}
      {recording && <span style={{ fontSize: 12.5, color: "rgba(255,255,255,0.35)", marginTop: 10 }}>Tap to stop</span>}
    </div>
  );
}

function RecordButton({ accent, onClick }: { accent: string; onClick: () => void }) {
  return (
    <button
      onClick={onClick}
      style={{
        width: 80,
        height: 80,
        borderRadius: "50%",
        border: "none",
        cursor: "pointer",
        background: "transparent",
        padding: 0,
        position: "relative",
      }}
    >
      <div style={{ position: "absolute", inset: 0, borderRadius: "50%", border: "3px solid rgba(255,255,255,0.7)" }} />
      <div
        style={{
          position: "absolute",
          top: "50%",
          left: "50%",
          transform: "translate(-50%,-50%)",
          width: 60,
          height: 60,
          borderRadius: "50%",
          background: accent,
          boxShadow: `0 0 24px ${accent}aa`,
        }}
      />
    </button>
  );
}

function Spinner({ accent }: { accent: string }) {
  return (
    <div style={{ width: 52, height: 52, position: "relative" }}>
      <svg width="52" height="52" viewBox="0 0 46 46" style={{ animation: "vspin 0.9s linear infinite" }}>
        <circle cx="23" cy="23" r="19" fill="none" stroke="rgba(255,255,255,0.12)" strokeWidth="4" />
        <circle cx="23" cy="23" r="19" fill="none" stroke={accent} strokeWidth="4" strokeLinecap="round" strokeDasharray="40 200" />
      </svg>
    </div>
  );
}
