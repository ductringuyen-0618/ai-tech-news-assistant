import { useEffect, useState } from 'react';
import { Skeleton } from './ui/skeleton';
import { API_ENDPOINTS, apiFetch } from '../config/api';

/**
 * TrendingRail -- horizontal ticker tape of the top entities by mention
 * count this week.
 *
 * M2 rewrite: drops the rounded pill row in favour of a mono ticker tape
 * with a leading "> trending" label, dot separators implied by gap, and
 * a signal-color count flag (`|N`) on each entity. The whole rail sits
 * inside a hairline-ruled band (`border-y border-[var(--rule)]`) and uses
 * `whitespace-nowrap` so entries never wrap.
 *
 * Test-contract preservation:
 *   - data-testid="news-feed-trending-rail"      (root)
 *   - data-testid="news-feed-trending-chip"      (per-entity buttons)
 *   - data-category="<entity name>"              (per-button data attr)
 *   - data-entity-type="<entity type>"           (per-button data attr)
 *
 * Coverage diversity: once the trending list loads, each entity's source
 * count is fetched from the existing entity-detail endpoint (which already
 * returns each mentioning article's `source`) and rendered as a "· Nsrc"
 * suffix -- a cheap approximation of Ground News's "coverage diversity"
 * chip using data the backend already exposes, no schema change needed.
 */

interface TrendingRailProps {
  /** Currently-selected entity ids. A chip whose id matches an entry in
   *  this list renders in its "selected" variant. */
  selectedEntityIds: number[];
  /** Fired when a chip is clicked. Passes the full {id, name} so the
   *  caller can drive the real backend entity_id filter, not just a
   *  display name. */
  onSelectEntity: (entity: { id: number; name: string }) => void;
  /** Maximum number of chips to render (default 12 -- longer ticker reads
   *  more like a wire feed than a 5-chip toolbar). */
  limit?: number;
}

interface TrendingEntity {
  id: number;
  name: string;
  type: string;
  mention_count: number;
  score: number;
}

export function TrendingRail({
  selectedEntityIds,
  onSelectEntity,
  limit = 12,
}: TrendingRailProps) {
  const [trending, setTrending] = useState<TrendingEntity[]>([]);
  const [loading, setLoading] = useState(true);
  const [sourceCounts, setSourceCounts] = useState<Record<number, number>>({});

  useEffect(() => {
    let cancelled = false;

    const loadTrending = async () => {
      try {
        setLoading(true);
        const params = new URLSearchParams({
          days: '7',
          limit: String(limit),
        });
        const data = await apiFetch<any>(
          `${API_ENDPOINTS.knowledgeGraphTrending}?${params}`
        );
        if (cancelled) return;
        const entities: TrendingEntity[] = Array.isArray(data?.entities)
          ? data.entities
          : [];
        const sorted = [...entities].sort(
          (a, b) => (b.mention_count || 0) - (a.mention_count || 0)
        );
        setTrending(sorted);
      } catch (err) {
        if (!cancelled) {
          console.error('TrendingRail: failed to load trending entities', err);
          setTrending([]);
        }
      } finally {
        if (!cancelled) {
          setLoading(false);
        }
      }
    };

    loadTrending();
    return () => {
      cancelled = true;
    };
  }, [limit]);

  // Progressively enhance each chip with a distinct-source count, pulled
  // from the entity-detail endpoint's `articles[].source` list (already
  // fetched by the KG side drawer elsewhere -- no new backend field).
  useEffect(() => {
    if (trending.length === 0) return;
    let cancelled = false;

    const loadSourceCounts = async () => {
      const results = await Promise.allSettled(
        trending.map(t =>
          apiFetch<{ articles?: { source?: string }[] }>(
            `/api/knowledge-graph/entity/${t.id}`
          ).then(detail => {
            const sources = new Set(
              (detail.articles || [])
                .map(a => a.source)
                .filter((s): s is string => Boolean(s))
            );
            return [t.id, sources.size] as const;
          })
        )
      );
      if (cancelled) return;
      setSourceCounts(prev => {
        const next = { ...prev };
        for (const r of results) {
          if (r.status === 'fulfilled') {
            const [id, count] = r.value;
            next[id] = count;
          }
        }
        return next;
      });
    };

    loadSourceCounts();
    return () => {
      cancelled = true;
    };
  }, [trending]);

  if (loading) {
    return (
      <div
        data-testid="news-feed-trending-rail"
        className="relative border-y border-[var(--rule)] py-2 overflow-hidden"
      >
        <div className="flex items-center gap-4 font-mono-tx text-[11px] uppercase-eyebrow whitespace-nowrap">
          <span className="text-foreground-soft shrink-0">
            &#9658; trending
          </span>
          {Array.from({ length: 4 }).map((_, i) => (
            <Skeleton key={i} className="h-4 w-20" />
          ))}
        </div>
      </div>
    );
  }

  if (trending.length === 0) {
    return null;
  }

  return (
    <div
      data-testid="news-feed-trending-rail"
      className="relative border-y border-[var(--rule)] py-2 overflow-hidden"
    >
      <div className="flex items-center gap-4 font-mono-tx text-[11px] uppercase-eyebrow whitespace-nowrap">
        <span className="text-foreground-soft shrink-0">&#9658; trending</span>
        {trending.map(t => {
          const isActive = selectedEntityIds.includes(t.id);
          const sourceCount = sourceCounts[t.id];
          return (
            <button
              key={`${t.id}-${t.name}`}
              type="button"
              data-testid="news-feed-trending-chip"
              data-category={t.name}
              data-entity-type={t.type}
              data-source-count={sourceCount ?? undefined}
              onClick={() => onSelectEntity({ id: t.id, name: t.name })}
              title={
                sourceCount != null
                  ? `Covered by ${sourceCount} source${sourceCount === 1 ? '' : 's'}`
                  : undefined
              }
              className={[
                'shrink-0 px-1.5 py-0.5 border transition-colors',
                isActive
                  ? 'text-signal border-[var(--rule)]'
                  : 'text-foreground-soft border-transparent hover:border-[var(--rule)] hover:text-foreground',
              ].join(' ')}
            >
              {t.name.toUpperCase()}{' '}
              <span className="text-signal">&#9612;{t.mention_count}</span>
              {sourceCount != null && sourceCount > 1 && (
                <span className="text-foreground-soft">
                  {' '}
                  &middot; {sourceCount}src
                </span>
              )}
            </button>
          );
        })}
      </div>
    </div>
  );
}
