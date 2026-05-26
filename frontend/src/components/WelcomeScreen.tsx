/**
 * WelcomeScreen — REDESIGN Phase C.
 *
 * The home page (`/`). Replaces the previous broadsheet single-screen
 * cover with the Atelier composition:
 *
 *   AtelierHero          — conversational "I read N stories overnight..."
 *                          + two CTAs + skip link.
 *   AgentDigestCard × 4  — 2×2 grid of topic clusters pulled from
 *                          /api/digest/topics. Each card has a label,
 *                          AI blurb, up to 3 headlines, and an
 *                          "Ask the desk →" footer.
 *
 * The export name and prop contract are preserved so App.tsx and the
 * Playwright suite keep working. Existing test hooks remain:
 *
 *   data-testid="welcome-screen"      — outer container (on AtelierHero)
 *   data-testid="welcome-cta-research"
 *   data-testid="welcome-cta-feed"
 *   data-testid="welcome-dismiss"
 *
 * New test hooks:
 *
 *   data-testid="atelier-hero"
 *   data-testid="atelier-digest-grid"
 *   data-testid="agent-digest-card"   (one per card)
 */
import { useEffect, useState } from "react";
import { motion, useReducedMotion } from "framer-motion";
import { API_ENDPOINTS, apiFetch } from "../config/api";
import { AtelierShell } from "./atelier/AtelierShell";
import { AtelierHero } from "./atelier/AtelierHero";
import { AgentDigestCard, type DigestTopic } from "./atelier/AgentDigestCard";

interface WelcomeScreenProps {
  onTryResearch: () => void;
  /**
   * When called without a topic, opens the feed root. When called with
   * a topic string (from an AgentDigestCard click), the host should
   * pre-filter the feed to that category. (DESIGN_REVIEW C-2.)
   */
  onBrowseFeed: (topic?: string) => void;
  onSkip: () => void;
}

/**
 * Topic-cluster payload from /api/digest/topics. The shape varies a
 * little across backend versions, so we normalize defensively. Known
 * keys observed in production:
 *   - `topic` | `label` | `name`
 *   - `summary` | `blurb` | `description`
 *   - `articles` | `headlines` | `stories` — each item has title + url + source
 */
function normalizeTopics(raw: any): DigestTopic[] {
  const arr = Array.isArray(raw?.topics)
    ? raw.topics
    : Array.isArray(raw)
      ? raw
      : Array.isArray(raw?.data)
        ? raw.data
        : [];
  return arr
    .map((t: any) => {
      const label =
        t?.topic || t?.label || t?.name || t?.category || t?.title || "";
      const blurb = t?.summary || t?.blurb || t?.description || "";
      const headlinesRaw = t?.articles || t?.headlines || t?.stories || [];
      const headlines = (Array.isArray(headlinesRaw) ? headlinesRaw : []).map(
        (h: any) => ({
          id: h?.id ?? h?._id ?? h?.url ?? h?.title,
          title: String(h?.title ?? "").trim(),
          url: h?.url || undefined,
          source: h?.source || undefined,
        })
      );
      return { label: String(label).trim(), blurb: String(blurb), headlines };
    })
    .filter((t: DigestTopic) => t.label.length > 0);
}

export function WelcomeScreen({
  onTryResearch,
  onBrowseFeed,
  onSkip,
}: WelcomeScreenProps) {
  const reduceMotion = useReducedMotion();
  const [topics, setTopics] = useState<DigestTopic[] | null>(null);
  const [topicsErrored, setTopicsErrored] = useState(false);

  // Pull topic clusters for the digest grid. Non-fatal — if the
  // endpoint is unreachable we just don't render the cards and the
  // hero stands on its own.
  useEffect(() => {
    let cancelled = false;
    (async () => {
      try {
        const data: any = await apiFetch<any>(API_ENDPOINTS.digestTopics);
        if (cancelled) return;
        const normalized = normalizeTopics(data);
        setTopics(normalized);
      } catch {
        if (!cancelled) setTopicsErrored(true);
      }
    })();
    return () => {
      cancelled = true;
    };
  }, []);

  // Hand a topic into /feed pre-filtered. DESIGN_REVIEW C-2 — the
  // App.tsx onBrowseFeed signature now accepts an optional topic and
  // seeds selectedCategories with it before switching tabs.
  const handleOpenFeed = (topic: string) => {
    onBrowseFeed(topic);
  };

  // Ask the desk: same idea — for now we route into Research; the
  // ResearchMode component will pick up a pre-filled query in a later
  // milestone (its API surface doesn't yet accept an initial prompt).
  const handleAskDesk = (_topic: string) => {
    onTryResearch();
  };

  // Render the top 4 topics. Fewer is fine; we just collapse the grid.
  const visibleTopics = (topics || []).slice(0, 4);

  return (
    <AtelierShell>
      <AtelierHero
        onTryResearch={onTryResearch}
        onBrowseFeed={onBrowseFeed}
        onSkip={onSkip}
      />

      {/* Digest grid. Only renders once we have at least one topic. */}
      {visibleTopics.length > 0 && (
        <motion.section
          data-testid="atelier-digest-grid"
          initial={reduceMotion ? false : { opacity: 0, y: 12 }}
          animate={{ opacity: 1, y: 0 }}
          transition={{
            duration: reduceMotion ? 0 : 0.4,
            delay: reduceMotion ? 0 : 0.15,
            ease: "easeOut",
          }}
          className="pb-16 px-2"
          aria-label="Topic digest"
        >
          <div className="flex items-baseline justify-between mb-4">
            <h2
              className="font-display text-foreground"
              style={{ fontSize: "20px", letterSpacing: "-0.02em" }}
            >
              What your desk surfaced
            </h2>
            <span className="text-[11px] uppercase tracking-wide text-foreground-mute">
              Topic clusters · last 24h
            </span>
          </div>
          {/* DESIGN_REVIEW S-2 — between 768 px and the md breakpoint
              cards stack vertically. The project is desktop-only
              (≥ 1280 px), so the 1-col fallback under md is intentional
              and is the right behavior for any future narrow window;
              a mobile-first pass would rebuild the grid against the
              real mobile mockups rather than re-using these tokens. */}
          <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
            {visibleTopics.map((t) => (
              <AgentDigestCard
                key={t.label}
                topic={t}
                onOpenFeed={handleOpenFeed}
                onAskDesk={handleAskDesk}
              />
            ))}
          </div>
        </motion.section>
      )}

      {/* Fallback when topics couldn't load. Quiet — doesn't compete
          with the hero. The user can still get to the feed/research
          via the hero CTAs. */}
      {topicsErrored && visibleTopics.length === 0 && (
        <div className="pb-16 px-2 text-[12px] text-foreground-mute">
          Digest clusters are warming up. Try again in a moment.
        </div>
      )}
    </AtelierShell>
  );
}
