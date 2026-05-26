/**
 * AgentDigestCard — REDESIGN Phase C.
 *
 * One card in the Atelier home's 2×2 grid. Each card represents a topic
 * cluster pulled from /api/digest/topics — the cluster label, an AI
 * summary blurb, and up to three headline links. Clicking the card body
 * (the topic label) routes into /feed pre-filtered to that topic; the
 * "ask the desk" footer link routes into /research with the topic as a
 * pre-filled question.
 *
 * The card itself is a calm tile — no border-bracket frames, no
 * mono-eyebrows, no decorative tick rules. Just a tinted surface, a
 * one-pixel hairline on hover, and Geist type at three sizes.
 */
import { ArrowUpRight } from "lucide-react";

export interface DigestTopic {
  label: string;
  blurb?: string;
  headlines: Array<{
    id?: string | number;
    title: string;
    url?: string;
    source?: string;
  }>;
}

interface AgentDigestCardProps {
  topic: DigestTopic;
  /** Called when the user clicks the topic label / card body. */
  onOpenFeed: (topic: string) => void;
  /** Called when the user clicks "ask the desk". */
  onAskDesk: (topic: string) => void;
}

export function AgentDigestCard({
  topic,
  onOpenFeed,
  onAskDesk,
}: AgentDigestCardProps) {
  const headlines = (topic.headlines || []).slice(0, 3);

  return (
    <article
      data-testid="agent-digest-card"
      className="group relative flex flex-col p-5 bg-[var(--background-tint)] border border-transparent hover:border-[var(--rule)] rounded-lg transition-colors"
    >
      {/* Topic label — clickable, routes into feed-with-filter. */}
      <button
        type="button"
        onClick={() => onOpenFeed(topic.label)}
        className="flex items-start justify-between gap-2 text-left"
      >
        <h3
          className="font-display text-foreground"
          style={{ fontSize: "18px", lineHeight: 1.3, letterSpacing: "-0.015em" }}
        >
          {topic.label}
        </h3>
        <ArrowUpRight
          className="w-4 h-4 text-foreground-mute opacity-0 group-hover:opacity-100 transition-opacity shrink-0 mt-1"
          aria-hidden
        />
      </button>

      {/* Optional AI blurb. */}
      {topic.blurb && (
        <p className="mt-2 text-[13px] leading-[1.55] text-foreground-soft line-clamp-2">
          {topic.blurb}
        </p>
      )}

      {/* Headline list. Each is a real anchor so middle-click + cmd-click
          open in a new tab; the card body button is decorative on top. */}
      {headlines.length > 0 && (
        <ul className="mt-3 space-y-1.5">
          {headlines.map((h, i) => (
            <li
              key={h.id ?? `${topic.label}-${i}`}
              className="text-[13px] leading-[1.45] flex gap-2 items-baseline"
            >
              <span
                className="text-foreground-mute shrink-0"
                aria-hidden
                style={{ fontSize: "10px" }}
              >
                ●
              </span>
              {h.url ? (
                <a
                  href={h.url}
                  target="_blank"
                  rel="noopener noreferrer"
                  className="text-foreground hover:text-foreground-soft hover:underline transition-colors line-clamp-2"
                >
                  {h.title}
                </a>
              ) : (
                <span className="text-foreground line-clamp-2">{h.title}</span>
              )}
            </li>
          ))}
        </ul>
      )}

      {/* Card footer — ask the desk about this topic. */}
      <div className="mt-auto pt-4 flex items-center justify-between border-t border-[var(--rule)] mt-4">
        <button
          type="button"
          onClick={() => onAskDesk(topic.label)}
          className="text-[12px] text-foreground-soft hover:text-foreground transition-colors"
        >
          Ask the desk →
        </button>
        {headlines.length > 0 && (
          <span className="text-[11px] text-foreground-mute tabular-nums uppercase tracking-wide">
            {headlines.length} {headlines.length === 1 ? "story" : "stories"}
          </span>
        )}
      </div>
    </article>
  );
}
