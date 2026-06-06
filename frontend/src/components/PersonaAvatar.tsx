import type { Persona } from "../lib/personas";

interface Props {
  p: Persona;
  size?: number;
  selected?: boolean;
  dim?: boolean;
}

export function PersonaAvatar({ p, size = 64, selected = false, dim = false }: Props) {
  return (
    <div
      style={{
        width: size,
        height: size,
        borderRadius: "50%",
        position: "relative",
        flexShrink: 0,
        transition: "transform .25s cubic-bezier(.2,.8,.2,1), opacity .25s",
        transform: selected ? "scale(1.04)" : "scale(1)",
        opacity: dim ? 0.4 : 1,
      }}
    >
      <div
        style={{
          position: "absolute",
          inset: 0,
          borderRadius: "50%",
          background: `linear-gradient(145deg, ${p.c1}, ${p.c2})`,
          display: "flex",
          alignItems: "center",
          justifyContent: "center",
          fontSize: size * 0.42,
          fontWeight: 700,
          color: "#fff",
          boxShadow: selected
            ? `0 0 0 2.5px #0d0d10, 0 0 0 4.5px ${p.c2}, 0 0 22px 2px ${p.c2}aa, 0 0 40px ${p.c1}66`
            : "0 4px 14px rgba(0,0,0,0.4), inset 0 1px 1px rgba(255,255,255,0.25)",
          letterSpacing: -1,
          transition: "box-shadow .3s",
        }}
      >
        {p.mono}
      </div>
    </div>
  );
}
