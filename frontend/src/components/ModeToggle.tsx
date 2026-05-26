/**
 * ModeToggle — REDESIGN Phase B.
 *
 * Two-pill segmented control rendered top-right of the masthead.
 * Flips between Atelier (default, calm reading) and Mission Control
 * (dense power-user workspace). The active pill carries
 * `bg-foreground text-background`; the inactive pill is muted and
 * picks up `:hover` like a real button.
 *
 * Accessibility:
 *  - Role: group (it's a pair of buttons, not a true tab list).
 *  - Each button has aria-pressed for the active state.
 *  - Title attributes explain the two modes on hover.
 *
 * Test hook:
 *  - data-testid="mode-toggle"
 *  - data-testid="mode-toggle-atelier"
 *  - data-testid="mode-toggle-mission"
 */
import { useMode } from "./ModeProvider";

export function ModeToggle() {
  const { mode, setMode } = useMode();

  return (
    <div
      data-testid="mode-toggle"
      role="group"
      aria-label="Surface mode"
      className="inline-flex items-center border border-[var(--rule)] bg-[var(--background-tint)] text-[11px] font-medium tracking-wide uppercase"
    >
      <button
        data-testid="mode-toggle-atelier"
        type="button"
        onClick={() => setMode("atelier")}
        aria-pressed={mode === "atelier"}
        title="Atelier — calm, conversational home"
        className={[
          "px-3 py-1 transition-colors",
          mode === "atelier"
            ? "bg-foreground text-background"
            : "text-foreground-soft hover:text-foreground",
        ].join(" ")}
      >
        Atelier
      </button>
      <span aria-hidden className="w-px self-stretch bg-[var(--rule)]" />
      <button
        data-testid="mode-toggle-mission"
        type="button"
        onClick={() => setMode("mission")}
        aria-pressed={mode === "mission"}
        title="Mission Control — dense, telemetry-rich workspace"
        className={[
          "px-3 py-1 transition-colors",
          mode === "mission"
            ? "bg-foreground text-background"
            : "text-foreground-soft hover:text-foreground",
        ].join(" ")}
      >
        Mission
      </button>
    </div>
  );
}
