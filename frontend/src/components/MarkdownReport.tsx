import type React from 'react';
import { useMemo } from 'react';
import ReactMarkdown from 'react-markdown';
import remarkGfm from 'remark-gfm';

/**
 * MarkdownReport -- M3b typography pass.
 *
 * Replaces the hand-rolled M3 inline renderer with `react-markdown` +
 * `remark-gfm`. Fixes the GFM table bug (the previous renderer didn't
 * understand `| col | col |\n|---|---|` and rendered tables as raw
 * pipes and dashes).
 *
 * Security: `rehype-raw` is intentionally NOT used. Any HTML inside the
 * model-emitted markdown is escaped, so a poisoned source can't inject
 * arbitrary tags / script / style.
 *
 * Citation linkifier:
 * - When `linkifyCitations=true`, plain-text `[N]` markers in paragraphs,
 *   list items, table cells, etc. are turned into
 *   `<a class="citation" href="#source-N">[N]</a>` anchors. Clicking
 *   smooth-scrolls to the matching `#source-N` id (assigned by the
 *   first list under any `Sources Used` heading).
 * - When `linkifyCitations=false` (default -- streaming phase) the
 *   markers pass through as literal text to avoid mid-stream flicker.
 *
 * M3.M4 `renderCitation`:
 * Optional callback invoked for each `[N]` anchor. Receives the citation
 * number plus the rendered anchor element and returns the React node to
 * insert in its place. Used by ResearchMode to wrap each citation in a
 * `<CitationHoverCard>` that fetches `/api/news/{id}` and shows a
 * preview card on hover.
 *
 * M3b typography (per docs/designs/frontend-overhaul.md S9 step 5):
 *  - Fraunces display headings (h1 28px with bottom rule, h2 22px,
 *    h3 18px, h4 mono-eyebrow 12px).
 *  - IBM Plex Sans body 15px / 1.65 line-height.
 *  - Editorial drop cap on the first <p> of the document when its
 *    plain-text length exceeds 200 chars. First-paragraph detection
 *    happens once via useMemo over the markdown source: we scan for
 *    the first non-heading paragraph and capture the first ~32 chars
 *    of its plain text, then compare against each rendered <p>'s text
 *    in the components prop.
 *  - Fraunces italic blockquote with signal-color left rule.
 *  - Mono inline code with subtle background tint.
 *  - Mono uppercase-eyebrow table headers.
 *  - Citation [N] pill: mono brackets in soft ink, signal-color number,
 *    signal-wash hover background.
 *
 * The styles are applied via per-element className on the components
 * prop so MarkdownReport works the same whether rendered inside
 * ResearchMode (which wraps it in `.research-report`) or inside
 * SavedResearchList (which does not).
 */

interface MarkdownReportProps {
  text: string;
  /**
   * When true, inline `[N]` markers become anchor links and the first
   * list under a `Sources Used` heading gets sequential `id="source-N"`
   * anchors. Off during streaming.
   */
  linkifyCitations?: boolean;
  /**
   * Optional wrapper for each citation anchor. Called as
   * `renderCitation(n, anchor)` where `n` is the citation index
   * (1-based) and `anchor` is the rendered `<a class="citation">`
   * element. The returned node replaces the bare anchor in the
   * output. Default: pass through.
   */
  renderCitation?: (n: number, anchor: React.ReactElement) => React.ReactNode;
}

function handleCitationClick(
  event: React.MouseEvent<HTMLAnchorElement>,
  n: number
): void {
  event.preventDefault();
  const target = document.getElementById(`source-${n}`);
  if (target) {
    target.scrollIntoView({ behavior: 'smooth', block: 'start' });
  }
}

/**
 * Render a `[N]` citation anchor with the M3b pill styling: mono
 * brackets in soft ink, signal-color number, signal-wash hover
 * background. The `citation` class + `#source-N` href are preserved
 * because Playwright contracts assert on both
 * (`a.citation[href^="#source-"]`).
 */
function CitationPill({
  n,
  anchorKey,
}: {
  n: number;
  anchorKey: string;
}): React.ReactElement {
  return (
    <a
      key={anchorKey}
      className="citation inline-flex items-baseline font-mono-tx text-[11px] align-baseline hover:bg-signal-wash transition-colors px-0.5 cursor-pointer no-underline"
      href={`#source-${n}`}
      onClick={e => handleCitationClick(e, n)}
    >
      <span className="text-foreground-soft">[</span>
      <span className="text-signal font-medium px-0.5">{n}</span>
      <span className="text-foreground-soft">]</span>
    </a>
  );
}

/**
 * Walk a node's children array and split string children on `[N]` so the
 * numeric citation markers become `<a class="citation">` anchors. Skips
 * non-string children (already-rendered React elements) so nested
 * formatting (bold, code, links) is preserved.
 */
function linkifyChildren(
  children: React.ReactNode,
  keyPrefix: string,
  renderCitation?: (n: number, anchor: React.ReactElement) => React.ReactNode
): React.ReactNode {
  const pattern = /\[(\d+)\]/g;
  const out: React.ReactNode[] = [];
  let i = 0;

  const walk = (node: React.ReactNode): void => {
    if (typeof node === 'string') {
      let lastIndex = 0;
      let m: RegExpExecArray | null;
      pattern.lastIndex = 0;
      while ((m = pattern.exec(node)) !== null) {
        if (m.index > lastIndex) {
          out.push(node.slice(lastIndex, m.index));
        }
        const n = parseInt(m[1], 10);
        const key = `${keyPrefix}-cite-${i++}`;
        const anchor = <CitationPill n={n} anchorKey={key} />;
        if (renderCitation) {
          out.push(<span key={key}>{renderCitation(n, anchor)}</span>);
        } else {
          // React requires `key` on the array element directly, not on
          // the component's internal return. Wrap so the key applies.
          out.push(<span key={key}>{anchor}</span>);
        }
        lastIndex = m.index + m[0].length;
      }
      if (lastIndex < node.length) {
        out.push(node.slice(lastIndex));
      }
      return;
    }
    if (Array.isArray(node)) {
      for (const child of node) walk(child);
      return;
    }
    out.push(node);
  };

  walk(children);
  return out;
}

/**
 * Recursively extract the plain text from a React children tree. Used
 * to compare a rendered <p>'s text against the cached first-paragraph
 * preview so we can apply `.editorial-drop` to the right paragraph.
 */
function extractText(children: React.ReactNode): string {
  if (children == null || typeof children === 'boolean') return '';
  if (typeof children === 'string') return children;
  if (typeof children === 'number') return String(children);
  if (Array.isArray(children)) return children.map(extractText).join('');
  if (typeof children === 'object' && 'props' in children) {
    return extractText(
      (children as { props?: { children?: React.ReactNode } }).props?.children
    );
  }
  return '';
}

/**
 * Scan the raw markdown for the first non-heading paragraph and
 * return the first ~64 chars of its plain text as a fingerprint plus
 * the full length. Headings, blank lines, list items, blockquotes,
 * tables and fenced code are skipped. Returns null when no qualifying
 * paragraph exists.
 *
 * This is the least-fragile pattern across react-markdown versions:
 * we do the scan once per render via useMemo over the source text,
 * then identify "the first paragraph" by comparing the rendered <p>'s
 * extracted text to the captured fingerprint -- no AST plugin, no
 * mutable closure flag.
 */
function findFirstParagraph(
  source: string
): { fingerprint: string; length: number } | null {
  if (!source) return null;
  const lines = source.split(/\r?\n/);
  let inFence = false;
  let buf: string[] = [];
  for (let i = 0; i < lines.length; i += 1) {
    const line = lines[i];
    const trimmed = line.trim();
    if (trimmed.startsWith('```') || trimmed.startsWith('~~~')) {
      inFence = !inFence;
      continue;
    }
    if (inFence) continue;
    if (!trimmed) {
      if (buf.length > 0) break;
      continue;
    }
    // Skip block constructs that aren't paragraphs.
    if (/^#{1,6}\s/.test(trimmed)) {
      buf = [];
      continue;
    }
    if (/^>/.test(trimmed)) continue;
    if (/^[-*+]\s/.test(trimmed) || /^\d+\.\s/.test(trimmed)) continue;
    if (/^\|/.test(trimmed)) continue;
    if (/^-{3,}$/.test(trimmed) || /^_{3,}$/.test(trimmed)) continue;
    buf.push(trimmed);
  }
  if (buf.length === 0) return null;
  // Strip markdown emphasis / links / inline code from the fingerprint
  // so it matches the *rendered* text the React tree produces.
  const joined = buf
    .join(' ')
    .replace(/`([^`]+)`/g, '$1')
    .replace(/\*\*([^*]+)\*\*/g, '$1')
    .replace(/\*([^*]+)\*/g, '$1')
    .replace(/_([^_]+)_/g, '$1')
    .replace(/\[([^\]]+)\]\([^)]+\)/g, '$1')
    .replace(/\s+/g, ' ')
    .trim();
  return {
    fingerprint: joined.slice(0, 64),
    length: joined.length,
  };
}

export function MarkdownReport({
  text,
  linkifyCitations = false,
  renderCitation,
}: MarkdownReportProps): JSX.Element {
  // -----------------------------------------------------------------------
  // Source-anchor state. While react-markdown walks the AST it calls our
  // `components.h2` override; we use closure variables to track whether
  // we're currently rendering inside a "Sources Used" section, and to
  // assign sequential `id="source-N"` attributes to the first list under
  // that heading.
  //
  // react-markdown re-renders the entire tree on every text update, so
  // we reset these counters at the start of every render.
  // -----------------------------------------------------------------------
  let inSourcesSection = false;
  let sourceCounter = 0;

  // First-paragraph detection -- cached per markdown source. The
  // editorial drop cap only applies to the very first body paragraph
  // when it's substantive (>200 chars of plain text).
  const firstPara = useMemo(() => findFirstParagraph(text), [text]);

  return (
    <div className="markdown-report max-w-none">
      <ReactMarkdown
        remarkPlugins={[remarkGfm]}
        components={{
          h1: ({ children, ...rest }) => {
            const t = String(children ?? '').trim();
            if (linkifyCitations && /^sources?\b/i.test(t)) {
              inSourcesSection = true;
              sourceCounter = 0;
            } else {
              inSourcesSection = false;
            }
            return (
              <h1
                className="font-display text-[28px] font-medium border-b border-[var(--rule)] pb-2 mt-8 mb-3 tracking-tight text-foreground"
                {...rest}
              >
                {children}
              </h1>
            );
          },
          h2: ({ children, ...rest }) => {
            const t = String(children ?? '').trim();
            if (linkifyCitations && /^sources?\b/i.test(t)) {
              inSourcesSection = true;
              sourceCounter = 0;
            } else {
              inSourcesSection = false;
            }
            return (
              <h2
                className="font-display text-[22px] font-medium mt-6 mb-2 tracking-tight text-foreground"
                {...rest}
              >
                {children}
              </h2>
            );
          },
          h3: ({ children, ...rest }) => {
            const t = String(children ?? '').trim();
            if (linkifyCitations && /^sources?\b/i.test(t)) {
              inSourcesSection = true;
              sourceCounter = 0;
            } else {
              inSourcesSection = false;
            }
            return (
              <h3
                className="font-display text-[18px] font-medium mt-5 mb-2 tracking-tight text-foreground"
                {...rest}
              >
                {children}
              </h3>
            );
          },
          h4: ({ children, ...rest }) => (
            <h4
              className="font-mono-tx text-[12px] uppercase-eyebrow text-foreground-soft mt-4 mb-1"
              {...rest}
            >
              {children}
            </h4>
          ),
          p: ({ children, ...rest }) => {
            // Editorial drop cap on the first body paragraph when it's
            // substantive (>200 chars). We match against the cached
            // fingerprint computed from the raw markdown source.
            const renderedText = extractText(children)
              .replace(/\s+/g, ' ')
              .trim();
            const isFirst =
              firstPara !== null &&
              firstPara.length > 200 &&
              renderedText.startsWith(firstPara.fingerprint);
            const cls = [
              'text-[15px] leading-[1.65] mb-4 text-foreground',
              isFirst ? 'editorial-drop' : '',
            ]
              .filter(Boolean)
              .join(' ');
            return (
              <p
                className={cls}
                style={{
                  overflowWrap: 'anywhere',
                  wordBreak: 'break-word',
                }}
                {...rest}
              >
                {linkifyCitations
                  ? linkifyChildren(children, 'p', renderCitation)
                  : children}
              </p>
            );
          },
          ul: ({ children, ...rest }) => (
            <ul
              className="markdown-list-soft-marker pl-5 my-3 space-y-1.5 text-[15px] leading-[1.6] text-foreground list-disc"
              {...rest}
            >
              {children}
            </ul>
          ),
          ol: ({ children, ...rest }) => (
            <ol
              className="markdown-list-soft-marker pl-5 my-3 space-y-1.5 text-[15px] leading-[1.6] text-foreground list-decimal"
              {...rest}
            >
              {children}
            </ol>
          ),
          li: ({ children, ...rest }) => {
            // If we're inside the Sources section, claim a sequential
            // anchor id for this <li>. Cap at 1000 so a runaway list
            // doesn't generate silly counts.
            const anchorId =
              inSourcesSection && sourceCounter < 1000
                ? `source-${++sourceCounter}`
                : undefined;
            return (
              <li id={anchorId} {...rest}>
                {linkifyCitations
                  ? linkifyChildren(children, 'li', renderCitation)
                  : children}
              </li>
            );
          },
          a: ({ href, children, ...rest }) => {
            // Already-linkified citation anchors keep their existing
            // styling. External links open in a new tab.
            const isCitation =
              typeof href === 'string' && href.startsWith('#source-');
            if (isCitation) {
              const m = href.match(/^#source-(\d+)$/);
              const n = m ? parseInt(m[1], 10) : 0;
              return (
                <a
                  className="citation inline-flex items-baseline font-mono-tx text-[11px] align-baseline hover:bg-signal-wash transition-colors px-0.5 cursor-pointer no-underline"
                  href={href}
                  onClick={e => handleCitationClick(e, n)}
                  {...rest}
                >
                  <span className="text-foreground-soft">[</span>
                  <span className="text-signal font-medium px-0.5">{n}</span>
                  <span className="text-foreground-soft">]</span>
                </a>
              );
            }
            return (
              <a
                href={href}
                target="_blank"
                rel="noopener noreferrer"
                className="text-signal underline decoration-[var(--accent-signal)] decoration-1 underline-offset-2 hover:bg-signal-wash break-words"
                {...rest}
              >
                {children}
              </a>
            );
          },
          code: ({ inline, className, children, ...rest }: any) => {
            if (inline) {
              return (
                <code
                  className="font-mono-tx text-[13px] bg-[var(--background-tint)] px-1 py-0.5 text-foreground"
                  {...rest}
                >
                  {children}
                </code>
              );
            }
            return (
              <code
                className={`block font-mono-tx text-[13px] bg-[var(--background-tint)] text-foreground p-3 overflow-x-auto ${className ?? ''}`}
                {...rest}
              >
                {children}
              </code>
            );
          },
          pre: ({ children, ...rest }) => (
            <pre
              className="font-mono-tx text-[13px] bg-[var(--background-tint)] p-3 my-4 overflow-x-auto border border-[var(--rule)]"
              {...rest}
            >
              {children}
            </pre>
          ),
          // ----- GFM table support (the table-bug fix) -----
          table: ({ children, ...rest }) => (
            <div className="my-4 overflow-x-auto">
              <table
                className="min-w-full border-collapse text-[14px]"
                {...rest}
              >
                {children}
              </table>
            </div>
          ),
          thead: ({ children, ...rest }) => <thead {...rest}>{children}</thead>,
          tbody: ({ children, ...rest }) => <tbody {...rest}>{children}</tbody>,
          tr: ({ children, ...rest }) => (
            <tr className="border-b border-[var(--rule)]" {...rest}>
              {children}
            </tr>
          ),
          th: ({ children, ...rest }: any) => (
            <th
              className="font-mono-tx text-[11px] uppercase-eyebrow text-foreground-soft border-b border-[var(--rule)] py-2 px-3 text-left"
              {...rest}
            >
              {children}
            </th>
          ),
          td: ({ children, ...rest }: any) => (
            <td
              className="py-2 px-3 align-top text-foreground text-[14px]"
              {...rest}
            >
              {linkifyCitations
                ? linkifyChildren(children, 'td', renderCitation)
                : children}
            </td>
          ),
          blockquote: ({ children, ...rest }) => (
            <blockquote
              className="font-display italic text-[18px] leading-[1.55] border-l-2 border-[var(--accent-signal)] pl-4 my-4 text-foreground"
              {...rest}
            >
              {children}
            </blockquote>
          ),
          hr: () => (
            <hr className="my-6 border-0 border-t border-[var(--rule)]" />
          ),
        }}
      >
        {text}
      </ReactMarkdown>
    </div>
  );
}

export default MarkdownReport;
