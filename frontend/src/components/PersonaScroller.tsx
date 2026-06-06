// Horizontal scrolling carousel — swipe (touch OR mouse-drag) through voices, snap-centered.
import { useEffect, useRef, type PointerEvent as ReactPointerEvent } from "react";
import type { Persona } from "../lib/personas";
import { PersonaAvatar } from "./PersonaAvatar";

interface Props {
  personas: Persona[];
  value: string;
  onChange: (id: string) => void;
}

export function PersonaScroller({ personas, value, onChange }: Props) {
  const scRef = useRef<HTMLDivElement>(null);
  const sel = personas.find((p) => p.id === value);
  const drag = useRef({ down: false, startX: 0, startScroll: 0, moved: false });
  const justDragged = useRef(false);
  const scrollTO = useRef(0);

  function centerActive() {
    const el = scRef.current;
    if (!el) return;
    const active = el.querySelector<HTMLElement>('[data-active="true"]');
    if (!active) return;
    el.scrollLeft = active.offsetLeft + active.offsetWidth / 2 - el.clientWidth / 2;
  }

  // re-center whenever the selected voice changes; re-assert across the open animation
  useEffect(() => {
    if (drag.current.down) return;
    const ids = [0, 120, 320, 520].map((d) =>
      window.setTimeout(() => {
        if (!drag.current.down) centerActive();
      }, d),
    );
    return () => ids.forEach(clearTimeout);
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [value]);

  function nearestId(): string | null {
    const el = scRef.current;
    if (!el) return null;
    const c = el.getBoundingClientRect();
    const cc = c.left + c.width / 2;
    let best: string | null = null;
    let bd = Infinity;
    el.querySelectorAll<HTMLElement>("[data-pid]").forEach((b) => {
      const r = b.getBoundingClientRect();
      const d = Math.abs(r.left + r.width / 2 - cc);
      if (d < bd) {
        bd = d;
        best = b.getAttribute("data-pid");
      }
    });
    return best;
  }
  function snapSelect() {
    const id = nearestId();
    if (id && id !== value) onChange(id);
    else centerActive();
  }

  // mouse / pen drag (touch uses native momentum scroll)
  function onPointerDown(e: ReactPointerEvent<HTMLDivElement>) {
    if (e.pointerType === "touch") return;
    const el = scRef.current;
    if (!el) return;
    drag.current = { down: true, startX: e.clientX, startScroll: el.scrollLeft, moved: false };
    try {
      el.setPointerCapture(e.pointerId);
    } catch {
      /* capture unsupported */
    }
  }
  function onPointerMove(e: ReactPointerEvent<HTMLDivElement>) {
    if (!drag.current.down || !scRef.current) return;
    const dx = e.clientX - drag.current.startX;
    if (Math.abs(dx) > 4) drag.current.moved = true;
    scRef.current.scrollLeft = drag.current.startScroll - dx;
  }
  function onPointerUp(e: ReactPointerEvent<HTMLDivElement>) {
    if (!drag.current.down) return;
    drag.current.down = false;
    try {
      scRef.current?.releasePointerCapture(e.pointerId);
    } catch {
      /* capture unsupported */
    }
    if (drag.current.moved) {
      justDragged.current = true;
      window.setTimeout(() => {
        justDragged.current = false;
      }, 60);
    }
    snapSelect();
  }
  function onScroll() {
    if (drag.current.down) return;
    clearTimeout(scrollTO.current);
    scrollTO.current = window.setTimeout(() => {
      if (!drag.current.down) snapSelect();
    }, 130);
  }

  return (
    <div style={{ width: "100%" }}>
      <div
        ref={scRef}
        onPointerDown={onPointerDown}
        onPointerMove={onPointerMove}
        onPointerUp={onPointerUp}
        onPointerCancel={onPointerUp}
        onScroll={onScroll}
        className="persona-scroller"
        style={{
          display: "flex",
          gap: 22,
          overflowX: "auto",
          scrollSnapType: "x proximity",
          padding: "14px 50%",
          WebkitOverflowScrolling: "touch",
          position: "relative",
          cursor: "grab",
          touchAction: "pan-x",
          userSelect: "none",
        }}
      >
        {personas.map((p) => {
          const active = value === p.id;
          return (
            <button
              key={p.id}
              data-active={active}
              data-pid={p.id}
              onClick={() => {
                if (justDragged.current) return;
                onChange(p.id);
              }}
              style={{
                background: "none",
                border: "none",
                padding: 0,
                cursor: "pointer",
                flexShrink: 0,
                display: "flex",
                flexDirection: "column",
                alignItems: "center",
                gap: 12,
                scrollSnapAlign: "center",
                transition: "transform .3s cubic-bezier(.2,.8,.2,1), opacity .3s",
                transform: active ? "scale(1)" : "scale(0.78)",
                opacity: active ? 1 : 0.45,
              }}
            >
              <PersonaAvatar p={p} size={104} selected={active} />
              <span
                style={{
                  fontSize: 15,
                  fontWeight: active ? 700 : 500,
                  color: active ? "#fff" : "rgba(255,255,255,0.55)",
                  whiteSpace: "nowrap",
                  transition: "color .2s",
                  pointerEvents: "none",
                }}
              >
                {p.name}
              </span>
            </button>
          );
        })}
      </div>

      {/* dot indicators */}
      <div style={{ display: "flex", justifyContent: "center", gap: 7, marginTop: 6 }}>
        {personas.map((p) => (
          <div
            key={p.id}
            style={{
              width: value === p.id ? 18 : 6,
              height: 6,
              borderRadius: 3,
              background: value === p.id ? (sel ? sel.c2 : "#fff") : "rgba(255,255,255,0.22)",
              transition: "all .3s",
            }}
          />
        ))}
      </div>

      {/* selected description */}
      <div style={{ textAlign: "center", marginTop: 20, minHeight: 40, padding: "0 12px" }}>
        <div
          style={{
            fontSize: 13.5,
            color: sel ? "rgba(255,255,255,0.6)" : "rgba(255,255,255,0.35)",
            lineHeight: 1.45,
          }}
        >
          {sel ? sel.tag : "Swipe to browse voices"}
        </div>
      </div>
    </div>
  );
}
