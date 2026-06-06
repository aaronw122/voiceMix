// Visual metadata for each voice. The backend /voices endpoint owns id/name/engine;
// this map layers on the gradient + mono glyph + tag the carousel renders.
// Palette tokens mirror the Voice Transform design handoff.
export interface VoiceVisual {
  c1: string;
  c2: string;
  mono: string;
  tag: string;
}

const VISUALS: Record<string, VoiceVisual> = {
  "old-man": { c1: "#f7b733", c2: "#fc4a1a", mono: "O", tag: "Weathered · warm · unhurried" },
  "young-woman": { c1: "#f857a6", c2: "#9b5cf6", mono: "Y", tag: "Bright · clear · youthful" },
  "femme-fatale": { c1: "#ff6a88", c2: "#b5179e", mono: "F", tag: "Sultry · smoky · bold" },
  jfk: { c1: "#36d1dc", c2: "#5b86e5", mono: "J", tag: "Resonant · oratorical" },
};

const FALLBACK: VoiceVisual = { c1: "#8e9eab", c2: "#5b86e5", mono: "?", tag: "Custom voice" };

export interface Voice {
  id: string;
  name: string;
  engine: string;
  acceptsText: boolean;
}

export interface Persona extends Voice, VoiceVisual {}

export function decorate(voice: Voice): Persona {
  const v = VISUALS[voice.id] ?? { ...FALLBACK, mono: (voice.name[0] ?? "?").toUpperCase() };
  return { ...voice, ...v };
}
