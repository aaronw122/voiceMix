// Desktop persona selector — every voice visible and clickable at once (no swipe).
import type { Persona } from "../lib/personas";
import { PersonaAvatar } from "./PersonaAvatar";

interface Props {
  personas: Persona[];
  value: string;
  onChange: (id: string) => void;
}

export function PersonaPicker({ personas, value, onChange }: Props) {
  const sel = personas.find((p) => p.id === value);
  return (
    <div style={{ width: "100%" }}>
      <div style={{ display: "flex", justifyContent: "center", flexWrap: "wrap", gap: 40, padding: "4px 16px 14px" }}>
        {personas.map((p) => (
          <button
            key={p.id}
            onClick={() => onChange(p.id)}
            style={{
              background: "none",
              border: "none",
              padding: 0,
              cursor: "pointer",
              display: "flex",
              flexDirection: "column",
              alignItems: "center",
              gap: 12,
            }}
          >
            <PersonaAvatar p={p} selected={value === p.id} dim={!!value && value !== p.id} size={92} />
            <span
              style={{
                fontSize: 14.5,
                fontWeight: value === p.id ? 600 : 500,
                color: value === p.id ? "#fff" : "rgba(255,255,255,0.5)",
                transition: "color .2s",
              }}
            >
              {p.name}
            </span>
          </button>
        ))}
      </div>
      <div
        style={{
          textAlign: "center",
          minHeight: 18,
          marginTop: 10,
          fontSize: 13.5,
          color: sel ? "rgba(255,255,255,0.55)" : "rgba(255,255,255,0.32)",
          transition: "color .2s",
        }}
      >
        {sel ? sel.tag : "Choose a voice to begin"}
      </div>
    </div>
  );
}
