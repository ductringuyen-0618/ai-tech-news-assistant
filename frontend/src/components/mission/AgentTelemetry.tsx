/**
 * AgentTelemetry — REDESIGN Phase E.
 *
 * The right rail of Mission Control. Shows:
 *  - A pulsing "N agents live" banner that listens to
 *    `techpulse:research-stream` and `techpulse:agent-event`
 *    CustomEvents on window.
 *  - A scrolling list of recent agent ticks (last 8).
 *  - A summary block — "last cycle: 163 stories scanned, 47 surfaced".
 *
 * The component is deliberately decoupled from the rest of the app via
 * window events. ResearchMode already dispatches `research-stream`;
 * future ingestion jobs can dispatch `agent-event` without needing a
 * prop drill or context.
 *
 * Test hook: data-testid="agent-telemetry"
 */
import { useEffect, useState } from "react";
import { motion, useReducedMotion, AnimatePresence } from "framer-motion";

interface AgentEvent {
  id: string;
  ts: number;
  label: string;
  kind: "research" | "ingest" | "entity" | "digest";
}

const KIND_STYLE: Record<AgentEvent["kind"], { color: string; glyph: string }> = {
  research: { color: "var(--accent-signal)", glyph: "▮" },
  ingest:   { color: "var(--accent-warm)",   glyph: "▮" },
  entity:   { color: "var(--accent-soft)",   glyph: "▮" },
  digest:   { color: "var(--foreground-soft)", glyph: "▮" },
};

export function AgentTelemetry() {
  const reduceMotion = useReducedMotion();
  const [events, setEvents] = useState<AgentEvent[]>([]);
  const [liveCount, setLiveCount] = useState(0);

  useEffect(() => {
    const onResearch = (e: Event) => {
      const ev = e as CustomEvent<{ active: boolean }>;
      const active = Boolean(ev.detail?.active);
      setLiveCount((n) => Math.max(0, active ? n + 1 : n - 1));
      if (active) {
        pushEvent({
          id: `r-${Date.now()}`,
          ts: Date.now(),
          label: "research dispatch opened",
          kind: "research",
        });
      }
    };
    const onAgent = (e: Event) => {
      const ev = e as CustomEvent<Partial<AgentEvent> & { label?: string; kind?: AgentEvent["kind"] }>;
      const label = ev.detail?.label;
      const kind = ev.detail?.kind || "ingest";
      if (!label) return;
      pushEvent({
        id: `a-${Date.now()}-${Math.random().toString(36).slice(2, 7)}`,
        ts: Date.now(),
        label,
        kind,
      });
    };
    const pushEvent = (next: AgentEvent) => {
      setEvents((prev) => [next, ...prev].slice(0, 8));
    };

    window.addEventListener("techpulse:research-stream", onResearch as EventListener);
    window.addEventListener("techpulse:agent-event", onAgent as EventListener);
    return () => {
      window.removeEventListener("techpulse:research-stream", onResearch as EventListener);
      window.removeEventListener("techpulse:agent-event", onAgent as EventListener);
    };
  }, []);

  return (
    <aside
      data-testid="agent-telemetry"
      className="flex flex-col gap-4 p-4 border-l border-[var(--rule)] bg-[var(--background-tint)] min-w-[240px] max-w-[280px] text-[11px]"
      aria-label="Agent telemetry"
    >
      {/* Live banner */}
      <div className="flex items-center gap-2">
        <span
          aria-hidden
          className="inline-block w-2 h-2 rounded-full"
          style={{
            background: liveCount > 0 ? "var(--accent-signal)" : "var(--foreground-mute)",
            animation:
              liveCount > 0 && !reduceMotion ? "tp-pulse 2s ease-in-out infinite" : undefined,
          }}
        />
        <span className="text-foreground font-medium uppercase tracking-wide">
          {liveCount > 0 ? `${liveCount} agent${liveCount > 1 ? "s" : ""} live` : "idle"}
        </span>
      </div>

      {/* Event stream — only mounted once an event has fired. The
          `techpulse:agent-event` channel isn't dispatched by the
          ingestion job yet (DESIGN_REVIEW S-5 / S-6), so showing
          "no events yet" on a cold tab read as broken. We hide the
          block entirely until the first event arrives. The aria-live
          container survives so screen readers still announce the
          first tick the moment it lands. */}
      <div className="flex flex-col gap-1.5" aria-live="polite">
        {events.length > 0 && (
          <>
            <span className="text-foreground-mute uppercase tracking-wide">Recent ticks</span>
            <ul className="flex flex-col gap-1 mono" data-mono>
              <AnimatePresence initial={false}>
                {events.map((ev) => {
              const style = KIND_STYLE[ev.kind];
              return (
                <motion.li
                  key={ev.id}
                  initial={reduceMotion ? false : { opacity: 0, x: 8 }}
                  animate={{ opacity: 1, x: 0 }}
                  exit={reduceMotion ? undefined : { opacity: 0 }}
                  transition={{ duration: reduceMotion ? 0 : 0.18 }}
                  className="flex items-center gap-2 text-foreground"
                >
                  <span aria-hidden style={{ color: style.color }}>{style.glyph}</span>
                  <span className="truncate">{ev.label}</span>
                </motion.li>
              );
            })}
              </AnimatePresence>
            </ul>
          </>
        )}
      </div>

      {/* Cycle summary — static-ish for now. Real numbers can flow in
          from /api/news/stats once the agent-event channel is wired
          to the ingestion job. */}
      <div className="mt-auto pt-3 border-t border-[var(--rule)] text-foreground-soft">
        <span className="text-foreground-mute uppercase tracking-wide block mb-1">Last cycle</span>
        <span className="text-foreground mono" data-mono>scan → surface → cluster</span>
      </div>

      <style>{`
        @keyframes tp-pulse {
          0%, 100% { opacity: 1; transform: scale(1); }
          50% { opacity: 0.55; transform: scale(1.4); }
        }
      `}</style>
    </aside>
  );
}
