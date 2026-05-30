import { create } from "zustand";

export type LLMMode = "mock" | "fake" | "cached" | "live";

interface ModeState {
  selectedMode: LLMMode;
  setMode: (mode: LLMMode) => void;
}

/**
 * Single source of truth for the user-selected LLM mode.
 * - Initial value is "mock"; on app mount we call /api/health and overwrite
 *   with the backend's env-var default (whatever LLM_MODE was set to).
 * - Every API call reads this via getState() to attach the X-LLM-Mode header.
 * - Not persisted across page refreshes (intentional — keeps dev sessions
 *   predictable; refresh resets to the backend default).
 */
export const useModeStore = create<ModeState>((set) => ({
  selectedMode: "mock",
  setMode: (mode) => set({ selectedMode: mode }),
}));
