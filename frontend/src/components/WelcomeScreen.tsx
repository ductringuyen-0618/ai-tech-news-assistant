/**
 * WelcomeScreen -- M4 single-screen broadsheet cover.
 *
 * Replaces the centered hero + 2x2 feature grid with a single-screen
 * broadsheet cover (per user decision: SINGLE SCREEN, not scroll
 * narrative). Two-column composition:
 *
 *   LEFT (cols 1-7):  vol. iii eyebrow, 96px Fraunces "TechPulse"
 *                     wordmark, 24px italic subhead, editorial-drop
 *                     body paragraph, compact I/II/III/IV feature
 *                     list, two CTAs, quiet "skip intro >" link.
 *   RIGHT (cols 8-12): LIVE WIRE pane. Fetches /api/news/?page_size=12
 *                     on mount, pipes 12 headlines in with an
 *                     80ms-per-row stagger. While loading shows
 *                     BOOTING WIRE + live-cursor; on error shows
 *                     WIRE OFFLINE with a pointer to start-dev.ps1.
 *
 * Per docs/designs/frontend-overhaul.md M4 (with section 11 user
 * override: single screen, live API feed).
 *
 * Test hooks:
 *   - data-testid="welcome-screen"
 *   - data-testid="welcome-cta-research"
 *   - data-testid="welcome-cta-feed"
 *   - data-testid="welcome-dismiss"
 */
import { useEffect, useState } from "react";
import { motion, useReducedMotion } from "framer-motion";
import { ArrowRight } from "lucide-react";
import { API_ENDPOINTS, apiFetch } from "../config/api";
import { DropCap } from "./DropCap";

interface WelcomeScreenProps {
  onTryResearch: () => void;
  onBrowseFeed: () => void;
  onSkip: () => void;
}

interface WireEntry {
  id: string;
  title: string;
  source: string;
  publishedAt: string;
  url?: string;
}

interface FeatureRow {
  num: string;
  name: string;
  blurb: string;
}

const FEATURES: FeatureRow[] = [
  {
    num: "I.",
    name: "RESEARCH",
    blurb: "Ask the agent. It decomposes, dispatches, cites.",
  },
  {
    num: "II.",
    name: "NEWS FEED",
    blurb: "Front-page broadsheet. AI-summarised, source-cited.",
  },
  {
    num: "III.",
    name: "KNOWLEDGE",
    blurb: "Entity graph. Companies, products, people, mentions.",
  },
  {
    num: "IV.",
    name: "DIGEST",
    blurb: "Daily brief. Curated headlines, trending topics.",
  },
];

export function WelcomeScreen({
  onTryResearch,
  onBrowseFeed,
  onSkip,
}: WelcomeScreenProps) {
  const reduceMotion = useReducedMotion();
  const [wire, setWire] = useState<WireEntry[] | null>(null);
  const [wireError, setWireError] = useState<string | null>(null);
  const [booted, setBooted] = useState(false);

  // Fetch the live wire once on mount. Slight delay so the BOOTING
  // animation reads as intentional even on fast networks.
  useEffect(() => {
    let cancelled = false;
    (async () => {
      try {
        await new Promise((r) => setTimeout(r, reduceMotion ? 0 : 400));
        if (cancelled) return;
        const data: any = await apiFetch<any>(
          `${API_ENDPOINTS.news}?page_size=12`
        );
        const raw: any[] = (data?.data || data?.items || []) as any[];
        const items: WireEntry[] = raw.slice(0, 12).map((a: any) => ({
          id: String(a.id ?? a._id ?? a.url ?? Math.random()),
          title: String(a.title ?? "(untitled)"),
          source: String(a.source ?? ""),
          publishedAt: String(a.published_at ?? a.publishedAt ?? ""),
          url: a.url,
        }));
        if (!cancelled) {
          setWire(items);
          setBooted(true);
        }
      } catch (err: any) {
        if (!cancelled) {
          setWireError(err?.message || "wire offline");
          setBooted(true);
        }
      }
    })();
    return () => {
      cancelled = true;
    };
  }, [reduceMotion]);

  const today = new Date()
    .toLocaleDateString("en-US", {
      weekday: "short",
      day: "numeric",
      month: "short",
      year: "numeric",
    })
    .toUpperCase()
    .replace(/,/g, "");

  const wireStatus = !booted
    ? "WIRE BOOTING"
    : wireError
      ? "WIRE OFFLINE"
      : "WIRE OPEN";

  return (
    <div
      data-testid="welcome-screen"
      className="min-h-[calc(100vh-72px)] flex flex-col px-6 py-6"
    >
      {/* Dateline header -- thin mono band across the top, mirrors
          the masthead language from M1. */}
      <div className="font-mono-tx text-[11px] uppercase-eyebrow text-foreground-soft flex items-center gap-3 border-y border-[var(--rule)] py-2 mb-8">
        <span>{"━━━ TECHPULSE"}</span>
        <span>{"━━━ WELCOME / VOL III"}</span>
        <span>{"━━━ "}{today}</span>
        <span className="flex-1 border-t border-[var(--rule)]" />
        <span className={booted && !wireError ? "text-signal" : ""}>
          {wireStatus}
        </span>
      </div>

      {/* Two-column body. */}
      <div className="grid grid-cols-12 gap-8 flex-1">
        {/* LEFT COL ----------------------------------------------- */}
        <motion.div
          initial={reduceMotion ? false : { opacity: 0, y: 8 }}
          animate={{ opacity: 1, y: 0 }}
          transition={{ duration: reduceMotion ? 0 : 0.32 }}
          className="col-span-12 lg:col-span-7 flex flex-col"
        >
          <div className="font-mono-tx text-[11px] uppercase-eyebrow text-foreground-soft mb-2">
            vol. iii &middot; special issue
          </div>
          <h1 className="font-display font-medium text-[96px] leading-[0.92] tracking-tight text-foreground mb-3">
            TechPulse
          </h1>
          <p className="font-display italic text-[24px] leading-[1.3] text-foreground-soft mb-6 max-w-xl">
            A reader&apos;s terminal for the agentic era.
          </p>
          <DropCap className="mb-6 max-w-xl">
            Reading the news is now a research problem. TechPulse aggregates
            the day&apos;s stories from TechCrunch, The Verge, Wired, Ars
            Technica and more &mdash; then hands you an agentic research
            desk that decomposes any question, dispatches subagents across
            the corpus, and synthesises a cited answer in real time.
          </DropCap>

          {/* Feature list -- compact numbered four-row, NOT a 2x2
              card grid. Single-screen means no fluff. */}
          <ul className="border-t border-[var(--rule)] mb-6">
            {FEATURES.map((f) => (
              <li
                key={f.num}
                className="border-b border-[var(--rule)] py-2 flex items-baseline gap-3"
              >
                <span className="font-mono-tx text-[11px] uppercase-eyebrow text-foreground-soft w-8 shrink-0">
                  {f.num}
                </span>
                <span className="font-display font-medium text-[16px] text-foreground w-32 shrink-0">
                  {f.name}
                </span>
                <span className="font-display italic text-[14px] text-foreground-soft flex-1">
                  {f.blurb}
                </span>
              </li>
            ))}
          </ul>

          {/* CTAs ------------------------------------------------- *
           *
           * Polish iter (design-review #15): clearer hierarchy.
           *  - Research is the marquee action: solid signal-accent
           *    fill, arrow glyph, hover flips to ink-on-paper.
           *  - Read today's feed is the secondary call: solid
           *    foreground/background block (inverted ink) so it
           *    reads as a real button, not a meta link.
           *  - Skip intro becomes a quiet tertiary text link with
           *    its own underline-on-hover affordance.
           */}
          <div className="flex items-center gap-3 mb-4">
            <button
              data-testid="welcome-cta-research"
              type="button"
              onClick={onTryResearch}
              className="font-mono-tx text-[12px] uppercase-eyebrow px-4 py-2 bg-[var(--accent-signal)] text-background hover:bg-foreground transition-colors inline-flex items-center gap-2"
            >
              [ start a research dispatch
              <ArrowRight className="w-3 h-3" />
              ]
            </button>
            <button
              data-testid="welcome-cta-feed"
              type="button"
              onClick={onBrowseFeed}
              className="font-mono-tx text-[12px] uppercase-eyebrow px-4 py-2 bg-foreground text-background hover:bg-[var(--accent-signal)] transition-colors"
            >
              [ read today&apos;s feed ]
            </button>
          </div>
          <button
            data-testid="welcome-dismiss"
            type="button"
            onClick={onSkip}
            className="font-mono-tx text-[11px] uppercase-eyebrow text-foreground-soft hover:text-signal hover:underline self-start transition-colors"
          >
            skip intro &gt;
          </button>
        </motion.div>

        {/* RIGHT COL -- LIVE WIRE --------------------------------- */}
        <motion.div
          initial={reduceMotion ? false : { opacity: 0, x: 12 }}
          animate={{ opacity: 1, x: 0 }}
          transition={{
            duration: reduceMotion ? 0 : 0.4,
            delay: reduceMotion ? 0 : 0.18,
          }}
          className="col-span-12 lg:col-span-5 flex flex-col border-l border-[var(--rule)] pl-8"
        >
          <div className="font-mono-tx text-[11px] uppercase-eyebrow text-foreground-soft mb-3 flex items-center gap-3">
            <span>{"━ LIVE WIRE"}</span>
            <span className="flex-1 border-t border-[var(--rule)]" />
            {wire && <span>{wire.length} dispatches</span>}
          </div>
          {!booted && (
            <div className="font-mono-tx text-[12px] text-foreground-soft">
              <p>
                BOOTING WIRE
                <span className="live-cursor"></span>
              </p>
            </div>
          )}
          {booted && wireError && (
            <div className="font-mono-tx text-[12px] text-foreground-soft">
              <p>WIRE OFFLINE &mdash; {wireError}</p>
              <p className="mt-2 text-foreground-soft">
                No backend? Run{" "}
                <code className="bg-[var(--background-tint)] px-1">
                  .\start-dev.ps1
                </code>{" "}
                to spin up the API.
              </p>
            </div>
          )}
          {booted && !wireError && wire && (
            <ol className="font-mono-tx text-[12px] space-y-1.5 overflow-y-auto max-h-[60vh]">
              {wire.map((item, i) => (
                <WireRow
                  key={item.id}
                  item={item}
                  idx={i}
                  reduceMotion={Boolean(reduceMotion)}
                />
              ))}
            </ol>
          )}
        </motion.div>
      </div>
    </div>
  );
}

function WireRow({
  item,
  idx,
  reduceMotion,
}: {
  item: WireEntry;
  idx: number;
  reduceMotion: boolean;
}) {
  // Stagger headlines piping in by 80ms each on mount.
  return (
    <motion.li
      initial={reduceMotion ? false : { opacity: 0, y: 4 }}
      animate={{ opacity: 1, y: 0 }}
      transition={{
        duration: reduceMotion ? 0 : 0.18,
        delay: reduceMotion ? 0 : idx * 0.08,
      }}
      className="flex gap-3 items-start"
    >
      <span className="text-foreground-soft shrink-0">
        {formatTime(item.publishedAt)}
      </span>
      <span className="text-foreground leading-[1.4]">
        <span className="text-signal mr-1">{"▸"}</span>
        {item.title}
      </span>
    </motion.li>
  );
}

function formatTime(iso: string): string {
  try {
    const d = new Date(iso);
    if (Number.isNaN(d.getTime())) return "--:--";
    return d.toLocaleTimeString("en-US", {
      hour: "2-digit",
      minute: "2-digit",
      hour12: false,
    });
  } catch {
    return "--:--";
  }
}
