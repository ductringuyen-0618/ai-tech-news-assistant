/**
 * AtelierHero — REDESIGN Phase C.
 *
 * The new home-page hero. Replaces the broadsheet WelcomeScreen cover.
 * Frames the AI as a colleague who did work overnight rather than a
 * tool waiting for input:
 *
 *   I read 163 stories overnight.
 *   Here's what your desk thinks matters today.
 *
 *   [ Read the brief → ]   [ Research a topic ]
 *
 * Live story count comes from /api/news/stats (recent_articles), with
 * graceful fallback to total_articles or a static phrase if the stats
 * endpoint is unreachable. The number is the only signal-colored text;
 * everything else is ink-on-paper to keep the hero quiet and confident.
 *
 * Test hooks (preserved from WelcomeScreen contract):
 *  - data-testid="welcome-screen"          — outer container
 *  - data-testid="welcome-cta-research"    — primary CTA
 *  - data-testid="welcome-cta-feed"        — secondary CTA
 *  - data-testid="welcome-dismiss"         — quiet skip link
 *  - data-testid="atelier-hero"            — new, for redesign specs
 */
import { useEffect, useMemo, useState } from "react";
import { motion, useReducedMotion } from "framer-motion";
import { ArrowRight, Sparkles } from "lucide-react";
import { API_ENDPOINTS, apiFetch } from "../../config/api";

interface AtelierHeroProps {
  onTryResearch: () => void;
  onBrowseFeed: () => void;
  onSkip: () => void;
}

export function AtelierHero({
  onTryResearch,
  onBrowseFeed,
  onSkip,
}: AtelierHeroProps) {
  const reduceMotion = useReducedMotion();
  const [storyCount, setStoryCount] = useState<number | null>(null);

  // Pull the recent-article count once. Failure is non-fatal — we just
  // render the hero without the integer.
  useEffect(() => {
    let cancelled = false;
    (async () => {
      try {
        const envelope: any = await apiFetch<any>(API_ENDPOINTS.newsStats);
        const data = envelope?.data ?? envelope;
        const recent = Number(data?.recent_articles ?? 0);
        const total = Number(data?.total_articles ?? 0);
        const n = recent > 0 ? recent : total;
        if (!cancelled && n > 0) setStoryCount(n);
      } catch {
        // Hero degrades gracefully — no toast, no error UI.
      }
    })();
    return () => {
      cancelled = true;
    };
  }, []);

  // Memoize so the eyebrow doesn't flip mid-session if a re-render happens
  // to straddle a clock hour. Computed once per mount.
  const greeting = useMemo(
    () => greetingForHour(new Date().getHours()),
    []
  );

  return (
    <section
      data-testid="welcome-screen"
      className="pt-16 pb-12 px-2"
    >
      <motion.div
        data-testid="atelier-hero"
        initial={reduceMotion ? false : { opacity: 0, y: 10 }}
        animate={{ opacity: 1, y: 0 }}
        transition={{ duration: reduceMotion ? 0 : 0.4, ease: "easeOut" }}
      >
        {/* Quiet eyebrow — greeting + a single live-status dot. */}
        <div className="flex items-center gap-2 mb-6 text-[12px] text-foreground-mute uppercase tracking-wide">
          <Sparkles
            className="w-3.5 h-3.5"
            style={{ color: "var(--accent-signal)" }}
            aria-hidden
          />
          <span>{greeting}, here's your desk.</span>
        </div>

        {/* Hero copy — Geist 44 px, near-black, generous leading. The
            integer in the first line is the only signal-colored word so
            the eye lands on "how much work the AI did overnight".

            NOTE: this is rendered as <h2> on purpose. The masthead in
            App.tsx already owns the page's <h1 aria-label="TechPulse AI">
            so the e2e suite's strict `getByRole("heading", { name: /TechPulse AI/i })`
            locators keep resolving to a single element. The hero just
            speaks; the document outline already has its h1. */}
        <h2
          className="font-display text-foreground"
          style={{ fontSize: "44px", lineHeight: 1.1, letterSpacing: "-0.025em" }}
        >
          I read{" "}
          {storyCount !== null ? (
            <button
              type="button"
              onClick={onBrowseFeed}
              data-testid="atelier-hero-count"
              aria-label={`Open today's brief — ${storyCount.toLocaleString()} stories scanned`}
              className="tabular-nums inline-baseline font-display hover:underline decoration-2 underline-offset-4 transition-all"
              style={{ color: "var(--accent-signal)", background: "transparent", padding: 0, border: 0, font: "inherit", cursor: "pointer" }}
            >
              {storyCount.toLocaleString()} {storyCount === 1 ? "story" : "stories"}
            </button>
          ) : (
            <span style={{ color: "var(--accent-signal)" }} className="tabular-nums">
              every story
            </span>
          )}{" "}
          overnight.
          <br />
          <span className="text-foreground-soft">
            Here&apos;s what your desk thinks matters today.
          </span>
        </h2>

        {/* CTAs — primary is a solid signal-tinted pill, secondary is
            an outlined ghost. No mono-eyebrow, no [ brackets ]. */}
        <div className="flex flex-wrap items-center gap-3 mt-8">
          <button
            data-testid="welcome-cta-research"
            type="button"
            onClick={onTryResearch}
            className="inline-flex items-center gap-2 px-5 py-2.5 text-[14px] font-medium text-background bg-foreground hover:opacity-90 transition-opacity rounded-md"
          >
            Research a topic
            <ArrowRight className="w-4 h-4" />
          </button>
          <button
            data-testid="welcome-cta-feed"
            type="button"
            onClick={onBrowseFeed}
            className="inline-flex items-center gap-2 px-5 py-2.5 text-[14px] font-medium text-foreground border border-[var(--rule-strong)] hover:bg-[var(--background-tint)] transition-colors rounded-md"
          >
            Read today&apos;s brief
          </button>
          <button
            data-testid="welcome-dismiss"
            type="button"
            onClick={onSkip}
            className="ml-1 text-[13px] text-foreground-mute hover:text-foreground hover:underline transition-colors"
          >
            skip intro
          </button>
        </div>
      </motion.div>
    </section>
  );
}

function greetingForHour(h: number): string {
  if (h < 5) return "Late night";
  if (h < 12) return "Good morning";
  if (h < 17) return "Good afternoon";
  if (h < 21) return "Good evening";
  return "Late night";
}
