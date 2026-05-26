/**
 * MissionShell — REDESIGN Phase E.
 *
 * 3-column dense layout for Mission Control mode:
 *
 *   ┌──────────────┬────────────────────────────────┬──────────────────┐
 *   │   (page)     │   children (article rows)      │  AgentTelemetry  │
 *   └──────────────┴────────────────────────────────┴──────────────────┘
 *
 * The first column (Sidebar) is rendered by App.tsx outside the shell —
 * MissionShell only owns columns 2 and 3. Column 2 is the feed itself
 * (passed in as children); column 3 is the live agent telemetry rail.
 *
 * Tinted background, terminal-style 12px base type, tabular numerics —
 * the visual cues that say "this is a workspace, not a reading view".
 */
import { ReactNode } from "react";
import { AgentTelemetry } from "./AgentTelemetry";

interface MissionShellProps {
  children: ReactNode;
  /** Optional heading shown above the feed (e.g. "Newsfeed · 47 stories"). */
  heading?: ReactNode;
}

export function MissionShell({ children, heading }: MissionShellProps) {
  return (
    <div
      data-testid="mission-shell"
      className="flex w-full min-h-[calc(100vh-130px)]"
      style={{ fontSize: "12px" }}
    >
      <section className="flex-1 min-w-0 flex flex-col">
        {heading && (
          <header className="px-3 py-2 border-b border-[var(--rule)] flex items-center justify-between text-[11px] uppercase tracking-wide text-foreground-mute">
            {heading}
          </header>
        )}
        <div className="flex-1 min-h-0 overflow-y-auto">{children}</div>
      </section>
      <AgentTelemetry />
    </div>
  );
}
