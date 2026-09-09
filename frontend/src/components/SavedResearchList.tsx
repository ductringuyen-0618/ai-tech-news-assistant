import { useEffect, useState } from 'react';
import { toast } from 'sonner';
import { MarkdownReport } from './MarkdownReport';
import { API_ENDPOINTS, apiFetch, API_BASE_URL } from '../config/api';
import { Loader2, AlertCircle } from 'lucide-react';

/**
 * SavedResearchList -- M5 broadsheet-row restyle.
 *
 * Each saved report now renders as a single broadsheet line:
 *
 *   ▸ FILED — TUE 12 MAY 14:08
 *   [ Fraunces 22px question title ]
 *   283 lines · 9 sources · saved 2h ago        [ × delete ]
 *
 * The Card chrome is dropped; rows are <li> elements separated
 * by hairline `border-t border-[var(--rule)]`. Click the title
 * to open the detail view; the right-side `[ × ]` deletes.
 *
 * The detail view header reuses the same FILED-eyebrow + Fraunces
 * title language; the body is unchanged (still <MarkdownReport>,
 * already typography-passed in M3b).
 *
 * Test contracts preserved (verified via
 * `grep -nE "data-testid=|getByText" frontend/e2e/saved-research.spec.ts`):
 *   - data-testid="saved-research-list"
 *   - data-testid="saved-research-item"
 *   - data-testid="saved-research-delete-btn"
 *   - data-testid="saved-research-empty"
 *   - data-testid="saved-research-detail"
 *   - data-testid="saved-research-back-btn"
 *   - visible text "No saved research yet"
 *   - each saved-research-item still has a <button> as its first
 *     child (saved-research.spec.ts:222 clicks
 *     `items.first().locator("button").first()` to open detail).
 *   - detail view renders <MarkdownReport>, which produces the
 *     "Executive Summary" and "Sources Used" headings the spec
 *     asserts on (saved-research.spec.ts:226-227).
 */

interface SavedListRow {
  id: number;
  question: string;
  created_at: string;
}

interface SavedFull {
  id: number;
  question: string;
  report_md: string;
  sources: Array<Record<string, unknown>>;
  created_at: string;
}

// ---------------------------------------------------------------------- //
//  Helpers
// ---------------------------------------------------------------------- //

function normalizeIso(iso: string): string {
  return /Z|[+-]\d{2}:?\d{2}$/.test(iso)
    ? iso
    : iso.includes('T')
      ? `${iso}Z`
      : `${iso.replace(' ', 'T')}Z`;
}

function formatRelativeTime(iso: string): string {
  const then = Date.parse(normalizeIso(iso));
  if (Number.isNaN(then)) return iso;
  const now = Date.now();
  const delta = Math.max(0, now - then);
  const sec = Math.round(delta / 1000);
  if (sec < 60) return 'just now';
  const min = Math.round(sec / 60);
  if (min < 60) return `${min}m ago`;
  const hr = Math.round(min / 60);
  if (hr < 24) return `${hr}h ago`;
  const day = Math.round(hr / 24);
  if (day < 30) return `${day}d ago`;
  const mon = Math.round(day / 30);
  if (mon < 12) return `${mon}mo ago`;
  const yr = Math.round(mon / 12);
  return `${yr}y ago`;
}

/** Format a saved-at timestamp as a mono dateline:
 *  `TUE 12 MAY 14:08`. Falls back to the raw string if the
 *  date can't be parsed. */
function formatDateline(iso: string): string {
  const then = Date.parse(normalizeIso(iso));
  if (Number.isNaN(then)) return iso;
  const d = new Date(then);
  const wd = d.toLocaleDateString('en-US', { weekday: 'short' }).toUpperCase();
  const day = d.toLocaleDateString('en-US', { day: '2-digit' });
  const mon = d.toLocaleDateString('en-US', { month: 'short' }).toUpperCase();
  const time = d.toLocaleTimeString('en-US', {
    hour: '2-digit',
    minute: '2-digit',
    hour12: false,
  });
  return `${wd} ${day} ${mon} ${time}`;
}

/** Best-effort line count for the saved markdown -- used in the
 *  row meta strip. */
function lineCountOf(md: string): number {
  if (!md) return 0;
  return md.split(/\r?\n/).filter(l => l.trim().length > 0).length;
}

// ---------------------------------------------------------------------- //
//  Component
// ---------------------------------------------------------------------- //

interface SavedResearchListProps {
  /** Refresh nonce — bump to force a re-fetch (e.g. after save). */
  refreshKey?: number;
}

export function SavedResearchList({ refreshKey = 0 }: SavedResearchListProps) {
  const [rows, setRows] = useState<SavedListRow[] | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [detailId, setDetailId] = useState<number | null>(null);
  const [detail, setDetail] = useState<SavedFull | null>(null);
  const [detailLoading, setDetailLoading] = useState(false);
  const [detailError, setDetailError] = useState<string | null>(null);

  // -------------------------------------------------------------------- //
  //  List fetch
  // -------------------------------------------------------------------- //

  async function fetchList() {
    setLoading(true);
    setError(null);
    try {
      const data = await apiFetch<SavedListRow[]>(API_ENDPOINTS.savedResearch);
      setRows(Array.isArray(data) ? data : []);
    } catch (err) {
      // eslint-disable-next-line no-console
      console.warn('SavedResearchList: list fetch failed', err);
      setError((err as Error).message || 'Failed to load saved research');
      setRows(null);
    } finally {
      setLoading(false);
    }
  }

  useEffect(() => {
    void fetchList();
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [refreshKey]);

  // -------------------------------------------------------------------- //
  //  Detail fetch
  // -------------------------------------------------------------------- //

  useEffect(() => {
    if (detailId === null) {
      setDetail(null);
      setDetailError(null);
      return;
    }
    let cancelled = false;
    (async () => {
      setDetailLoading(true);
      setDetailError(null);
      try {
        const data = await apiFetch<SavedFull>(
          API_ENDPOINTS.savedResearchById(detailId)
        );
        if (!cancelled) setDetail(data);
      } catch (err) {
        // eslint-disable-next-line no-console
        console.warn('SavedResearchList: detail fetch failed', err);
        if (!cancelled) {
          setDetailError(
            (err as Error).message || 'Failed to load saved report'
          );
          setDetail(null);
        }
      } finally {
        if (!cancelled) setDetailLoading(false);
      }
    })();
    return () => {
      cancelled = true;
    };
  }, [detailId]);

  // -------------------------------------------------------------------- //
  //  Delete
  // -------------------------------------------------------------------- //

  async function handleDelete(id: number) {
    const prev = rows ?? [];
    setRows(prev.filter(r => r.id !== id));
    if (detailId === id) setDetailId(null);

    try {
      const url = `${API_BASE_URL}${API_ENDPOINTS.savedResearchById(id)}`;
      const resp = await fetch(url, { method: 'DELETE' });
      if (!resp.ok && resp.status !== 204) {
        throw new Error(`DELETE failed: ${resp.status} ${resp.statusText}`);
      }
      toast.success('Saved research deleted');
    } catch (err) {
      // eslint-disable-next-line no-console
      console.warn('SavedResearchList: delete failed', err);
      toast.error('Failed to delete saved research');
      setRows(prev);
    }
  }

  // -------------------------------------------------------------------- //
  //  Render — detail view
  // -------------------------------------------------------------------- //

  if (detailId !== null) {
    return (
      <div
        className="max-w-4xl mx-auto space-y-6"
        data-testid="saved-research-detail"
      >
        <button
          type="button"
          onClick={() => setDetailId(null)}
          data-testid="saved-research-back-btn"
          className="font-mono-tx text-[11px] uppercase-eyebrow text-foreground-soft hover:text-signal transition-colors"
        >
          [ ← back to dispatches ]
        </button>

        {detailLoading && (
          <div className="flex items-center gap-2 py-12 justify-center font-mono-tx text-[11px] uppercase-eyebrow text-foreground-soft">
            <Loader2 className="w-4 h-4 animate-spin" />
            <span>loading saved report...</span>
          </div>
        )}

        {detailError && !detailLoading && (
          <div className="flex items-start gap-3 py-6 border-t-2 border-[var(--accent-signal)] px-4 bg-[var(--background-tint)]">
            <AlertCircle className="w-5 h-5 text-signal flex-shrink-0 mt-0.5" />
            <div className="flex-1">
              <p className="font-display text-[18px] font-medium text-foreground">
                Failed to load saved report
              </p>
              <p className="font-mono-tx text-[11px] uppercase-eyebrow text-foreground-soft mt-1">
                {detailError}
              </p>
            </div>
            <button
              type="button"
              onClick={() => {
                const id = detailId;
                setDetailId(null);
                setTimeout(() => setDetailId(id), 0);
              }}
              className="font-mono-tx text-[11px] uppercase-eyebrow text-foreground-soft hover:text-signal"
            >
              [ retry ]
            </button>
          </div>
        )}

        {detail && !detailLoading && !detailError && (
          <article className="space-y-4">
            <header className="space-y-2 border-b-2 border-[var(--foreground)] pb-4">
              <div className="font-mono-tx text-[11px] uppercase-eyebrow text-foreground-soft">
                ━ FILED — {formatDateline(detail.created_at)} · saved{' '}
                {formatRelativeTime(detail.created_at)}
              </div>
              <h2
                className="font-display text-[28px] font-medium tracking-tight text-foreground leading-[1.1] break-words"
                style={{ overflowWrap: 'anywhere', wordBreak: 'break-word' }}
              >
                {detail.question}
              </h2>
            </header>
            <div
              className="min-w-0 overflow-hidden"
              style={{ overflowWrap: 'anywhere', wordBreak: 'break-word' }}
            >
              <MarkdownReport text={detail.report_md} linkifyCitations />
            </div>
          </article>
        )}
      </div>
    );
  }

  // -------------------------------------------------------------------- //
  //  Render — list view
  // -------------------------------------------------------------------- //

  return (
    <div
      className="max-w-3xl mx-auto space-y-4"
      data-testid="saved-research-list"
    >
      {/* === MASTHEAD ============================== */}
      <header className="space-y-1 border-b-2 border-[var(--foreground)] pb-3">
        <div className="font-mono-tx text-[11px] uppercase-eyebrow text-foreground-soft">
          ━ THE FILE ROOM
        </div>
        <h2 className="font-display text-[28px] font-medium tracking-tight text-foreground leading-[1.1]">
          Saved Dispatches
        </h2>
        <p className="font-mono-tx text-[11px] uppercase-eyebrow text-foreground-soft">
          research reports you've filed away · click a row to re-open · [ × ]
          removes
        </p>
      </header>

      {loading && (
        <div className="flex items-center justify-center py-12 font-mono-tx text-[11px] uppercase-eyebrow text-foreground-soft gap-2">
          <Loader2 className="w-4 h-4 animate-spin" />
          <span>loading saved research...</span>
        </div>
      )}

      {!loading && error && (
        <div className="flex items-start gap-3 py-4 border-t-2 border-[var(--accent-signal)] px-4 bg-[var(--background-tint)]">
          <AlertCircle className="w-5 h-5 text-signal flex-shrink-0 mt-0.5" />
          <div className="flex-1">
            <p className="font-display text-[18px] font-medium text-foreground">
              Failed to load saved research
            </p>
            <p className="font-mono-tx text-[11px] uppercase-eyebrow text-foreground-soft mt-1">
              {error}
            </p>
          </div>
          <button
            type="button"
            onClick={() => void fetchList()}
            className="font-mono-tx text-[11px] uppercase-eyebrow text-foreground-soft hover:text-signal"
          >
            [ retry ]
          </button>
        </div>
      )}

      {!loading && !error && rows && rows.length === 0 && (
        <div
          className="text-center py-12 space-y-2"
          data-testid="saved-research-empty"
        >
          <p className="font-mono-tx text-[24px] text-foreground-soft">▌</p>
          <p className="font-mono-tx text-[11px] uppercase-eyebrow text-foreground-soft">
            No saved research yet. Run a research query and click Save.
          </p>
        </div>
      )}

      {!loading && !error && rows && rows.length > 0 && (
        <ul>
          {rows.map(row => (
            <li
              key={row.id}
              data-testid="saved-research-item"
              className="border-t border-[var(--rule)] last:border-b last:border-b-[var(--rule)]"
            >
              <div className="flex items-stretch gap-2">
                <button
                  type="button"
                  onClick={() => setDetailId(row.id)}
                  className="flex-1 py-4 min-w-0 flex flex-col items-start text-left space-y-1 hover:bg-[var(--background-tint)] transition-colors px-2 -mx-2"
                >
                  <span className="font-mono-tx text-[11px] uppercase-eyebrow text-foreground-soft">
                    ▸ FILED — {formatDateline(row.created_at)}
                  </span>
                  <span
                    className="font-display text-[22px] font-medium text-foreground leading-[1.2] group-hover:text-signal w-full break-words"
                    title={row.question}
                    style={{
                      overflowWrap: 'anywhere',
                      wordBreak: 'break-word',
                    }}
                  >
                    {row.question}
                  </span>
                  <span className="font-mono-tx text-[11px] uppercase-eyebrow text-foreground-soft tabular-nums">
                    saved {formatRelativeTime(row.created_at)}
                  </span>
                </button>
                <button
                  type="button"
                  onClick={e => {
                    e.stopPropagation();
                    void handleDelete(row.id);
                  }}
                  data-testid="saved-research-delete-btn"
                  aria-label={`Delete saved research: ${row.question}`}
                  className="self-stretch w-16 flex items-center justify-center font-mono-tx text-[11px] uppercase-eyebrow text-foreground-soft hover:text-signal hover:bg-[var(--background-tint)] transition-colors"
                >
                  [ × ]
                </button>
              </div>
            </li>
          ))}
        </ul>
      )}
    </div>
  );
}
