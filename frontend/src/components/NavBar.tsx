export interface NavButtonConfig {
  label?: string;
  back?: boolean;
  onClick?: () => void;
  disabled?: boolean;
  strong?: boolean;
  color?: string;
}

export interface NavConfig {
  title: string;
  left: NavButtonConfig | null;
  right: NavButtonConfig | null;
}

const IOS_BLUE = "#0a84ff";

function NavButton({ label, back, onClick, disabled, strong, color, accent }: NavButtonConfig & { accent: string }) {
  const c = color || accent || IOS_BLUE;
  if (back) {
    return (
      <button
        onClick={onClick}
        style={{
          background: "none",
          border: "none",
          cursor: "pointer",
          padding: "6px 4px",
          display: "flex",
          alignItems: "center",
          gap: 3,
          color: IOS_BLUE,
        }}
      >
        <svg width="11" height="19" viewBox="0 0 12 20" fill="none">
          <path d="M10 2L2 10l8 8" stroke={IOS_BLUE} strokeWidth="2.6" strokeLinecap="round" strokeLinejoin="round" />
        </svg>
        <span style={{ fontSize: 17 }}>Back</span>
      </button>
    );
  }
  return (
    <button
      onClick={disabled ? undefined : onClick}
      disabled={disabled}
      style={{
        background: "none",
        border: "none",
        cursor: disabled ? "default" : "pointer",
        padding: "6px 4px",
        fontSize: 17,
        fontWeight: strong ? 600 : 400,
        color: disabled ? "rgba(255,255,255,0.28)" : strong ? c : IOS_BLUE,
        transition: "color .2s",
      }}
    >
      {label}
    </button>
  );
}

export function NavBar({ nav, accent }: { nav: NavConfig; accent: string }) {
  return (
    <div
      style={{
        display: "flex",
        alignItems: "center",
        height: 52,
        padding: "0 16px",
        position: "relative",
        flexShrink: 0,
      }}
    >
      <div style={{ flex: 1, display: "flex", justifyContent: "flex-start" }}>
        {nav.left && <NavButton {...nav.left} accent={accent} />}
      </div>
      <div
        style={{
          position: "absolute",
          left: 0,
          right: 0,
          textAlign: "center",
          pointerEvents: "none",
          fontSize: 17,
          fontWeight: 600,
          color: "#fff",
        }}
      >
        {nav.title}
      </div>
      <div style={{ flex: 1, display: "flex", justifyContent: "flex-end" }}>
        {nav.right && <NavButton {...nav.right} accent={accent} />}
      </div>
    </div>
  );
}
