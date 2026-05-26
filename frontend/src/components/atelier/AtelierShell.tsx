/**
 * AtelierShell — REDESIGN Phase C.
 *
 * Thin layout wrapper for Atelier surfaces. Centers content in a
 * comfortable reading column (max-width 1120 px), gives the page
 * generous top breathing room, and lets children control their own
 * vertical rhythm. The shell is intentionally minimal — it does NOT
 * render the masthead or the sidebar; those live in App.tsx so they
 * persist across mode toggles without re-mounting.
 *
 * Use this around any Atelier-mode page content (home, feed, research,
 * digest). It does not apply when mode === "mission" — Mission Control
 * uses its own dense 3-column shell.
 */
import { ReactNode } from "react";

interface AtelierShellProps {
  children: ReactNode;
  className?: string;
}

export function AtelierShell({ children, className = "" }: AtelierShellProps) {
  return (
    <div
      data-testid="atelier-shell"
      className={["mx-auto w-full max-w-[1120px]", className].join(" ")}
    >
      {children}
    </div>
  );
}
