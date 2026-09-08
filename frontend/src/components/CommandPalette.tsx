/**
 * CommandPalette — Mission 3 / Milestone 1.
 *
 * Global Cmd+K (macOS) / Ctrl+K (Win/Linux) command palette. Lists:
 *   - 6 tab destinations (mirror of SIDEBAR_NAV_ITEMS)
 *   - The last 10 research queries from
 *     `localStorage.techpulse-recent-research` (set by ResearchMode in
 *     M2). When unset / malformed we render an empty section.
 *
 * Selecting a tab switches the active tab. Selecting a recent research
 * query switches to the Research tab AND writes the query into
 * `localStorage.techpulse-pending-research` so ResearchMode can pick it
 * up on next mount (auto-submit is M2's concern).
 *
 * The provider also exposes a `useCommandPalette()` hook with `open()` /
 * `close()` so any descendant (e.g. the Cmd+K button in the sidebar) can
 * trigger it imperatively.
 *
 * Also lists (added alongside tabs + recent research):
 *   - Saved articles, read straight from
 *     `localStorage.techpulse-saved-articles` (the id list NewsCard's Save
 *     button writes -- same key SavedArticlesList.tsx reads). We resolve
 *     ids to titles with the same one-GET-per-id approach
 *     SavedArticlesList uses (no batch-by-ids endpoint exists). Selecting
 *     one navigates to the Saved tab and opens it directly via the
 *     `onOpenArticle` callback (App.tsx's `openArticleReader`) rather than
 *     round-tripping through localStorage -- an earlier version stashed
 *     the id and relied on a `[activeTab]`-effect to pick it up, which
 *     silently no-opped when the palette was opened while already on the
 *     Saved tab (selecting "saved" again is a no-op state update, so the
 *     effect never re-fired).
 *
 * Digest editions were NOT added: there is no client-side digest-history
 * data source to jump into (digest is fetched fresh per-view, nothing
 * persists past editions to localStorage). See CommandPalette's report for
 * this gap rather than fabricating one here.
 */
import {
  createContext,
  useCallback,
  useContext,
  useEffect,
  useMemo,
  useState,
  ReactNode,
} from "react";
import { Command } from "cmdk";
import { DialogTitle } from "./ui/dialog";
import {
  Newspaper,
  Lightbulb,
  Mail,
  Settings,
  Bookmark,
  History,
  FileText,
} from "lucide-react";
import { API_ENDPOINTS, apiFetch } from "../config/api";

// ---------------------------------------------------------------------------
// Tab catalogue — single source of truth for the palette's destination list.
// Kept in sync with Sidebar.tsx's SIDEBAR_NAV_ITEMS. Duplicated here (rather
// than imported) so this file stays independent from Sidebar — the palette
// is mounted at App-root level and Sidebar consumes it (not the other way
// round).
// ---------------------------------------------------------------------------
interface TabEntry {
  value: string;
  label: string;
  icon: React.ComponentType<{ className?: string }>;
}

const TAB_ENTRIES: TabEntry[] = [
  { value: "feed", label: "News Feed", icon: Newspaper },
  { value: "research", label: "Research", icon: Lightbulb },
  { value: "digest", label: "Digest", icon: Mail },
  { value: "saved", label: "Saved", icon: Bookmark },
  { value: "preferences", label: "Settings", icon: Settings },
];

const RECENT_RESEARCH_KEY = "techpulse-recent-research";
const PENDING_RESEARCH_KEY = "techpulse-pending-research";
const SAVED_ARTICLES_KEY = "techpulse-saved-articles";

// ---------------------------------------------------------------------------
// Context — exposes open() / close() to descendants.
// ---------------------------------------------------------------------------
interface CommandPaletteContextValue {
  open: () => void;
  close: () => void;
  toggle: () => void;
  isOpen: boolean;
}

const CommandPaletteContext = createContext<CommandPaletteContextValue | null>(null);

export function useCommandPalette(): CommandPaletteContextValue {
  const ctx = useContext(CommandPaletteContext);
  if (!ctx) {
    throw new Error("useCommandPalette must be used inside <CommandPaletteProvider>");
  }
  return ctx;
}

// ---------------------------------------------------------------------------
// Helper: pull the 10 most recent research queries from localStorage. The
// shape is whatever ResearchMode chooses to write in M2 — we accept both
// `string[]` (just the question text) and `{question: string}[]` shapes and
// silently coerce. Malformed JSON returns an empty array.
// ---------------------------------------------------------------------------
function readRecentResearch(): string[] {
  try {
    const raw = localStorage.getItem(RECENT_RESEARCH_KEY);
    if (!raw) return [];
    const parsed = JSON.parse(raw);
    if (!Array.isArray(parsed)) return [];
    return parsed
      .map((item) => {
        if (typeof item === "string") return item;
        if (item && typeof item === "object" && typeof item.question === "string") {
          return item.question;
        }
        return "";
      })
      .filter((q) => q.length > 0)
      .slice(0, 10);
  } catch {
    return [];
  }
}

// ---------------------------------------------------------------------------
// Helper: read the saved-article id list (capped at 10, newest-first is
// however NewsCard appended them -- we don't reorder). Malformed JSON
// returns an empty array, matching readRecentResearch's failure mode.
// ---------------------------------------------------------------------------
function readSavedArticleIds(): string[] {
  try {
    const raw = localStorage.getItem(SAVED_ARTICLES_KEY);
    if (!raw) return [];
    const parsed = JSON.parse(raw);
    if (!Array.isArray(parsed)) return [];
    return parsed.map(String).slice(0, 10);
  } catch {
    return [];
  }
}

interface SavedArticleEntry {
  id: string;
  title: string;
}

// ---------------------------------------------------------------------------
// Provider — wraps the app and renders the modal as a portal-like overlay.
// ---------------------------------------------------------------------------
interface CommandPaletteProviderProps {
  children: ReactNode;
  /** Currently active tab value (controlled by App.tsx). */
  activeTab: string;
  /** Callback to switch the active tab. */
  onSelectTab: (value: string) => void;
  /** Opens ArticleReader for the given article id (App.tsx's openArticleReader). */
  onOpenArticle: (articleId: string) => void;
}

export function CommandPaletteProvider({
  children,
  activeTab: _activeTab,
  onSelectTab,
  onOpenArticle,
}: CommandPaletteProviderProps) {
  const [isOpen, setIsOpen] = useState(false);
  const [recentResearch, setRecentResearch] = useState<string[]>([]);
  const [savedArticles, setSavedArticles] = useState<SavedArticleEntry[]>([]);

  // Resolve saved-article ids -> titles, one GET per id (mirrors
  // SavedArticlesList.tsx — there's no batch-by-ids endpoint). Fire-and-
  // forget: it fills in the "Saved articles" group a beat after the
  // palette opens rather than blocking open() on the network.
  const loadSavedArticles = useCallback(async () => {
    const ids = readSavedArticleIds();
    if (ids.length === 0) {
      setSavedArticles([]);
      return;
    }
    const results = await Promise.allSettled(
      ids.map((id) =>
        apiFetch<{ data?: { title?: string } }>(API_ENDPOINTS.newsById(id))
      )
    );
    const loaded: SavedArticleEntry[] = [];
    results.forEach((result, idx) => {
      if (result.status === "fulfilled" && result.value?.data?.title) {
        loaded.push({ id: ids[idx], title: result.value.data.title });
      }
    });
    setSavedArticles(loaded);
  }, []);

  const open = useCallback(() => {
    // Refresh the recents list every time we open — cheap, and the user
    // probably ran a research since they last opened the palette.
    setRecentResearch(readRecentResearch());
    void loadSavedArticles();
    setIsOpen(true);
  }, [loadSavedArticles]);

  const close = useCallback(() => setIsOpen(false), []);

  const toggle = useCallback(() => {
    setIsOpen((prev) => {
      if (!prev) {
        setRecentResearch(readRecentResearch());
        void loadSavedArticles();
      }
      return !prev;
    });
  }, [loadSavedArticles]);

  // Global Cmd+K / Ctrl+K hotkey. We attach to `window` so the shortcut
  // works regardless of which element has focus. `preventDefault` stops
  // the browser's default "focus address bar" / "search" mapping.
  useEffect(() => {
    const handler = (e: KeyboardEvent) => {
      const key = e.key.toLowerCase();
      const isModifier = e.metaKey || e.ctrlKey;
      if (isModifier && key === "k") {
        e.preventDefault();
        toggle();
      }
    };
    window.addEventListener("keydown", handler);
    return () => window.removeEventListener("keydown", handler);
  }, [toggle]);

  const ctxValue = useMemo<CommandPaletteContextValue>(
    () => ({ open, close, toggle, isOpen }),
    [open, close, toggle, isOpen]
  );

  const handleSelectTab = (value: string) => {
    onSelectTab(value);
    close();
  };

  const handleSelectRecent = (question: string) => {
    // Stash the query so ResearchMode can pick it up on its next render.
    try {
      localStorage.setItem(PENDING_RESEARCH_KEY, question);
    } catch {
      // If storage is unavailable we just navigate without prefill.
    }
    onSelectTab("research");
    close();
  };

  const handleSelectSavedArticle = (id: string) => {
    onSelectTab("saved");
    onOpenArticle(id);
    close();
  };

  return (
    <CommandPaletteContext.Provider value={ctxValue}>
      {children}
      {isOpen && (
        <CommandPaletteModal
          recentResearch={recentResearch}
          savedArticles={savedArticles}
          onSelectTab={handleSelectTab}
          onSelectRecent={handleSelectRecent}
          onSelectSavedArticle={handleSelectSavedArticle}
          onClose={close}
        />
      )}
    </CommandPaletteContext.Provider>
  );
}

// ---------------------------------------------------------------------------
// Modal — built on cmdk. cmdk handles arrow keys + Enter navigation and the
// Escape-to-close keybinding through its `<Command.Dialog>` primitive.
// ---------------------------------------------------------------------------
interface CommandPaletteModalProps {
  recentResearch: string[];
  savedArticles: SavedArticleEntry[];
  onSelectTab: (value: string) => void;
  onSelectRecent: (question: string) => void;
  onSelectSavedArticle: (id: string) => void;
  onClose: () => void;
}

function CommandPaletteModal({
  recentResearch,
  savedArticles,
  onSelectTab,
  onSelectRecent,
  onSelectSavedArticle,
  onClose,
}: CommandPaletteModalProps) {
  return (
    <Command.Dialog
      open
      onOpenChange={(o) => {
        if (!o) onClose();
      }}
      label="Command palette"
      // The className passed to Command.Dialog flows to the inner Command
      // root (cmdk's source code: `<Command className={className} />`).
      // overlayClassName/contentClassName style the Radix overlay + content
      // wrappers. The Radix Dialog Content already handles Esc-to-close and
      // backdrop-click-to-close through onOpenChange.
      className="flex flex-col"
      overlayClassName="fixed inset-0 bg-black/50 backdrop-blur-sm z-40"
      contentClassName="fixed top-[15vh] left-1/2 -translate-x-1/2 z-50 w-[min(640px,calc(100vw-2rem))] max-h-[60vh] bg-popover text-popover-foreground border border-border rounded-xl shadow-2xl overflow-hidden"
    >
      <>
        {/*
          Radix Dialog requires an accessible title. cmdk's Command.Dialog
          wraps Radix Dialog but doesn't auto-inject one. Add a
          screen-reader-only title to silence the a11y warnings AND
          improve screen-reader UX.
        */}
        <DialogTitle className="sr-only">Command palette</DialogTitle>
        <Command.Input
          placeholder="Jump to a tab or recent research..."
          className="w-full px-4 py-3 text-sm bg-transparent border-b border-border outline-none placeholder:text-muted-foreground"
        />
        <Command.List className="flex-1 overflow-y-auto p-2">
          <Command.Empty className="px-3 py-6 text-sm text-muted-foreground text-center">
            No matches.
          </Command.Empty>

          <Command.Group
            heading="Navigation"
            className="text-[11px] text-muted-foreground uppercase tracking-wider px-2 py-1"
          >
            {TAB_ENTRIES.map((tab) => {
              const Icon = tab.icon;
              return (
                <Command.Item
                  key={tab.value}
                  value={`tab:${tab.value}:${tab.label}`}
                  onSelect={() => onSelectTab(tab.value)}
                  className="flex items-center gap-2 px-2 py-1.5 text-sm rounded-md cursor-pointer text-foreground data-[selected=true]:bg-accent data-[selected=true]:text-accent-foreground"
                >
                  <Icon className="w-4 h-4 text-muted-foreground" />
                  <span>{tab.label}</span>
                </Command.Item>
              );
            })}
          </Command.Group>

          {recentResearch.length > 0 && (
            <Command.Group
              heading="Recent research"
              className="text-[11px] text-muted-foreground uppercase tracking-wider px-2 py-1 mt-2"
            >
              {recentResearch.map((question, idx) => (
                <Command.Item
                  key={`recent-${idx}`}
                  value={`recent:${idx}:${question}`}
                  onSelect={() => onSelectRecent(question)}
                  className="flex items-center gap-2 px-2 py-1.5 text-sm rounded-md cursor-pointer text-foreground data-[selected=true]:bg-accent data-[selected=true]:text-accent-foreground"
                >
                  <History className="w-4 h-4 text-muted-foreground shrink-0" />
                  <span className="truncate">{question}</span>
                </Command.Item>
              ))}
            </Command.Group>
          )}

          {savedArticles.length > 0 && (
            <Command.Group
              heading="Saved articles"
              className="text-[11px] text-muted-foreground uppercase tracking-wider px-2 py-1 mt-2"
            >
              {savedArticles.map((article) => (
                <Command.Item
                  key={`saved-${article.id}`}
                  value={`saved:${article.id}:${article.title}`}
                  onSelect={() => onSelectSavedArticle(article.id)}
                  className="flex items-center gap-2 px-2 py-1.5 text-sm rounded-md cursor-pointer text-foreground data-[selected=true]:bg-accent data-[selected=true]:text-accent-foreground"
                >
                  <FileText className="w-4 h-4 text-muted-foreground shrink-0" />
                  <span className="truncate">{article.title}</span>
                </Command.Item>
              ))}
            </Command.Group>
          )}
        </Command.List>
        <div className="border-t border-border px-3 py-2 text-[11px] text-muted-foreground flex items-center justify-between">
          <span>
            <kbd className="px-1 py-[1px] border border-border rounded bg-muted text-[10px]">
              esc
            </kbd>{" "}
            to close
          </span>
          <span>
            <kbd className="px-1 py-[1px] border border-border rounded bg-muted text-[10px]">
              up
            </kbd>{" "}
            <kbd className="px-1 py-[1px] border border-border rounded bg-muted text-[10px]">
              down
            </kbd>{" "}
            navigate ·{" "}
            <kbd className="px-1 py-[1px] border border-border rounded bg-muted text-[10px]">
              enter
            </kbd>{" "}
            select
          </span>
        </div>
      </>
    </Command.Dialog>
  );
}
