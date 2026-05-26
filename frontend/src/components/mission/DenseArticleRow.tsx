/**
 * DenseArticleRow — REDESIGN Phase E.
 *
 * One row in the Mission Control feed table. Single line, tabular,
 * scannable — time · source · title · confidence · which subagent
 * surfaced the article.
 *
 * The "subagent" column is derived client-side from the source name
 * (we don't yet ship a real `surfaced_by` column; the redesign plan
 * §5.3 has the migration queued). Confidence falls back to the
 * existing credibilityScore field; rows without one render an em-dash
 * so we never invent data.
 *
 * Test hook: data-testid="dense-article-row"
 */
import { useMemo } from "react";

interface DenseArticleRowProps {
  article: {
    id: string;
    title: string;
    source: string;
    url: string;
    publishedAt: string;
    credibilityScore?: number;
  };
}

// Heuristic — maps a source to the subagent most likely to have surfaced
// it. Replace with a real `surfaced_by` column once the backend migration
// from REDESIGN_PLAN.md §5.3 lands.
function inferSubagent(source: string): string {
  const s = (source || "").toLowerCase();
  if (s.includes("hacker") || s.includes("ycomb")) return "editor-pick";
  if (s.includes("verge") || s.includes("techcrunch") || s.includes("wired"))
    return "feed-ingest";
  if (s.includes("bloomberg") || s.includes("reuters") || s.includes("ft"))
    return "topic-cluster";
  if (s.includes("ars") || s.includes("anandtech")) return "entity-link";
  return "feed-ingest";
}

function fmtClock(iso: string): string {
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

export function DenseArticleRow({ article }: DenseArticleRowProps) {
  const subagent = useMemo(() => inferSubagent(article.source), [article.source]);
  const conf = typeof article.credibilityScore === "number"
    ? article.credibilityScore
    : null;

  return (
    <a
      data-testid="dense-article-row"
      data-slot="card"
      href={article.url}
      target="_blank"
      rel="noopener noreferrer"
      className="group grid items-baseline gap-3 py-1.5 px-3 border-b border-[var(--rule)] hover:bg-[var(--background-tint)] transition-colors text-[12px] tabular-nums"
      style={{ gridTemplateColumns: "56px 130px minmax(260px, 1fr) 48px 110px" }}
    >
      {/* Wall clock */}
      <span className="text-foreground-mute font-[var(--font-mono)] mono" data-mono>
        {fmtClock(article.publishedAt)}
      </span>

      {/* Source */}
      <span className="text-foreground-soft truncate">{article.source}</span>

      {/* Title */}
      <span
        data-slot="card-title"
        className="text-foreground group-hover:underline truncate"
        style={{ fontSize: "13px", fontWeight: 500 }}
      >
        {article.title}
      </span>

      {/* Confidence — DESIGN_REVIEW C-4. Amber was competing with the
          indigo subagent label and reading as a CTA. Default confidence
          uses foreground-soft; only a low-confidence reading (<60%)
          escalates to amber as a warning signal. */}
      <span
        className="text-right mono"
        data-mono
        style={{
          color:
            conf == null
              ? "var(--foreground-mute)"
              : conf < 60
                ? "var(--accent-warm)"
                : "var(--foreground-soft)",
        }}
      >
        {conf != null ? `${conf}%` : "—"}
      </span>

      {/* Which subagent surfaced it */}
      <span
        className="text-right mono"
        data-mono
        style={{ color: "var(--accent-signal)", fontSize: "11px" }}
      >
        {subagent}
      </span>
    </a>
  );
}
