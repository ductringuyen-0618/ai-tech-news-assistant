/**
 * ModeProvider — REDESIGN Phase B.
 *
 * Atelier vs Mission Control surface mode. Mirrors ThemeProvider:
 *
 *  - `useMode()` returns `{ mode, setMode, toggleMode }`.
 *  - `mode` is `"atelier" | "mission"`.
 *  - `setMode(m)` writes `localStorage.techpulse_mode` AND mirrors the
 *    value onto `<html data-mode="...">` so CSS variables flip without
 *    re-rendering the React tree.
 *  - On mount, the provider reads localStorage. If unset, it ASSUMES
 *    `"atelier"` because the inline bootstrap script in `index.html`
 *    already wrote `data-mode="atelier"` before React hydrated.
 *  - We do NOT write the default back to localStorage on first paint —
 *    keeping storage empty until the user explicitly toggles matches
 *    the ThemeProvider contract and keeps the Settings persistence
 *    test (which asserts fresh contexts have empty localStorage) happy.
 *
 * Mode is independent of theme — light/dark and atelier/mission compose
 * freely. Layout components read `mode` to decide which shell to render;
 * CSS reads `data-mode` to layer dense-mode token overrides.
 */
import { createContext, useContext, useEffect, useState, ReactNode } from "react";

export type Mode = "atelier" | "mission";

interface ModeContextValue {
  mode: Mode;
  setMode: (m: Mode) => void;
  toggleMode: () => void;
}

const ModeContext = createContext<ModeContextValue | null>(null);

const STORAGE_KEY = "techpulse_mode";

function readStoredMode(): Mode {
  try {
    const v = localStorage.getItem(STORAGE_KEY);
    if (v === "atelier" || v === "mission") return v;
  } catch {
    // Privacy mode / storage disabled — fall through to default.
  }
  return "atelier";
}

function applyModeAttr(mode: Mode) {
  document.documentElement.setAttribute("data-mode", mode);
}

export function ModeProvider({ children }: { children: ReactNode }) {
  const [mode, setModeState] = useState<Mode>(() => {
    if (typeof window === "undefined") return "atelier";
    return readStoredMode();
  });

  // Apply the attribute on every mode change. Defense-in-depth even
  // though the inline bootstrap should have already set it.
  useEffect(() => {
    applyModeAttr(mode);
  }, [mode]);

  const setMode = (m: Mode) => {
    setModeState(m);
    try {
      localStorage.setItem(STORAGE_KEY, m);
    } catch {
      // Best-effort persistence; ignore quota / privacy errors.
    }
  };

  const toggleMode = () => setMode(mode === "atelier" ? "mission" : "atelier");

  return (
    <ModeContext.Provider value={{ mode, setMode, toggleMode }}>
      {children}
    </ModeContext.Provider>
  );
}

export function useMode(): ModeContextValue {
  const ctx = useContext(ModeContext);
  if (!ctx) {
    throw new Error("useMode must be used inside <ModeProvider>");
  }
  return ctx;
}
