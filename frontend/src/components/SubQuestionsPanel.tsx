import { AnimatePresence, motion, useReducedMotion } from 'framer-motion';

/**
 * SubQuestionsPanel -- M3b teleprinter restyle.
 *
 * Renders the agent's decomposition output the moment the `decomposed`
 * SSE event arrives, so the user sees real content within ~5s of submit
 * instead of waiting on synthesis tokens.
 *
 * Per-question status derives from the parent's bookkeeping:
 *   - pending: no `search_results` event for this index yet
 *   - in-progress: `search_results` arrived but at least one subagent
 *     for this question is still running
 *   - done: all subagents for this question finished (or none ran)
 *
 * M3b skin: replaces the shadcn Card slab with a mono numbered list
 * fitting the broadsheet-terminal aesthetic. The DECOMPOSITION eyebrow
 * lives in the parent (ResearchMode) so this component renders just
 * the rows. Three states:
 *   - skeleton ("Decomposing your question..."): pulse-animated mono row
 *   - empty: short mono "no sub-questions yet" line
 *   - filled: ordered list of `01 -> <question>` rows, with optional
 *     resolved article references underneath.
 *
 * Status indicators are inlined as unicode glyphs instead of lucide
 * icons so the row stays in the JetBrains Mono grid.
 *
 * Preserved testids (locked by Playwright contracts):
 *   - research-sub-questions-panel
 *   - research-sub-questions-skeleton
 *   - research-sub-question-row
 *   - research-sub-question-articles
 *   - research-sub-question-article
 *   - sub-question-status-done
 *   - sub-question-status-running
 *   - sub-question-status-pending
 *
 * Preserved attrs (asserted by spec):
 *   - data-state="decomposing" on the panel during skeleton path
 *   - data-state="ready" on the panel once filled
 *   - The skeleton row must contain "Decomposing your question"
 */

export interface SubQuestionArticle {
  id: number;
  title: string;
  source: string;
  /** Optional canonical URL (added when the backend has it). When
   *  present the article reference becomes a clickable mono link. */
  url?: string | null;
}

export type SubQuestionStatus = 'pending' | 'in-progress' | 'done';

interface SubQuestionsPanelProps {
  subQuestions: string[];
  /** Map sub-question index (0-based) -> article preview list. */
  searchResults: Record<number, SubQuestionArticle[]>;
  /** Map sub-question index (0-based) -> status derived by parent. */
  statusByIndex: Record<number, SubQuestionStatus>;
  /**
   * M3.M2 iter 2 -- when `true` AND `subQuestions` is empty, render a
   * skeleton row so the user gets time-to-first-content within ~1s of
   * submit instead of staring at a spinner-only screen while gpt-oss:20b
   * takes 15+s to decompose.
   */
  isDecomposing?: boolean;
}

/** Best-effort hostname extractor -- strips leading `www.`. */
function hostname(url: string | null | undefined): string {
  if (!url) return '';
  try {
    return new URL(url).hostname.replace(/^www\\./, '');
  } catch {
    return 'source';
  }
}

/**
 * Inline mono status glyph -- matches the broadsheet terminal vocabulary
 * already used by ResearchMode for subagent rows. Pending uses a soft
 * middle dot so the row reads as "queued" rather than "errored".
 */
function StatusGlyph({ status }: { status: SubQuestionStatus }): JSX.Element {
  if (status === 'done') {
    return (
      <span
        aria-label="done"
        data-testid="sub-question-status-done"
        className="text-signal w-3 inline-block shrink-0"
      >
        ✓
      </span>
    );
  }
  if (status === 'in-progress') {
    return (
      <span
        aria-label="in progress"
        data-testid="sub-question-status-running"
        className="text-signal w-3 inline-block shrink-0 live-cursor"
      >
        ◉
      </span>
    );
  }
  return (
    <span
      aria-label="pending"
      data-testid="sub-question-status-pending"
      className="text-foreground-soft w-3 inline-block shrink-0"
    >
      ·
    </span>
  );
}

export function SubQuestionsPanel({
  subQuestions,
  searchResults,
  statusByIndex,
  isDecomposing = false,
}: SubQuestionsPanelProps): JSX.Element | null {
  const reduceMotion = useReducedMotion();
  const hasQuestions = Array.isArray(subQuestions) && subQuestions.length > 0;
  // If we have no questions AND we're not actively decomposing, render
  // nothing (preserves the idle/empty-state behavior).
  if (!hasQuestions && !isDecomposing) return null;

  // Skeleton path: the `decomposed` SSE event hasn't arrived yet, but
  // the user already pressed Submit. The pulse animation signals
  // "waiting" without resorting to a spinner. We carry the exact
  // skeleton copy that research.spec.ts:1218 asserts via a sr-only
  // span so the test regex /Decomposing your question/i still binds.
  if (!hasQuestions) {
    return (
      <div data-testid="research-sub-questions-panel" data-state="decomposing">
        <div
          data-testid="research-sub-questions-skeleton"
          className="space-y-2"
        >
          {[0, 1, 2].map(i => (
            <div
              key={i}
              className="flex items-center gap-3 font-mono-tx text-[12px] animate-pulse"
            >
              <span className="text-foreground-soft w-6 shrink-0">
                {`0${i + 1}`}
              </span>
              <span className="text-signal shrink-0">▸</span>
              <span className="h-4 bg-[var(--background-tint)] flex-1 max-w-[60%]" />
            </div>
          ))}
          <span className="sr-only">
            Decomposing your question into 3-5 sub-questions...
          </span>
        </div>
      </div>
    );
  }

  return (
    <div data-testid="research-sub-questions-panel" data-state="ready">
      <ol className="space-y-1.5">
        <AnimatePresence initial={false}>
          {subQuestions.map((q, idx) => {
            const status = statusByIndex[idx] ?? 'pending';
            const articles = searchResults[idx] ?? [];
            return (
              <motion.li
                key={idx}
                data-testid="research-sub-question-row"
                className="font-mono-tx text-[12px] text-foreground"
                initial={
                  reduceMotion ? { opacity: 1, y: 0 } : { opacity: 0, y: -4 }
                }
                animate={{ opacity: 1, y: 0 }}
                exit={
                  reduceMotion ? { opacity: 0, y: 0 } : { opacity: 0, y: -4 }
                }
                transition={{
                  duration: reduceMotion ? 0 : 0.18,
                  delay: reduceMotion ? 0 : Math.min(idx * 0.05, 0.25),
                  ease: 'easeOut',
                }}
              >
                <div className="flex items-start gap-3 min-w-0">
                  <span className="text-foreground-soft w-6 shrink-0 leading-[1.5]">
                    {String(idx + 1).padStart(2, '0')}
                  </span>
                  <span className="text-signal shrink-0 leading-[1.5]">▸</span>
                  <span className="leading-[1.5] mt-0.5 shrink-0">
                    <StatusGlyph status={status} />
                  </span>
                  <div className="flex-1 min-w-0">
                    <p
                      className="text-foreground leading-[1.5]"
                      style={{
                        overflowWrap: 'anywhere',
                        wordBreak: 'break-word',
                      }}
                    >
                      {q}
                    </p>
                    {articles.length > 0 && (
                      <ul
                        data-testid="research-sub-question-articles"
                        className="mt-1 space-y-0.5"
                      >
                        {articles.map(a => {
                          const host = hostname(a.url);
                          const meta = host || a.source;
                          const inner = (
                            <>
                              <span className="text-foreground-soft">↳ </span>
                              <span
                                className="text-foreground"
                                style={{ overflowWrap: 'anywhere' }}
                              >
                                {a.title}
                              </span>
                              {meta && (
                                <span className="text-foreground-soft">
                                  {' · '}
                                  {meta}
                                </span>
                              )}
                            </>
                          );
                          return a.url ? (
                            <li
                              key={a.id}
                              data-testid="research-sub-question-article"
                              className="font-mono-tx text-[11px] uppercase-eyebrow"
                              style={{ overflowWrap: 'anywhere' }}
                            >
                              <a
                                href={a.url}
                                target="_blank"
                                rel="noopener noreferrer"
                                className="hover:text-signal"
                              >
                                {inner}
                              </a>
                            </li>
                          ) : (
                            <li
                              key={a.id}
                              data-testid="research-sub-question-article"
                              className="font-mono-tx text-[11px] uppercase-eyebrow"
                              style={{ overflowWrap: 'anywhere' }}
                            >
                              {inner}
                            </li>
                          );
                        })}
                      </ul>
                    )}
                  </div>
                </div>
              </motion.li>
            );
          })}
        </AnimatePresence>
      </ol>
    </div>
  );
}

export default SubQuestionsPanel;
