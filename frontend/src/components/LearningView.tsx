import { useEffect, useState } from 'react';
import { Badge } from './ui/badge';
import { Skeleton } from './ui/skeleton';
import { API_ENDPOINTS, apiFetch } from '../config/api';

/**
 * LearningView -- proposal 003, "Trending AI Agent Skills".
 *
 * A dedicated feed of AI-agent tooling/technique content (new Claude
 * Code skills, MCP servers, agent frameworks, "everything you can do
 * with X" roundups), distinct from the general News Feed. Backed by
 * `GET /api/learning/`, which serves articles the ingestion pipeline
 * tagged with the reserved "Agent Skills" category (see
 * `backend/src/services/learning_ingestion.py`).
 *
 * v1 scope, deliberately: no personalization/reactions (the main News
 * Feed already has those -- see `NewsCard`/`interestWeights`), and no
 * knowledge-graph cross-linking on category chips -- the standalone
 * knowledge-graph view was cut before this was built (see App.tsx's
 * VALID_TABS comment) and `/api/learning/` doesn't carry per-article
 * entity data, so a chip here is informational only, matching what
 * `/api/news/` already exposes.
 */

interface LearningItem {
  id: string | number;
  title: string;
  source: string;
  url: string;
  publishedAt: string;
  imageUrl: string;
  category: string[];
  summary: string;
}

interface RawArticle {
  id: string | number;
  title: string;
  source: string;
  url: string;
  published_at?: string;
  image_url?: string | null;
  categories?: string[] | null;
  summary?: string | null;
  content?: string | null;
}

function mapItem(a: RawArticle): LearningItem {
  const body = (a.summary || a.content || '').toString().trim();
  const summary =
    body.length > 240 ? body.slice(0, 240).trimEnd() + '...' : body;
  return {
    id: a.id,
    title: a.title,
    source: a.source,
    url: a.url,
    publishedAt: a.published_at || '',
    imageUrl: a.image_url || '',
    category: a.categories || [],
    summary,
  };
}

function timeAgo(dateString: string): string {
  if (!dateString) return '';
  const date = new Date(dateString);
  if (Number.isNaN(date.getTime())) return '';
  const hours = Math.floor((Date.now() - date.getTime()) / (1000 * 60 * 60));
  if (hours < 1) return 'Just now';
  if (hours < 24) return `${hours}h ago`;
  return `${Math.floor(hours / 24)}d ago`;
}

function hostname(url: string): string {
  try {
    return new URL(url).hostname.replace(/^www\./, '');
  } catch {
    return 'source';
  }
}

function LearningCard({ item }: { item: LearningItem }) {
  return (
    <article
      data-testid="learning-card"
      className="p-4 bg-[var(--background-tint)] border border-transparent hover:border-[var(--rule)] rounded-lg transition-colors"
    >
      <div className="font-mono-tx text-[11px] uppercase-eyebrow flex items-center gap-2 mb-2 text-gray-500">
        <span className="uppercase-eyebrow">{item.source}</span>
        {item.publishedAt && (
          <>
            <span className="text-foreground-soft">.</span>
            <span className="text-foreground-soft">
              {timeAgo(item.publishedAt)}
            </span>
          </>
        )}
      </div>

      <h3
        data-slot="card-title"
        style={{
          overflowWrap: 'anywhere',
          wordBreak: 'break-word',
          fontSize: '17px',
          lineHeight: 1.3,
          letterSpacing: '-0.02em',
          fontWeight: 600,
        }}
        className="font-display text-foreground mb-2"
      >
        {item.title}
      </h3>

      {item.summary ? (
        <p
          data-testid="learning-card-summary"
          style={{ overflowWrap: 'anywhere', wordBreak: 'break-word' }}
          className="text-[14px] leading-[1.55] text-foreground-soft mb-3"
        >
          {item.summary}
        </p>
      ) : (
        <p className="text-[14px] italic text-foreground-mute mb-3">
          Tap "read at" for the full story.
        </p>
      )}

      <div className="pt-2 border-t border-[var(--rule)] flex items-center justify-between gap-2 text-[11px]">
        <div className="flex gap-1.5 flex-wrap items-center">
          {item.category.map(c => (
            <Badge key={c} variant="outline" className="font-mono-tx">
              {c}
            </Badge>
          ))}
        </div>
        <a
          data-testid="learning-card-read-more"
          href={item.url}
          target="_blank"
          rel="noopener noreferrer"
          className="inline-flex items-center gap-1 font-medium hover:underline shrink-0"
          style={{ color: 'var(--accent-signal)' }}
        >
          read at {hostname(item.url)} &rarr;
        </a>
      </div>
    </article>
  );
}

export function LearningView() {
  const [items, setItems] = useState<LearningItem[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState(false);

  useEffect(() => {
    let cancelled = false;

    const load = async () => {
      try {
        setLoading(true);
        setError(false);
        const data = await apiFetch<{ data?: RawArticle[] }>(
          `${API_ENDPOINTS.learning}?page=1&page_size=20`
        );
        if (cancelled) return;
        const raw = Array.isArray(data?.data) ? data.data : [];
        setItems(raw.map(mapItem));
      } catch (err) {
        if (!cancelled) {
          console.error('LearningView: failed to load learning feed', err);
          setError(true);
          setItems([]);
        }
      } finally {
        if (!cancelled) setLoading(false);
      }
    };

    load();
    return () => {
      cancelled = true;
    };
  }, []);

  return (
    <div data-testid="learning-view" className="max-w-3xl mx-auto">
      <div className="mb-6">
        <h1 className="font-display text-2xl text-foreground mb-1">Learning</h1>
        <p className="text-[14px] text-foreground-soft">
          Trending AI agent skills, techniques, and setups worth adding to your
          own workflow this week.
        </p>
      </div>

      {loading && (
        <div className="space-y-4" data-testid="learning-loading">
          {Array.from({ length: 3 }).map((_, i) => (
            <div
              key={i}
              className="p-4 border border-[var(--rule)] rounded-lg space-y-3"
            >
              <Skeleton className="h-3 w-24" />
              <Skeleton className="h-5 w-full" />
              <Skeleton className="h-4 w-full" />
              <Skeleton className="h-4 w-2/3" />
            </div>
          ))}
        </div>
      )}

      {!loading && error && (
        <div
          data-testid="learning-error"
          className="p-6 border border-[var(--rule)] rounded-lg text-center text-foreground-soft text-[14px]"
        >
          Couldn't load the Learning feed right now. Try again in a moment.
        </div>
      )}

      {!loading && !error && items.length === 0 && (
        <div
          data-testid="learning-empty"
          className="p-6 border border-[var(--rule)] rounded-lg text-center text-foreground-soft text-[14px]"
        >
          Nothing here yet -- the Learning feed updates as new agent tooling and
          technique content comes in. Check back soon.
        </div>
      )}

      {!loading && !error && items.length > 0 && (
        <div className="space-y-3">
          {items.map(item => (
            <LearningCard key={item.id} item={item} />
          ))}
        </div>
      )}
    </div>
  );
}

export default LearningView;
