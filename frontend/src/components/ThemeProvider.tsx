/**
 * ThemeProvider — Mission 3 / Milestone 1.
 *
 * Custom dark/light theme context using the Tailwind class strategy.
 *
 * Contract:
 *  - `useTheme()` returns `{ theme, setTheme, toggleTheme }`
 *  - `theme` is `"dark" | "light"`.
 *  - `setTheme(t)` writes `localStorage.techpulse-theme` AND toggles
 *    `<html class="dark">`.
 *  - On mount, the provider reads localStorage. If unset, it ASSUMES
 *    `"dark"` because the inline bootstrap script in `index.html` already
 *    added `<html class="dark">` before React hydration. We do NOT write
 *    the default back to localStorage here — keeping storage empty until
 *    the user explicitly toggles preserves the existing Settings
 *    persistence test (which asserts a fresh browser context has empty
 *    localStorage on first paint).
 */
import {
  createContext,
  useContext,
  useEffect,
  useState,
  ReactNode,
} from 'react';

export type Theme = 'dark' | 'light';

interface ThemeContextValue {
  theme: Theme;
  setTheme: (t: Theme) => void;
  toggleTheme: () => void;
}

const ThemeContext = createContext<ThemeContextValue | null>(null);

const STORAGE_KEY = 'techpulse-theme';

function readStoredTheme(): Theme {
  try {
    const v = localStorage.getItem(STORAGE_KEY);
    if (v === 'light' || v === 'dark') return v;
  } catch {
    // Privacy mode or storage disabled — fall through to default.
  }
  return 'dark';
}

function applyThemeClass(theme: Theme) {
  const html = document.documentElement;
  if (theme === 'dark') {
    html.classList.add('dark');
  } else {
    html.classList.remove('dark');
  }
}

export function ThemeProvider({ children }: { children: ReactNode }) {
  // Initial state: read whatever the inline bootstrap script already wrote
  // (and what localStorage says). On the server / SSR there's no document;
  // we guard with typeof checks for safety even though Vite is SPA-only.
  const [theme, setThemeState] = useState<Theme>(() => {
    if (typeof window === 'undefined') return 'dark';
    return readStoredTheme();
  });

  // Apply the class on every theme change. We also re-run on mount in
  // case React's initial state diverged from what the bootstrap script
  // applied (it shouldn't, but defense-in-depth).
  useEffect(() => {
    applyThemeClass(theme);
  }, [theme]);

  const setTheme = (t: Theme) => {
    setThemeState(t);
    try {
      localStorage.setItem(STORAGE_KEY, t);
    } catch {
      // Best-effort persistence; ignore quota / privacy errors.
    }
  };

  const toggleTheme = () => setTheme(theme === 'dark' ? 'light' : 'dark');

  return (
    <ThemeContext.Provider value={{ theme, setTheme, toggleTheme }}>
      {children}
    </ThemeContext.Provider>
  );
}

export function useTheme(): ThemeContextValue {
  const ctx = useContext(ThemeContext);
  if (!ctx) {
    throw new Error('useTheme must be used inside <ThemeProvider>');
  }
  return ctx;
}
