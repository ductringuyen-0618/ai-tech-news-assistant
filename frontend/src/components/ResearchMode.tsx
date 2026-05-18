import { useEffect, useMemo, useRef, useState } from "react";
import type React from "react";
import { AnimatePresence, motion, useReducedMotion } from "framer-motion";
import { toast } from "sonner";
import { API_BASE_URL, API_ENDPOINTS } from "../config/api";
import { MarkdownReport } from "./MarkdownReport";
import { SuggestedQueries } from "./SuggestedQueries";
import { RecentDispatches } from "./RecentDispatches";
import {
  SubQuestionsPanel,
  type SubQuestionArticle,
  type SubQuestionStatus,
} from "./SubQuestionsPanel";

/**
 * ResearchMode -- M3 Broadsheet Terminal rebuild.
 *
 * The marquee feature reimagined as a wire-service teleprinter
 * dispatch. Strips the Claude-chat skin (no bg-secondary rounded-2xl
 * user bubble, no shadcn collapsible ToolUseBlocks) and replaces
 * with:
 *
 *   - Teleprinter masthead -- mono dateline strip with dispatch #,
 *     opened/filed timestamps, and the phase chip at the right
 *     pulsing on a live-cursor blink while mid-flight.
 *   - User question -- editorial Fraunces italic block with mono
 *     "THE QUESTION" eyebrow and mono attribution.
 *   - Three transcript sections separated by mono em-rule headers:
 *       A. DECOMPOSITION  -- numbered sub-questions
 *       B. DISPATCHING SUBAGENTS  -- status rows
 *       C. SYNTHESIZING REPORT / DISPATCH  -- markdown body
 *   - Sticky bottom query bar with mono "> " caret prompt.
 *   - Mono action pills [ ⌃S save ] [ ⌃C copy ] [ ⌃D .md ].
 *
 * Preserves the full M3.M2 testid graph -- no test should break:
 *   research-user-message, research-phase-chip, research-report-card,
 *   research-report-body, research-error-panel, research-retry-btn,
 *   research-cancel-btn, research-save-btn, research-copy-btn,
 *   research-download-btn, research-subagents-panel,
 *   research-subagents-header (sr-only span carrying the legacy regex),
 *   research-subagent-row, research-subagent-row-toggle,
 *   research-subagent-summary, research-sub-questions-panel,
 *   research-sub-question-row, research-sub-question-article,
 *   research-sub-questions-skeleton, research-follow-ups,
 *   research-follow-up-chip, research-empty-suggestions.
 *
 * Phase chip text values pinned to the SSE contract: Decomposing,
 * Searching (i/N), Synthesizing, Done, Error.
 *
 * SSE event surface (unchanged):
 *   - phase: Decomposing | Searching (i/N) | Synthesizing | done
 *   - token: <chunk>
 *   - subagent: start | done | error  (+ enriched `summary` on done)
 *   - error: <message>
 *   - decomposed: {sub_questions: string[]}
 *   - search_results: {sub_question_index, articles}
 *
 * Honors `prefers-reduced-motion` via `useReducedMotion`.
 */

// ---------------------------------------------------------------------------
// Test contract inventory (M3 rewrite gate).
// Every value below MUST survive in the rendered DOM:
//   data-testid="research-user-message"            -- editorial quoted block
//   data-testid="research-phase-chip"              -- mono chip in masthead
//   data-testid="research-report-card"             -- outer transcript wrapper
//   data-testid="research-report-body"             -- markdown wrapper
//   data-testid="research-error-panel"             -- mono error block
//   data-testid="research-retry-btn"               -- [ retry ] pill
//   data-testid="research-cancel-btn"              -- [ ⌃X cancel ] pill
//   data-testid="research-save-btn"                -- [ ⌃S save ] pill
//   data-testid="research-copy-btn"                -- [ ⌃C copy ] pill
//   data-testid="research-download-btn"            -- [ ⌃D .md ] pill
//   data-testid="research-subagents-panel"         -- section B wrapper
//   data-testid="research-subagents-header"        -- sr-only span,
//                                                     /Subagents \(\d+ running,
//                                                      \d+ done, \d+ errored\)/i
//   data-testid="research-subagent-row"            -- per-article row
//   data-testid="research-subagent-row-toggle"     -- clickable expander
//   data-testid="research-subagent-summary"        -- inline expanded body
//   data-testid="research-sub-questions-panel"     -- section A wrapper
//                                                     (rendered by
//                                                     SubQuestionsPanel)
//   data-testid="research-sub-questions-skeleton"  -- decomposing placeholder
//   data-testid="research-sub-question-row"        -- per-question li
//   data-testid="research-sub-question-article"    -- per-article li
//   data-testid="research-follow-ups"              -- continue-with row
//   data-testid="research-follow-up-chip"          -- per-chip button
//   data-testid="research-empty-suggestions"       -- empty-state queries
// Phase chip text values (test-asserted):
//   "Decomposing" | "Searching (i/N)" | "Synthesizing" | "Done" | "Error"
// ---------------------------------------------------------------------------

const EMPTY_STATE_QUERIES: string[] = [
  "OpenAI's last 30 days",
  "AI chip market shifts",
  "Anthropic vs OpenAI announcements",
  "AI funding rounds past month",
  "Cloud security trends",
  "Edge computing developments",
];

// Mount-time handoff key from the Cmd+K palette (M3.M1).
const PENDING_RESEARCH_KEY = "techpulse-pending-research";

// ---------------------------------------------------------------------------
// Follow-up extractor (unchanged from M3.M2).
// ---------------------------------------------------------------------------

const STOPWORDS = new Set([
  "The", "What", "How", "When", "Where", "Why", "Who", "Which",
  "And", "But", "Or", "If", "Of", "For", "From", "With", "Without",
  "In", "On", "At", "To", "By", "As", "Is", "Are", "Was", "Were",
  "Be", "Been", "Being", "Has", "Have", "Had", "Do", "Does", "Did",
  "Can", "Could", "Would", "Should", "Will", "Shall", "May", "Might",
  "Must", "AI", "An", "A", "It", "Its", "This", "That", "These",
  "Those", "Some", "Many", "Most", "More", "Less", "Few", "All",
  "Both", "Each", "Every", "Other", "Such", "No", "Not", "Only",
  "Same", "Than", "Then", "Too", "Very", "Just", "Also", "Even",
  "New", "Old", "First", "Last", "Next", "Past", "Year", "Month",
  "Week", "Day", "Now", "Today", "Sources", "Used", "Executive",
  "Summary", "Key", "Findings", "Trends", "Themes", "Report",
]);

function extractFollowUpEntities(report: string, limit = 3): string[] {
  if (!report) return [];
  const pattern = /\b[A-Z][a-zA-Z]+(?:\s+[A-Z][a-zA-Z]+)*\b/g;
  const counts = new Map<string, number>();
  let m: RegExpExecArray | null;
  while ((m = pattern.exec(report)) !== null) {
    const term = m[0].trim();
    if (!term) continue;
    if (term.length <= 2) continue;
    const words = term.split(/\s+/);
    if (words.every((w) => STOPWORDS.has(w))) continue;
    counts.set(term, (counts.get(term) ?? 0) + 1);
  }
  const ranked = Array.from(counts.entries())
    .filter(([k]) => k.length > 2 && !STOPWORDS.has(k))
    .sort((a, b) => b[1] - a[1])
    .slice(0, limit)
    .map(([k]) => k);
  return ranked;
}

function buildFollowUps(report: string): string[] {
  const entities = extractFollowUpEntities(report, 3);
  const out: string[] = [];
  if (entities[0]) {
    out.push(`How is ${entities[0]} positioned vs the rest of the market?`);
  }
  if (entities[1]) {
    out.push(`What are the most recent developments around ${entities[1]}?`);
  }
  if (entities[2]) {
    out.push(`Drill into ${entities[2]}'s funding history.`);
  }
  const generic = [
    "What risks should we watch out for next quarter?",
    "Which companies are most affected?",
    "How does this compare to the previous month?",
  ];
  let gi = 0;
  while (out.length < 3 && gi < generic.length) {
    if (!out.includes(generic[gi])) out.push(generic[gi]);
    gi += 1;
  }
  return out.slice(0, 3);
}

// ---------------------------------------------------------------------------
// SSE event types
// ---------------------------------------------------------------------------

interface AgentEvent {
  type:
    | "phase"
    | "token"
    | "error"
    | "subagent"
    | "decomposed"
    | "search_results";
  data?: string;
  report?: string;
  skill?: string;
  article_id?: number;
  duration_ms?: number;
  message?: string;
  summary?: string;
  sub_questions?: string[];
  sub_question_index?: number;
  articles?: Array<{ id: number; title: string; source: string }>;
}

interface SubagentRow {
  skill: string;
  articleId: number;
  status: "running" | "done" | "error";
  startedAt: number;
  durationMs?: number;
  message?: string;
  summary?: string;
}

// ---------------------------------------------------------------------------
// Time helpers -- masthead clock + relative-time attribution.
// ---------------------------------------------------------------------------

function formatClock(date: Date): string {
  const hh = String(date.getUTCHours()).padStart(2, "0");
  const mm = String(date.getUTCMinutes()).padStart(2, "0");
  const ss = String(date.getUTCSeconds()).padStart(2, "0");
  return `${hh}:${mm}:${ss} UTC`;
}

function formatRelativeTime(timestamp: number): string {
  if (!timestamp) return "just now";
  const diff = Math.max(0, Date.now() - timestamp);
  if (diff < 5_000) return "just now";
  if (diff < 60_000) return `${Math.round(diff / 1000)}s ago`;
  if (diff < 3_600_000) return `${Math.round(diff / 60_000)}m ago`;
  return `${Math.round(diff / 3_600_000)}h ago`;
}

interface ResearchModeProps {
  // No props needed.
}

export function ResearchMode({}: ResearchModeProps) {
  const reduceMotion = useReducedMotion();
  const [query, setQuery] = useState("");
  const [isResearching, setIsResearching] = useState(false);
  const [phase, setPhase] = useState<string>("");
  const [reportText, setReportText] = useState<string>("");
  const [errorMessage, setErrorMessage] = useState<string | null>(null);
  const [lastSubmittedQuery, setLastSubmittedQuery] = useState<string>("");
  const [submittedAt, setSubmittedAt] = useState<number>(0);
  const [filedAt, setFiledAt] = useState<number>(0);
  const [dispatchNum, setDispatchNum] = useState<string>("");
  const [copied, setCopied] = useState(false);
  const [saveState, setSaveState] = useState<"idle" | "saving" | "saved">(
    "idle"
  );
  const [subagents, setSubagents] = useState<Map<string, SubagentRow>>(
    () => new Map()
  );
  const [subQuestions, setSubQuestions] = useState<string[]>([]);
  const [searchResults, setSearchResults] = useState<
    Record<number, SubQuestionArticle[]>
  >({});
  const [expandedRows, setExpandedRows] = useState<Set<string>>(
    () => new Set()
  );
  // Wall-clock tick for the agent header's "elapsed Ns" indicator.
  const [nowMs, setNowMs] = useState<number>(0);
  const runStartRef = useRef<number>(0);

  const abortRef = useRef<AbortController | null>(null);
  const copiedTimerRef = useRef<ReturnType<typeof setTimeout> | null>(null);
  const inputRef = useRef<HTMLTextAreaElement | null>(null);

  // M3.M1 palette handoff: on mount, if the palette stashed a query in
  // localStorage, pull it, clear the key, and auto-submit.
  const consumedHandoffRef = useRef<boolean>(false);
  useEffect(() => {
    if (consumedHandoffRef.current) return;
    consumedHandoffRef.current = true;
    try {
      const pending = window.localStorage.getItem(PENDING_RESEARCH_KEY);
      if (pending && pending.trim()) {
        window.localStorage.removeItem(PENDING_RESEARCH_KEY);
        setQuery(pending);
        setTimeout(() => {
          void conductResearch(pending);
        }, 50);
      }
    } catch {
      // localStorage unavailable -- silently skip.
    }
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  useEffect(() => {
    return () => {
      if (abortRef.current) {
        abortRef.current.abort();
        abortRef.current = null;
      }
      if (copiedTimerRef.current) {
        clearTimeout(copiedTimerRef.current);
        copiedTimerRef.current = null;
      }
    };
  }, []);

  // Tick a wall-clock while researching so the masthead can show an
  // "elapsed Ns" line. The tick stops once the run finishes.
  useEffect(() => {
    if (!isResearching) return;
    const id = setInterval(() => setNowMs(Date.now()), 200);
    return () => clearInterval(id);
  }, [isResearching]);

  // M1 -- broadcast research-streaming state to the masthead so the
  // dateline's LIVE/FILED token can blink in signal color while the
  // agent is mid-run. Loose pub/sub via a window-scoped CustomEvent
  // so the masthead never has to know ResearchMode exists.
  useEffect(() => {
    const active = phase !== "" && phase !== "done" && phase !== "error";
    window.dispatchEvent(
      new CustomEvent("techpulse:research-stream", { detail: { active } })
    );
    return () => {
      window.dispatchEvent(
        new CustomEvent("techpulse:research-stream", {
          detail: { active: false },
        })
      );
    };
  }, [phase]);

  // -----------------------------------------------------------------------
  // SSE event handler.
  // -----------------------------------------------------------------------

  function handleEvent(
    ev: AgentEvent,
    tokenAcc: { current: string }
  ): { done: boolean; finalReport?: string; errored?: string } {
    if (ev.type === "phase") {
      const ph = ev.data ?? "";
      setPhase(ph);
      if (ph === "done") {
        setFiledAt(Date.now());
        const finalReport =
          typeof ev.report === "string" ? ev.report : tokenAcc.current;
        return { done: true, finalReport };
      }
      return { done: false };
    }

    if (ev.type === "decomposed") {
      const qs = Array.isArray(ev.sub_questions) ? ev.sub_questions : [];
      setSubQuestions(qs);
      return { done: false };
    }

    if (ev.type === "search_results") {
      const idx =
        typeof ev.sub_question_index === "number"
          ? ev.sub_question_index
          : 0;
      const articles = Array.isArray(ev.articles) ? ev.articles : [];
      setSearchResults((prev) => ({ ...prev, [idx]: articles }));
      return { done: false };
    }

    if (ev.type === "token") {
      tokenAcc.current = tokenAcc.current + (ev.data || "");
      setReportText(tokenAcc.current);
      return { done: false };
    }

    if (ev.type === "subagent") {
      const stage = ev.data;
      const skill = ev.skill ?? "unknown";
      const articleId =
        typeof ev.article_id === "number" ? ev.article_id : -1;
      const key = `${skill}:${articleId}`;
      setSubagents((prev) => {
        const next = new Map(prev);
        const existing = next.get(key);
        if (stage === "start") {
          next.set(key, {
            skill,
            articleId,
            status: "running",
            startedAt: existing?.startedAt ?? Date.now(),
          });
        } else if (stage === "done") {
          const startedAt = existing?.startedAt ?? Date.now();
          next.set(key, {
            skill,
            articleId,
            status: "done",
            startedAt,
            durationMs:
              typeof ev.duration_ms === "number"
                ? ev.duration_ms
                : undefined,
            summary: ev.summary,
          });
        } else if (stage === "error") {
          const startedAt = existing?.startedAt ?? Date.now();
          next.set(key, {
            skill,
            articleId,
            status: "error",
            startedAt,
            message: ev.message,
          });
        }
        return next;
      });
      return { done: false };
    }

    if (ev.type === "error") {
      return { done: true, errored: ev.data || "Unknown error" };
    }
    return { done: false };
  }

  // -----------------------------------------------------------------------
  // Conduct research (POST + SSE consume).
  // -----------------------------------------------------------------------

  const conductResearch = async (questionOverride?: string) => {
    const question = (questionOverride ?? query).trim();
    if (!question) {
      toast.error("Please enter a research query");
      return;
    }

    if (abortRef.current) {
      abortRef.current.abort();
      abortRef.current = null;
    }

    setIsResearching(true);
    setPhase("Decomposing");
    setReportText("");
    setErrorMessage(null);
    setLastSubmittedQuery(question);
    setSubmittedAt(Date.now());
    setFiledAt(0);
    setDispatchNum(String(Date.now() % 100000).padStart(5, "0"));
    setCopied(false);
    setSaveState("idle");
    setSubagents(new Map());
    setSubQuestions([]);
    setSearchResults({});
    setExpandedRows(new Set());
    runStartRef.current = Date.now();
    setNowMs(Date.now());

    const ac = new AbortController();
    abortRef.current = ac;

    const tokenAcc = { current: "" };

    try {
      const url = `${API_BASE_URL}${API_ENDPOINTS.research}`;
      const resp = await fetch(url, {
        method: "POST",
        headers: {
          "Content-Type": "application/json",
          Accept: "text/event-stream",
        },
        body: JSON.stringify({ question }),
        signal: ac.signal,
      });

      if (!resp.ok) {
        let detail = `${resp.status} ${resp.statusText}`;
        try {
          const j = await resp.json();
          if (j && typeof j.detail === "string") detail = j.detail;
        } catch {
          // not JSON
        }
        throw new Error(detail);
      }

      if (!resp.body) throw new Error("Streaming response has no body");

      const reader = resp.body.getReader();
      const decoder = new TextDecoder("utf-8");
      let buffer = "";
      let finished = false;

      while (!finished) {
        const { value, done } = await reader.read();
        if (done) break;
        buffer += decoder.decode(value, { stream: true });

        let sepIdx = buffer.indexOf("\n\n");
        while (sepIdx !== -1) {
          const frame = buffer.slice(0, sepIdx);
          buffer = buffer.slice(sepIdx + 2);

          if (frame.startsWith(":")) {
            sepIdx = buffer.indexOf("\n\n");
            continue;
          }

          const dataLines: string[] = [];
          for (const line of frame.split("\n")) {
            if (line.startsWith("data:")) {
              dataLines.push(line.slice(5).replace(/^ /, ""));
            }
          }
          if (dataLines.length > 0) {
            const payload = dataLines.join("\n");
            try {
              const ev = JSON.parse(payload) as AgentEvent;
              const r = handleEvent(ev, tokenAcc);
              if (r.done) {
                if (r.errored) {
                  setErrorMessage(r.errored);
                  setPhase("error");
                } else if (typeof r.finalReport === "string") {
                  setReportText(r.finalReport);
                }
                finished = true;
                break;
              }
            } catch (parseErr) {
              // eslint-disable-next-line no-console
              console.warn(
                "research SSE: failed to parse frame",
                parseErr
              );
            }
          }

          sepIdx = buffer.indexOf("\n\n");
        }
      }
    } catch (err) {
      if ((err as Error).name === "AbortError") return;
      // eslint-disable-next-line no-console
      console.warn("research SSE: stream failed:", err);
      setErrorMessage((err as Error).message || "research interrupted");
      setPhase("error");
    } finally {
      setIsResearching(false);
      if (abortRef.current === ac) abortRef.current = null;
    }
  };

  const onRetry = () => {
    if (lastSubmittedQuery) void conductResearch(lastSubmittedQuery);
  };

  const handleCancel = () => {
    if (abortRef.current) {
      abortRef.current.abort();
      abortRef.current = null;
    }
    setIsResearching(false);
    setPhase("");
    setErrorMessage(null);
  };

  const onCopyMarkdown = () => {
    if (!reportText) return;
    const writeToClipboard = async (): Promise<boolean> => {
      try {
        if (
          navigator.clipboard &&
          typeof navigator.clipboard.writeText === "function"
        ) {
          await navigator.clipboard.writeText(reportText);
          return true;
        }
      } catch {
        // fallthrough
      }
      try {
        const ta = document.createElement("textarea");
        ta.value = reportText;
        ta.setAttribute("readonly", "");
        ta.style.position = "fixed";
        ta.style.opacity = "0";
        document.body.appendChild(ta);
        ta.select();
        const ok = document.execCommand("copy");
        document.body.removeChild(ta);
        return ok;
      } catch {
        return false;
      }
    };
    void writeToClipboard().then((ok) => {
      if (!ok) {
        toast.error("Copy failed");
        return;
      }
      setCopied(true);
      toast.success("Report copied to clipboard");
      if (copiedTimerRef.current) clearTimeout(copiedTimerRef.current);
      copiedTimerRef.current = setTimeout(() => {
        setCopied(false);
        copiedTimerRef.current = null;
      }, 2000);
    });
  };

  const onSaveResearch = async () => {
    if (!reportText || saveState !== "idle") return;
    setSaveState("saving");
    try {
      const url = `${API_BASE_URL}${API_ENDPOINTS.savedResearch}`;
      const resp = await fetch(url, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          question: lastSubmittedQuery,
          report_md: reportText,
          sources: [],
        }),
      });
      if (!resp.ok) {
        let detail = `${resp.status} ${resp.statusText}`;
        try {
          const j = await resp.json();
          if (j && typeof j.detail === "string") detail = j.detail;
        } catch {
          // not JSON
        }
        throw new Error(detail);
      }
      setSaveState("saved");
      toast.success("Research saved", {
        description: "Find it in the Saved tab.",
        duration: 3000,
      });
    } catch (err) {
      // eslint-disable-next-line no-console
      console.warn("research save failed:", err);
      toast.error("Failed to save research", {
        description: (err as Error).message || "Please try again.",
        duration: 3000,
      });
      setSaveState("idle");
    }
  };

  const onDownloadMarkdown = () => {
    if (!reportText) return;
    try {
      const blob = new Blob([reportText], { type: "text/markdown" });
      const url = URL.createObjectURL(blob);
      const a = document.createElement("a");
      a.href = url;
      const stamp = new Date().toISOString().replace(/[:.]/g, "-");
      a.download = `research-${stamp}.md`;
      document.body.appendChild(a);
      a.click();
      document.body.removeChild(a);
      setTimeout(() => URL.revokeObjectURL(url), 1000);
    } catch (err) {
      // eslint-disable-next-line no-console
      console.warn("research download failed:", err);
      toast.error("Download failed");
    }
  };

  function formatDuration(ms: number): string {
    if (ms < 1000) return `${ms}ms`;
    return `${(ms / 1000).toFixed(1)}s`;
  }

  function truncateMessage(msg: string, max = 80): string {
    if (msg.length <= max) return msg;
    return msg.slice(0, max - 1) + "...";
  }

  // -----------------------------------------------------------------------
  // Derived state
  // -----------------------------------------------------------------------

  const showErrorPanel = phase === "error" && errorMessage !== null;
  const showReport = !showErrorPanel && reportText.length > 0;
  const hasActiveQuery =
    lastSubmittedQuery.length > 0 || isResearching || showErrorPanel;
  const showEmptyState =
    !showErrorPanel && !showReport && !isResearching && !hasActiveQuery;

  const subagentRows = Array.from(subagents.values());
  const showSubagentsBlock = subagentRows.length > 0;
  let runningCount = 0;
  let doneCount = 0;
  let erroredCount = 0;
  for (const row of subagentRows) {
    if (row.status === "running") runningCount += 1;
    else if (row.status === "done") doneCount += 1;
    else if (row.status === "error") erroredCount += 1;
  }
  // The summary text doubles as the legacy `research-subagents-header`
  // -- the M3.M2 test contract asserts the regex
  //   /Subagents \(\d+ running, \d+ done, \d+ errored\)/i
  // so we keep it verbatim on an sr-only span. The visible mono line
  // above carries the editorial copy.
  const subagentsHeaderText =
    `Subagents (${runningCount} running, ${doneCount} done, ${erroredCount} errored)`;

  // Sub-question status derivation (unchanged from M3.M2).
  const subQuestionStatusByIndex: Record<number, SubQuestionStatus> = {};
  for (let i = 0; i < subQuestions.length; i += 1) {
    const articles = searchResults[i];
    if (!articles) {
      subQuestionStatusByIndex[i] =
        phase.startsWith("Searching") || subagentRows.length > 0
          ? "in-progress"
          : "pending";
      continue;
    }
    if (articles.length === 0) {
      subQuestionStatusByIndex[i] = "done";
      continue;
    }
    const articleIds = new Set(articles.map((a) => a.id));
    let anyRunning = false;
    let anyDoneOrError = false;
    for (const row of subagentRows) {
      if (articleIds.has(row.articleId)) {
        if (row.status === "running") anyRunning = true;
        if (row.status === "done" || row.status === "error")
          anyDoneOrError = true;
      }
    }
    if (anyRunning) subQuestionStatusByIndex[i] = "in-progress";
    else if (
      anyDoneOrError ||
      phase === "Synthesizing" ||
      phase === "done"
    )
      subQuestionStatusByIndex[i] = "done";
    else subQuestionStatusByIndex[i] = "in-progress";
  }

  // Backward-compat phase chip text -- mirrors the old single-chip
  // badge so `data-testid="research-phase-chip"` still works in the
  // existing Playwright suite. Maps directly to the SSE `phase` event.
  const phaseChipText =
    phase === "done"
      ? "Done"
      : phase === "error"
      ? "Error"
      : phase || "";

  const isActivePhase =
    phase !== "" && phase !== "done" && phase !== "error";

  // Total elapsed time -- counts up while running, freezes once done.
  const agentElapsedMs = (() => {
    if (!runStartRef.current) return 0;
    if (isResearching) return Math.max(0, nowMs - runStartRef.current);
    if (filedAt > 0) return Math.max(0, filedAt - runStartRef.current);
    return 0;
  })();
  const elapsedSeconds =
    agentElapsedMs > 0 ? (agentElapsedMs / 1000).toFixed(1) : "0.0";

  const followUps =
    phase === "done" && reportText ? buildFollowUps(reportText) : [];

  // Masthead timings.
  const openedTimeStr = useMemo(() => {
    if (!submittedAt) return "";
    return formatClock(new Date(submittedAt));
  }, [submittedAt]);
  const filedTimeStr = useMemo(() => {
    if (!filedAt) return "";
    return formatClock(new Date(filedAt));
  }, [filedAt]);

  function toggleRowExpanded(key: string) {
    setExpandedRows((prev) => {
      const next = new Set(prev);
      if (next.has(key)) next.delete(key);
      else next.add(key);
      return next;
    });
  }

  function onSubmitKey(e: React.KeyboardEvent<HTMLTextAreaElement>) {
    if (e.key === "Enter" && !e.shiftKey) {
      e.preventDefault();
      if (!isResearching && query.trim()) {
        void conductResearch();
      }
    }
  }

  // ===================================================================
  // Render
  // ===================================================================

  return (
    <div className="max-w-3xl mx-auto">
      {/* -----------------------------------------------------------
       * Empty state -- shown only when no query has been run yet.
       * SuggestedQueries provides the `research-empty-suggestions`
       * testid via its data-testid prop.
       * ----------------------------------------------------------- */}
      {showEmptyState && (
        <div className="mb-8">
          <div className="font-mono-tx text-[11px] uppercase-eyebrow text-foreground-soft mb-3">
            ━ AGENTIC DESK
          </div>
          <h2 className="font-display text-[28px] leading-[1.3] text-foreground mb-3 italic">
            Ask the desk a question.
          </h2>
          <p className="text-[15px] leading-[1.65] text-foreground-soft mb-6 max-w-3xl">
            The research agent decomposes your question into sub-questions,
            dispatches subagents to read the relevant articles, and
            synthesizes a cited report.
          </p>
          <SuggestedQueries
            queries={EMPTY_STATE_QUERIES}
            onSelect={(q) => {
              setQuery(q);
              void conductResearch(q);
            }}
            label="Try a sample question:"
            data-testid="research-empty-suggestions"
          />
          {/* Recent Dispatches panel (design-review #7). Fills the
              ~50% empty whitespace under the input on desktop and
              gives the Research empty state visual weight + a recall
              affordance. Lazily fetches /api/saved-research so the
              empty state stays cheap to mount. */}
          <RecentDispatches />
        </div>
      )}

      {/* -----------------------------------------------------------
       * Masthead -- teleprinter dateline + phase chip on the right.
       * ----------------------------------------------------------- */}
      {hasActiveQuery && (
        <div className="border-y border-[var(--rule)] py-2 mb-6 font-mono-tx text-[11px] uppercase-eyebrow flex items-center gap-3 flex-wrap">
          <span className="text-foreground-soft">━━━ AGENTIC DESK ━━━</span>
          <span className="text-foreground">DISPATCH #{dispatchNum}</span>
          <span className="text-foreground-soft">━━━</span>
          <span className="text-foreground-soft">
            {phase === "done" && filedTimeStr
              ? `FILED ${filedTimeStr}`
              : openedTimeStr
              ? `OPENED ${openedTimeStr}`
              : "OPENED"}
          </span>
          <span className="text-foreground-soft">━━━</span>
          <span
            data-testid="research-phase-chip"
            className={[
              "ml-auto",
              isActivePhase ? "text-signal live-cursor" : "text-foreground-soft",
              phase === "done" ? "text-signal" : "",
              phase === "error" ? "text-signal" : "",
            ]
              .filter(Boolean)
              .join(" ")}
          >
            {phaseChipText}
          </span>
        </div>
      )}

      {/* -----------------------------------------------------------
       * User question -- editorial quoted block.
       * ----------------------------------------------------------- */}
      {hasActiveQuery && lastSubmittedQuery.length > 0 && (
        <motion.div
          data-testid="research-user-message"
          className="border-b border-[var(--rule)] pb-6 mb-6"
          initial={
            reduceMotion ? { opacity: 1, y: 0 } : { opacity: 0, y: -4 }
          }
          animate={{ opacity: 1, y: 0 }}
          transition={{
            duration: reduceMotion ? 0 : 0.18,
            ease: "easeOut",
          }}
        >
          <div className="font-mono-tx text-[11px] uppercase-eyebrow text-foreground-soft mb-2">
            THE QUESTION
          </div>
          <p
            className="font-display italic text-[24px] leading-[1.3] text-foreground max-w-3xl"
            style={{ overflowWrap: "anywhere", wordBreak: "break-word" }}
          >
            {lastSubmittedQuery}
          </p>
          <div className="font-mono-tx text-[11px] uppercase-eyebrow text-foreground-soft mt-2 text-right">
            — you, {formatRelativeTime(submittedAt)}
          </div>
        </motion.div>
      )}

      {/* -----------------------------------------------------------
       * Transcript -- three sections inside the report-card wrapper.
       * The wrapper carries `data-testid="research-report-card"` so
       * the rubric assertions still bind.
       * ----------------------------------------------------------- */}
      {hasActiveQuery && (
        <motion.div
          data-testid="research-report-card"
          initial={
            reduceMotion ? { opacity: 1, y: 0 } : { opacity: 0, y: 4 }
          }
          animate={{ opacity: 1, y: 0 }}
          transition={{
            duration: reduceMotion ? 0 : 0.22,
            ease: "easeOut",
          }}
        >
          {/* ===== SECTION A -- DECOMPOSITION ===== */}
          {(subQuestions.length > 0 || isResearching) && (
            <section className="mb-6">
              <div className="flex items-center gap-3 font-mono-tx text-[11px] uppercase-eyebrow text-foreground-soft mb-3">
                <span>━ DECOMPOSITION</span>
                <span className="flex-1 border-t border-[var(--rule)]" />
                <span>
                  {subQuestions.length > 0
                    ? `${subQuestions.length} sub-question${subQuestions.length === 1 ? "" : "s"}`
                    : "decomposing..."}
                </span>
              </div>
              <SubQuestionsPanel
                subQuestions={subQuestions}
                searchResults={searchResults}
                statusByIndex={subQuestionStatusByIndex}
                isDecomposing={isResearching && subQuestions.length === 0}
              />
            </section>
          )}

          {/* ===== SECTION B -- DISPATCHING SUBAGENTS ===== */}
          {showSubagentsBlock && (
            <section
              data-testid="research-subagents-panel"
              className="mb-6"
            >
              {/* Visible mono header. Carries the legacy regex-matching
                  text so the M3.M2 test contract toBeVisible() +
                  /Subagents \(\d+ running, \d+ done, \d+ errored\)/i
                  binds to the same element. */}
              <div
                data-testid="research-subagents-header"
                className="flex items-center gap-3 font-mono-tx text-[11px] uppercase-eyebrow text-foreground-soft mb-3 flex-wrap"
              >
                <span>━ DISPATCHING SUBAGENTS</span>
                <span className="flex-1 border-t border-[var(--rule)]" />
                <span>{subagentsHeaderText}</span>
              </div>
              <ul className="space-y-1 font-mono-tx text-[12px]">
                <AnimatePresence initial={false}>
                  {subagentRows.map((row, idx) => {
                    const key = `${row.skill}:${row.articleId}`;
                    const isExpanded = expandedRows.has(key);
                    const canExpand =
                      row.status === "done" &&
                      typeof row.summary === "string" &&
                      row.summary.length > 0;
                    const statusGlyph =
                      row.status === "running"
                        ? "◉"
                        : row.status === "done"
                        ? "✓"
                        : "✗";
                    const statusText =
                      row.status === "running"
                        ? "running"
                        : row.status === "done"
                        ? typeof row.durationMs === "number"
                          ? formatDuration(row.durationMs)
                          : "done"
                        : "error";
                    return (
                      <motion.li
                        key={key}
                        data-testid="research-subagent-row"
                        data-expanded={isExpanded ? "true" : "false"}
                        initial={
                          reduceMotion
                            ? { opacity: 1, y: 0 }
                            : { opacity: 0, y: -4 }
                        }
                        animate={{ opacity: 1, y: 0 }}
                        exit={
                          reduceMotion
                            ? { opacity: 0, y: 0 }
                            : { opacity: 0, y: -4 }
                        }
                        transition={{
                          duration: reduceMotion ? 0 : 0.18,
                          delay: reduceMotion
                            ? 0
                            : Math.min(idx * 0.05, 0.25),
                          ease: "easeOut",
                        }}
                      >
                        <button
                          type="button"
                          data-testid="research-subagent-row-toggle"
                          onClick={() => canExpand && toggleRowExpanded(key)}
                          disabled={!canExpand}
                          aria-expanded={isExpanded}
                          className={[
                            "w-full flex items-center gap-3 text-left py-1",
                            canExpand
                              ? "cursor-pointer hover:text-foreground"
                              : "cursor-default",
                          ].join(" ")}
                        >
                          <span
                            className={
                              row.status === "error"
                                ? "text-signal w-3 inline-block"
                                : row.status === "running"
                                ? "text-signal w-3 inline-block live-cursor"
                                : "text-signal w-3 inline-block"
                            }
                          >
                            {statusGlyph}
                          </span>
                          <span
                            className="flex-1 text-foreground min-w-0"
                            style={{ overflowWrap: "anywhere" }}
                          >
                            {row.skill} #{row.articleId}
                          </span>
                          <span className="text-foreground-soft text-[11px]">
                            {statusText}
                            {row.status === "done" ? " done" : ""}
                          </span>
                          {row.status === "error" && row.message && (
                            <span
                              className="text-foreground-soft text-[11px]"
                              title={row.message}
                              style={{ overflowWrap: "anywhere" }}
                            >
                              {truncateMessage(row.message)}
                            </span>
                          )}
                        </button>
                        {isExpanded && row.summary && (
                          <div
                            data-testid="research-subagent-summary"
                            className="ml-6 mt-2 mb-2 text-foreground-soft text-[12px] leading-[1.55]"
                            style={{ overflowWrap: "anywhere" }}
                          >
                            {row.summary}
                          </div>
                        )}
                      </motion.li>
                    );
                  })}
                </AnimatePresence>
              </ul>
            </section>
          )}

          {/* ===== SECTION C -- SYNTHESIZING REPORT / DISPATCH ===== */}
          {showErrorPanel ? (
            <div
              data-testid="research-error-panel"
              className="border border-[var(--accent-signal)] p-4 mt-4 mb-6 font-mono-tx text-[12px]"
            >
              <div className="uppercase-eyebrow text-signal mb-2">
                ━ ERROR — Research interrupted
              </div>
              {errorMessage && (
                <p
                  className="text-foreground mb-3 leading-[1.55]"
                  style={{ overflowWrap: "anywhere" }}
                >
                  {errorMessage}
                </p>
              )}
              <button
                type="button"
                onClick={onRetry}
                data-testid="research-retry-btn"
                disabled={isResearching || !lastSubmittedQuery}
                className="px-3 py-1.5 text-[11px] uppercase-eyebrow border border-[var(--rule)] hover:bg-[var(--background-tint)] hover:text-signal disabled:opacity-40"
              >
                [ retry ]
              </button>
            </div>
          ) : (
            (reportText.length > 0 || isResearching) && (
              <section className="mb-6">
                <div className="flex items-center gap-3 font-mono-tx text-[11px] uppercase-eyebrow text-foreground-soft mb-3 flex-wrap">
                  <span>
                    ━ {phase === "done" ? "DISPATCH" : "SYNTHESIZING REPORT"}
                  </span>
                  <span className="flex-1 border-t border-[var(--rule)]" />
                  <span>{elapsedSeconds}s elapsed</span>
                </div>
                <div
                  data-testid="research-report-body"
                  className="research-report min-w-0 overflow-hidden"
                  style={{
                    overflowWrap: "anywhere",
                    wordBreak: "break-word",
                  }}
                >
                  {reportText.length > 0 ? (
                    <>
                      <MarkdownReport
                        text={reportText}
                        linkifyCitations={phase === "done"}
                      />
                      {phase === "Synthesizing" && (
                        <span className="stream-caret" />
                      )}
                    </>
                  ) : (
                    <div className="flex items-center gap-2 text-foreground-soft py-4 font-mono-tx text-[12px]">
                      <span className="live-cursor text-signal" />
                      <span>
                        {phase === "Decomposing"
                          ? "decomposing question..."
                          : phase.startsWith("Searching")
                          ? "searching for articles..."
                          : phase === "Synthesizing"
                          ? "synthesizing the dispatch..."
                          : "thinking..."}
                      </span>
                    </div>
                  )}
                </div>
              </section>
            )
          )}

          {/* -----------------------------------------------------------
           * Action bar -- mono pills. Cancel mid-flight, save/copy/dl on done.
           * ----------------------------------------------------------- */}
          {(isResearching || phase === "done") && (
            <div className="flex items-center gap-2 font-mono-tx text-[11px] uppercase-eyebrow mt-6 pt-4 border-t border-[var(--rule)] flex-wrap">
              {isResearching && (
                <button
                  type="button"
                  onClick={handleCancel}
                  data-testid="research-cancel-btn"
                  aria-label="Cancel research"
                  className="px-3 py-1.5 border border-[var(--rule)] hover:bg-[var(--background-tint)] hover:text-signal"
                >
                  [ ⌃X cancel ]
                </button>
              )}
              {showReport && phase === "done" && (
                <>
                  <button
                    type="button"
                    onClick={onSaveResearch}
                    data-testid="research-save-btn"
                    aria-label={
                      saveState === "saved"
                        ? "Saved"
                        : saveState === "saving"
                        ? "Saving"
                        : "Save research"
                    }
                    aria-live="polite"
                    disabled={saveState !== "idle"}
                    className="px-3 py-1.5 border border-[var(--rule)] hover:bg-[var(--background-tint)] hover:text-signal disabled:opacity-40"
                  >
                    {saveState === "saved"
                      ? "[ ✓ saved ]"
                      : saveState === "saving"
                      ? "[ saving... ]"
                      : "[ ⌃S save ]"}
                  </button>
                  <button
                    type="button"
                    onClick={onCopyMarkdown}
                    data-testid="research-copy-btn"
                    aria-label={copied ? "Copied" : "Copy markdown"}
                    aria-live="polite"
                    className="px-3 py-1.5 border border-[var(--rule)] hover:bg-[var(--background-tint)] hover:text-signal"
                  >
                    {copied ? "[ ✓ copied ]" : "[ ⌃C copy ]"}
                  </button>
                  <button
                    type="button"
                    onClick={onDownloadMarkdown}
                    data-testid="research-download-btn"
                    aria-label="Download markdown"
                    className="px-3 py-1.5 border border-[var(--rule)] hover:bg-[var(--background-tint)] hover:text-signal"
                  >
                    [ ⌃D .md ]
                  </button>
                </>
              )}
            </div>
          )}
        </motion.div>
      )}

      {/* -----------------------------------------------------------
       * Follow-up ticker -- mono [ <q> ] chips.
       * ----------------------------------------------------------- */}
      {followUps.length > 0 && (
        <div
          data-testid="research-follow-ups"
          className="mt-6 pt-4 border-t border-[var(--rule)]"
        >
          <div className="font-mono-tx text-[11px] uppercase-eyebrow text-foreground-soft mb-3">
            ━ continue with
          </div>
          <div className="flex flex-wrap gap-2">
            {followUps.map((s, i) => (
              <button
                key={i}
                type="button"
                data-testid="research-follow-up-chip"
                onClick={() => {
                  setQuery(s);
                  void conductResearch(s);
                }}
                className="px-3 py-1.5 font-mono-tx text-[11px] uppercase-eyebrow border border-[var(--rule)] hover:text-signal hover:border-[var(--accent-signal)]"
              >
                [ {s} ]
              </button>
            ))}
          </div>
        </div>
      )}

      {/* -----------------------------------------------------------
       * Sticky bottom query bar -- mono caret prompt + submit pill.
       * The placeholder MUST contain "AI funding rounds" so the
       * Playwright helper `page.getByPlaceholder(/AI funding rounds/i)`
       * keeps locating it.
       * ----------------------------------------------------------- */}
      <div className="sticky bottom-0 bg-background border-t-2 border-[var(--foreground)] mt-8 pt-3 pb-4">
        <div className="flex items-end gap-3">
          <span className="font-mono-tx text-foreground-soft pt-2 pl-3 text-[13px]">
            {isResearching ? (
              <span className="live-cursor text-signal" />
            ) : (
              <>&gt;</>
            )}
          </span>
          <textarea
            ref={inputRef}
            value={query}
            onChange={(e) => setQuery(e.target.value)}
            onKeyDown={onSubmitKey}
            rows={1}
            disabled={isResearching}
            placeholder="ask the desk... e.g., Summarize the biggest AI funding rounds in the past 2 weeks"
            className="flex-1 resize-none bg-transparent font-mono-tx text-[13px] text-foreground placeholder:text-foreground-soft border-0 outline-none focus:ring-0 py-2 disabled:opacity-40"
          />
          <button
            type="button"
            onClick={() => conductResearch()}
            disabled={isResearching || !query.trim()}
            aria-label="Research"
            className="px-3 py-1.5 font-mono-tx text-[11px] uppercase-eyebrow border border-[var(--rule)] hover:bg-[var(--background-tint)] hover:text-signal disabled:opacity-40"
          >
            {isResearching ? "[ running... ]" : "[ Research ⏎ ]"}
          </button>
        </div>
      </div>
    </div>
  );
}

export default ResearchMode;
