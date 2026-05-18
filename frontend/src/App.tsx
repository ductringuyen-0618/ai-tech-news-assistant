import { useState, useEffect } from "react";
import { motion, useReducedMotion } from "framer-motion";
import { Tabs, TabsContent } from "./components/ui/tabs";
import { Button } from "./components/ui/button";
import { Badge } from "./components/ui/badge";
import { Toaster } from "./components/ui/sonner";
import { toast } from "sonner";
import { NewsCard } from "./components/NewsCard";
import { LeadStoryCard } from "./components/LeadStoryCard";
import { Settings } from "./components/Settings";
import { SearchBar } from "./components/SearchBar";
import { DigestView } from "./components/DigestView";
import { TrendingRail } from "./components/TrendingRail";
import { ResearchMode } from "./components/ResearchMode";
import { KnowledgeGraph } from "./components/KnowledgeGraph";
import { SavedResearchList } from "./components/SavedResearchList";
import { ThemeProvider } from "./components/ThemeProvider";
import { CommandPaletteProvider } from "./components/CommandPalette";
import { Sidebar } from "./components/Sidebar";
import { WelcomeScreen } from "./components/WelcomeScreen";
import {
  Newspaper,
  TrendingUp,
  Loader2,
  Grid,
  List,
} from "lucide-react";
import { API_ENDPOINTS, apiFetch } from "./config/api";

/**
 * AppShell — the actual UI. Lives inside <ThemeProvider> via the default
 * <App /> export below. The shell renders the sidebar + main content
 * inside a controlled Radix <Tabs> root so we keep the existing
 * `role="tab"` / `role="tablist"` / `role="tabpanel"` accessibility tree
 * that the 35 Playwright tests rely on.
 */
function AppShell() {
  const [articles, setArticles] = useState<any[]>([]);
  const [filteredArticles, setFilteredArticles] = useState<any[]>([]);
  // Start with no category filters so the News Feed shows every ingested
  // article on first load. Previously we pre-applied ["AI", "Machine
  // Learning"] which hid every article whose RSS categories didn't include
  // those exact strings -- 'No articles found' on a fully-populated DB.
  const [selectedCategories, setSelectedCategories] = useState<string[]>([]);
  // Polish iter 3 / Part D — entities the user has chip-toggled from the
  // TrendingRail. Kept separate from ``selectedCategories`` (which still
  // hits the backend ``?category=`` filter) because entity names are NOT
  // valid categories — we apply them client-side as a substring match on
  // each article's title + summary.
  const [selectedEntities, setSelectedEntities] = useState<string[]>([]);
  const [searchQuery, setSearchQuery] = useState("");
  const [digest, setDigest] = useState<any>(null);
  // Polish iter 3 / Part C — separate state for the three new digest panels
  // so the existing /api/digest/ call doesn't block the rest of the UI.
  const [dailySummary, setDailySummary] = useState<any>(null);
  const [dailySummaryLoading, setDailySummaryLoading] = useState(false);
  const [curatedHeadlines, setCuratedHeadlines] = useState<any[] | null>(null);
  const [topicClusters, setTopicClusters] = useState<any[] | null>(null);
  const [loading, setLoading] = useState(true);
  const [viewMode, setViewMode] = useState<"compact" | "detailed">("detailed");
  const [showTrendingOnly, setShowTrendingOnly] = useState(false);
  const [isSavingPreferences, setIsSavingPreferences] = useState(false);
  const [savedCategories, setSavedCategories] = useState<string[]>([]);
  const [hasUnsavedChanges, setHasUnsavedChanges] = useState(false);
  const [totalArticleCount, setTotalArticleCount] = useState<number>(0);
  // ---------------------------------------------------------------------- //
  //  Routing -- History API, clean paths (polish iter 7).
  // ---------------------------------------------------------------------- //
  //
  // URL design follows standard front-end practice: every tab is a real
  // path segment, `/` is the homepage.
  //
  //   /            -> Welcome / homepage
  //   /feed        -> News Feed
  //   /research    -> Agentic Research
  //   /knowledge   -> Knowledge Graph
  //   /digest      -> Daily Digest
  //   /saved       -> Saved Research
  //   /settings    -> Settings (renamed from /preferences for shorter URL)
  //
  // Deployment note: any SPA-fallback dev/prod server is required so
  // refreshing /research returns index.html (Vite dev does this by
  // default; production needs a catch-all route in the static host).
  const VALID_TABS = ["feed", "research", "knowledge", "digest", "saved", "preferences"] as const;
  // Internal tab id -> URL path segment. Most are identical; preferences
  // maps to /settings because that's the user-facing label and the
  // shorter URL reads better.
  const TAB_TO_PATH: Record<string, string> = {
    feed: "/feed",
    research: "/research",
    knowledge: "/knowledge",
    digest: "/digest",
    saved: "/saved",
    preferences: "/settings",
  };
  const PATH_TO_TAB: Record<string, string> = {
    feed: "feed",
    research: "research",
    knowledge: "knowledge",
    digest: "digest",
    saved: "saved",
    settings: "preferences",
    // Backwards-compat: keep /preferences working for any old bookmarks.
    preferences: "preferences",
  };
  const readPathTab = (): string | null => {
    if (typeof window === "undefined") return null;
    const seg = window.location.pathname.replace(/^\/+/, "").split("/")[0];
    if (!seg) return null; // "/" -> no tab, render welcome
    return PATH_TO_TAB[seg] || null;
  };
  const [activeTab, setActiveTabState] = useState<string>(
    () => readPathTab() || "feed"
  );

  // Welcome screen shows when the user is at `/` (no tab path).
  // Deep links like /research skip the welcome so shared URLs always
  // land on the intended content. The legacy `techpulse-welcome-seen`
  // localStorage flag is no longer consulted -- `/` is now a real
  // routable home page, not a one-time onboarding flash.
  const [showWelcome, setShowWelcome] = useState<boolean>(
    () => readPathTab() === null
  );

  // Tab setter that also pushes the new path into history. Wrapped so
  // every callsite (Sidebar, CommandPalette, Welcome CTAs) updates the
  // URL automatically. Uses pushState so back/forward navigates between
  // tabs. setShowWelcome(false) is called here so any tab navigation
  // automatically dismisses the welcome overlay.
  const setActiveTab = (next: string) => {
    setActiveTabState(next);
    setShowWelcome(false);
    if (typeof window !== "undefined") {
      const desired = TAB_TO_PATH[next] || `/${next}`;
      if (window.location.pathname !== desired) {
        window.history.pushState(null, "", desired);
      }
    }
  };

  // Navigate to the home page (welcome screen). Sidebar logo uses this.
  const goHome = () => {
    setShowWelcome(true);
    if (typeof window !== "undefined" && window.location.pathname !== "/") {
      window.history.pushState(null, "", "/");
    }
  };

  // Listen for popstate (back/forward button, manual URL edit) and
  // reflect the new path into state.
  useEffect(() => {
    const onPop = () => {
      const tab = readPathTab();
      if (tab) {
        setActiveTabState(tab);
        setShowWelcome(false);
      } else {
        setShowWelcome(true);
      }
    };
    window.addEventListener("popstate", onPop);
    return () => window.removeEventListener("popstate", onPop);
  }, []);

  const reduceMotion = useReducedMotion();
  // Page-tab fade-in: each TabsContent's children are wrapped in a
  // motion.div that fades in from opacity 0 → 1 on mount. Radix unmounts
  // the inactive tab's children, so switching tabs is a natural unmount
  // + remount — and the new motion.div's `initial → animate` is the
  // fade. Reduced-motion resolves to instant.
  const panelInitial = reduceMotion ? { opacity: 1 } : { opacity: 0 };
  const panelAnimate = { opacity: 1 };
  const panelTransition = { duration: reduceMotion ? 0 : 0.2, ease: "easeOut" as const };

  // -------------------------------------------------------------------------
  // M1 — research-streaming signal for the masthead dateline.
  //
  // ResearchMode dispatches a window-scoped "techpulse:research-stream"
  // CustomEvent whenever its phase changes; the masthead listens for it
  // and toggles between LIVE (signal color + blinking cursor) and FILED
  // (muted). Loose pub/sub keeps the masthead and ResearchMode fully
  // decoupled — no context provider or prop drilling required.
  // -------------------------------------------------------------------------
  const [isResearchStreaming, setIsResearchStreaming] = useState(false);
  useEffect(() => {
    const onStreamChange = (e: Event) => {
      const ev = e as CustomEvent<{ active: boolean }>;
      setIsResearchStreaming(Boolean(ev.detail?.active));
    };
    window.addEventListener(
      "techpulse:research-stream",
      onStreamChange as EventListener
    );
    return () =>
      window.removeEventListener(
        "techpulse:research-stream",
        onStreamChange as EventListener
      );
  }, []);

  // -------------------------------------------------------------------------
  // Data fetchers (unchanged from M2 — behavior is out of scope for M3.M1).
  // -------------------------------------------------------------------------
  const fetchArticles = async () => {
    try {
      setLoading(true);
      const params = new URLSearchParams();
      params.append("page", "1");
      params.append("page_size", "50");

      if (selectedCategories.length > 0) {
        for (const cat of selectedCategories) {
          if (cat && cat.trim()) {
            params.append("category", cat);
          }
        }
      }
      if (searchQuery) {
        params.append("author", searchQuery);
      }

      const data = await apiFetch<any>(`${API_ENDPOINTS.news}?${params}`);
      console.log("API Response:", data);

      const articles = data.data || data.items || [];
      const buildSummaries = (a: any): { summaryShort: string; summaryMedium: string } => {
        // Prefer the longer of `summary` vs `content` so cards feel
        // substantive even when the backend's `summary` field is a one-line
        // teaser. Falls back to either if only one is present.
        const summary = (a.summary || "").toString().trim();
        const content = (a.content || "").toString().trim();
        const body = content.length > summary.length * 1.5 ? content : (summary || content);
        if (!body) {
          return { summaryShort: "", summaryMedium: "" };
        }
        // Bumped from 200 -> 280 chars so the 2-3 line summary preview
        // actually fills the line-clamp-3 box on cards. Medium stays at
        // 800 for the expanded "Read more" view.
        const short =
          body.length > 280 ? body.slice(0, 280).trimEnd() + "..." : body;
        const medium =
          body.length > 800 ? body.slice(0, 800).trimEnd() + "..." : body;
        return { summaryShort: short, summaryMedium: medium };
      };
      const mappedArticles =
        articles.map((article: any) => {
          const { summaryShort, summaryMedium } = buildSummaries(article);
          return {
            id: article.id,
            title: article.title,
            content: article.content,
            summaryShort,
            summaryMedium,
            url: article.url,
            publishedAt: article.published_at,
            // Polish iter (design-review #9): pass the raw image_url
            // through without an unconditional placeholder fallback.
            // Card components decide their own no-image rendering --
            // LeadStoryCard drops the hero image slot entirely when
            // missing; the secondary NewsCard keeps a minimal grey
            // placeholder for grid alignment.
            imageUrl: article.image_url || "",
            category: article.categories || [],
            source: article.source,
            credibilityScore: 85,
            trending: false,
            sentiment: "neutral",
            keyInsights: [],
            sourcesUsed: [article.source],
          };
        }) || [];

      setArticles(mappedArticles);
      setFilteredArticles(mappedArticles);
    } catch (error) {
      console.error("Error fetching articles:", error);
      toast.error("Failed to fetch articles. Please try again.");
    } finally {
      setLoading(false);
    }
  };

  const fetchStats = async () => {
    try {
      const envelope = await apiFetch<any>(API_ENDPOINTS.newsStats);
      const data = envelope?.data ?? envelope;
      const recent = Number(data?.recent_articles ?? 0);
      const total = Number(data?.total_articles ?? 0);
      setTotalArticleCount(recent > 0 ? recent : total);
    } catch (error) {
      console.error("Error fetching stats:", error);
    }
  };

  const fetchDigest = async () => {
    try {
      const data = await apiFetch<any>(API_ENDPOINTS.digest);
      setDigest(data);
    } catch (error) {
      console.error("Error fetching digest:", error);
      toast.error("Failed to fetch digest. Please try again.");
    }
  };

  // Polish iter 3 / Part C — pull the three new digest panels. Each is
  // independent so a slow LLM doesn't block the curated/topics renders.
  const fetchDailySummary = async () => {
    setDailySummaryLoading(true);
    try {
      const data = await apiFetch<any>(API_ENDPOINTS.digestDailySummary);
      setDailySummary(data);
    } catch (error) {
      console.error("Error fetching daily summary:", error);
      // No toast — the hero card just stays hidden on failure.
    } finally {
      setDailySummaryLoading(false);
    }
  };

  const fetchCuratedHeadlines = async () => {
    try {
      const data = await apiFetch<any>(API_ENDPOINTS.digestCurated);
      setCuratedHeadlines(
        Array.isArray(data?.headlines) ? data.headlines : []
      );
    } catch (error) {
      console.error("Error fetching curated headlines:", error);
      setCuratedHeadlines([]);
    }
  };

  const fetchTopicClusters = async () => {
    try {
      const data = await apiFetch<any>(API_ENDPOINTS.digestTopics);
      setTopicClusters(Array.isArray(data?.topics) ? data.topics : []);
    } catch (error) {
      console.error("Error fetching topic clusters:", error);
      setTopicClusters([]);
    }
  };

  const savePreferences = async () => {
    setIsSavingPreferences(true);
    try {
      const body = {
        categories: selectedCategories,
        view_mode: viewMode,
        show_trending_only: showTrendingOnly,
      };

      const envelope = await apiFetch<any>(API_ENDPOINTS.settings, {
        method: "PUT",
        body: JSON.stringify(body),
      });
      const saved = envelope?.data ?? envelope;

      const persistedCategories: string[] = Array.isArray(saved?.categories)
        ? saved.categories
        : selectedCategories;
      setSavedCategories([...persistedCategories]);
      setHasUnsavedChanges(false);

      try {
        localStorage.setItem(
          "techpulse_categories",
          JSON.stringify(persistedCategories)
        );
      } catch {
        // Best-effort cache; ignore quota / privacy-mode failures.
      }

      toast.success("Preferences saved successfully!", {
        description: `Your feed will now show ${persistedCategories.length} selected topic${persistedCategories.length !== 1 ? "s" : ""}.`,
        duration: 3000,
      });

      await fetchArticles();
    } catch (error) {
      console.error("Error saving preferences:", error);
      toast.error("Failed to save preferences", {
        description: "Please try again later.",
        duration: 3000,
      });
    } finally {
      setIsSavingPreferences(false);
    }
  };

  useEffect(() => {
    const loadData = async () => {
      try {
        const envelope = await apiFetch<any>(API_ENDPOINTS.settings);
        const data = envelope?.data ?? envelope;
        if (data && typeof data === "object") {
          if (Array.isArray(data.categories)) {
            setSelectedCategories(data.categories);
            setSavedCategories(data.categories);
            try {
              localStorage.setItem(
                "techpulse_categories",
                JSON.stringify(data.categories)
              );
            } catch {
              // Ignore cache write failures.
            }
          }
          if (data.view_mode === "compact" || data.view_mode === "detailed") {
            setViewMode(data.view_mode);
          }
          if (typeof data.show_trending_only === "boolean") {
            setShowTrendingOnly(data.show_trending_only);
          }
        }
      } catch (backendError) {
        console.warn(
          "Backend settings unreachable; falling back to localStorage cache",
          backendError
        );
        try {
          const saved = localStorage.getItem("techpulse_categories");
          if (saved) {
            const cats = JSON.parse(saved);
            if (Array.isArray(cats)) {
              setSelectedCategories(cats);
              setSavedCategories(cats);
            }
          }
        } catch (cacheError) {
          console.error("Error loading preferences from cache:", cacheError);
        }
      }

      fetchArticles();
      fetchDigest();
      fetchStats();
      // Polish iter 3 / Part C — kick off the three new digest fetches in
      // parallel. Daily-summary may take 20-60s on cache miss, the others
      // are cheap DB reads.
      fetchDailySummary();
      fetchCuratedHeadlines();
      fetchTopicClusters();
    };

    loadData();
  }, []);

  useEffect(() => {
    const categoriesChanged =
      JSON.stringify(selectedCategories.sort()) !==
      JSON.stringify(savedCategories.sort());
    setHasUnsavedChanges(categoriesChanged);
  }, [selectedCategories, savedCategories]);

  useEffect(() => {
    fetchArticles();
  }, [selectedCategories, searchQuery, showTrendingOnly]);

  // Polish iter 3 / Part D — Apply the entity chip filter client-side.
  //
  // When the user toggles an entity chip in the TrendingRail, we add the
  // entity name to ``selectedEntities``. Filtering is approximate: an
  // article "mentions" an entity iff its title or summaryShort/summaryMedium
  // contains the entity name as a case-insensitive substring. This v1
  // doesn't consult the knowledge-graph's tracked mentions, so it may miss
  // articles that mention the entity only in the article body. The accuracy
  // hit is acceptable here because the chips are a discovery affordance, not
  // a precise query interface.
  //
  // If no entity chips are active, the filter is a no-op and we display
  // every article returned by the backend query.
  useEffect(() => {
    if (selectedEntities.length === 0) {
      setFilteredArticles(articles);
      return;
    }
    const needles = selectedEntities.map((e) => e.toLowerCase());
    const next = articles.filter((article: any) => {
      const haystack = [
        article.title,
        article.summaryShort,
        article.summaryMedium,
        article.content,
      ]
        .filter(Boolean)
        .join(" ")
        .toLowerCase();
      // OR-match across entities — clicking two chips broadens the filter.
      return needles.some((n) => haystack.includes(n));
    });
    setFilteredArticles(next);
  }, [articles, selectedEntities]);

  // -------------------------------------------------------------------------
  // Render — sidebar + main pane inside a controlled Radix Tabs root.
  // -------------------------------------------------------------------------
  return (
    <Tabs
      value={activeTab}
      onValueChange={setActiveTab}
      className="min-h-screen flex flex-row bg-background text-foreground"
    >
      {/* Skip-to-content link (design-review #14). Hidden until
          focused; appears as a high-contrast mono pill in the top-
          left corner so keyboard users can jump past the sidebar
          and masthead. Anchored to ``#main-content`` which lives on
          the <main> below. */}
      <a
        href="#main-content"
        className="sr-only focus:not-sr-only fixed top-2 left-2 z-50 bg-foreground text-background px-3 py-1 font-mono-tx text-[12px] uppercase-eyebrow"
      >
        [ skip to main ]
      </a>
      <CommandPaletteProvider activeTab={activeTab} onSelectTab={setActiveTab}>
        <Sidebar
          activeTab={activeTab}
          onGoHome={goHome}
          badges={hasUnsavedChanges ? { preferences: "unsaved" } : undefined}
        />

        <main
          id="main-content"
          data-slot="main-content"
          className="flex-1 min-w-0 flex flex-col overflow-x-hidden"
        >
          {/* M1 masthead — broadsheet two-row composition.
              Row 1: mono dateline (TECHPULSE / VOL III / NO. <day> / DATE / LIVE-FILED)
              Row 2: Fraunces 32px display headline + terminal-pill stats.

              The <h1>'s accessible name MUST remain "TechPulse AI" so
              `getByRole("heading", { name: /TechPulse AI/i })` keeps
              binding across 35+ Playwright tests. We solve that with an
              aria-label on the h1 PLUS a visually-hidden <span>, while
              the visible glyphs render the editorial line that's marked
              aria-hidden so the screen reader doesn't double-up. */}
          <header className="border-b border-[var(--rule)] bg-background sticky top-0 z-10">
            {/* Row 1 — dateline. Mono uppercase eyebrow band. */}
            <div className="border-b border-[var(--rule)] px-6 py-2 flex items-center justify-between font-mono-tx text-[11px] uppercase-eyebrow">
              <span>TECHPULSE</span>
              <span className="flex items-center gap-3">
                {(() => {
                  const now = new Date();
                  const startOfYear = new Date(now.getFullYear(), 0, 0);
                  const dayOfYear = Math.floor(
                    (now.getTime() - startOfYear.getTime()) / 86400000
                  );
                  const dateline = now
                    .toLocaleDateString("en-US", {
                      weekday: "short",
                      day: "2-digit",
                      month: "short",
                      year: "numeric",
                    })
                    .toUpperCase()
                    .replace(/,/g, "");
                  return (
                    <>
                      <span>VOL III · NO. {dayOfYear}</span>
                      <span>{dateline}</span>
                    </>
                  );
                })()}
                {isResearchStreaming ? (
                  <span className="text-signal live-cursor">LIVE</span>
                ) : (
                  <span className="text-foreground-soft">FILED</span>
                )}
              </span>
            </div>
            {/* Row 2 — headline + stat pills. */}
            <div className="px-6 py-4 flex items-end justify-between gap-6">
              <h1
                className="font-display text-[32px] tracking-tight leading-[1.05] text-foreground"
                aria-label="TechPulse AI"
              >
                <span className="sr-only">TechPulse AI</span>
                <span aria-hidden>Tech intelligence,</span>
                <br />
                <em aria-hidden className="text-foreground-soft font-display italic">
                  from the agentic desk.
                </em>
              </h1>
              {/* Masthead stat chips. Polish iter (design-review
                  #8): bump text from ``text-foreground-soft`` to the
                  full ``text-foreground`` so light-mode chips clear
                  WCAG AA on a cream background, and tint the integer
                  count with the signal accent so the eye lands on the
                  number rather than the bracket frame. */}
              <div className="flex items-center gap-2 pb-1">
                <span className="border border-[var(--rule)] px-2 py-0.5 font-mono-tx text-[11px] text-foreground">
                  [ <span aria-hidden>🔥 </span>
                  <span className="text-signal tabular-nums">
                    {articles.filter((a) => a.trending).length}
                  </span>{" "}
                  trending ]
                </span>
                <span className="border border-[var(--rule)] px-2 py-0.5 font-mono-tx text-[11px] text-foreground">
                  [{" "}
                  <span className="text-signal tabular-nums">
                    {totalArticleCount || articles.length}
                  </span>{" "}
                  today ]
                </span>
              </div>
            </div>
          </header>

          <div className="px-6 py-6 flex-1">
            {/* First-load welcome screen -- shown until the user
                dismisses it via one of the CTAs. While visible we hide
                ALL tab content via a wrapper div so Radix's tablist
                stays intact (preserves a11y) but nothing else renders
                in the main pane. */}
            {showWelcome && (
              <WelcomeScreen
                onTryResearch={() => {
                  setActiveTab("research");
                }}
                onBrowseFeed={() => {
                  setActiveTab("feed");
                }}
                onSkip={() => {
                  setActiveTab("feed");
                }}
              />
            )}

            <div style={{ display: showWelcome ? "none" : "contents" }}>
            {/* Page-tab cross-fade — every TabsContent's children are
                wrapped in a motion.div that fades in on mount. Radix
                unmounts the inactive tab's children, so switching tabs
                triggers a fresh mount + fade-in for the new panel. No
                AnimatePresence required because there's nothing to
                animate out (Radix removes the old children
                instantly). Reduced-motion resolves to instant. */}
            {/* News Feed Tab */}
            <TabsContent value="feed" className="space-y-5 mt-0">
              <motion.div
                initial={panelInitial}
                animate={panelAnimate}
                transition={panelTransition}
                className="space-y-5"
              >
              {/* News-feed toolbar -- terminal pills. Search input keeps its
                  existing skin (M3 will revisit), trending/view toggles are
                  recast as mono [ ] / [+] pills. */}
              <div className="flex flex-col md:flex-row gap-3 items-start md:items-center justify-between">
                <div className="flex-1 w-full md:max-w-md">
                  <SearchBar onSearch={setSearchQuery} />
                </div>
                <div className="flex gap-2 items-center font-mono-tx text-[11px] uppercase-eyebrow">
                  <button
                    type="button"
                    onClick={() => setShowTrendingOnly(!showTrendingOnly)}
                    aria-pressed={showTrendingOnly}
                    className={[
                      "inline-flex items-center gap-1.5 px-2 py-1 border transition-colors",
                      showTrendingOnly
                        ? "border-[var(--rule)] text-signal"
                        : "border-[var(--rule)] text-foreground-soft hover:text-foreground",
                    ].join(" ")}
                  >
                    <TrendingUp className="w-3 h-3" />
                    {showTrendingOnly ? "[ trending ]" : "[ trending ]"}
                  </button>
                  <div className="inline-flex border border-[var(--rule)]">
                    <button
                      type="button"
                      onClick={() => setViewMode("detailed")}
                      aria-pressed={viewMode === "detailed"}
                      className={[
                        "inline-flex items-center px-2 py-1 transition-colors",
                        viewMode === "detailed"
                          ? "bg-[var(--background-tint)] text-signal"
                          : "text-foreground-soft hover:text-foreground",
                      ].join(" ")}
                    >
                      <Grid className="w-3 h-3" />
                    </button>
                    <button
                      type="button"
                      onClick={() => setViewMode("compact")}
                      aria-pressed={viewMode === "compact"}
                      className={[
                        "inline-flex items-center px-2 py-1 border-l border-[var(--rule)] transition-colors",
                        viewMode === "compact"
                          ? "bg-[var(--background-tint)] text-signal"
                          : "text-foreground-soft hover:text-foreground",
                      ].join(" ")}
                    >
                      <List className="w-3 h-3" />
                    </button>
                  </div>
                </div>
              </div>

              {/* Polish iter 3 / Part D — Trending Now rail. Now driven by
                  the knowledge-graph trending-entities endpoint (top entities
                  this week). Clicking a chip toggles the entity in
                  ``selectedEntities``, which then drives a client-side
                  substring filter over the loaded article list. */}
              <TrendingRail
                selectedCategories={selectedEntities}
                onSelectCategory={(entity) => {
                  setSelectedEntities((prev) =>
                    prev.includes(entity)
                      ? prev.filter((c) => c !== entity)
                      : [...prev, entity]
                  );
                }}
              />

              {(selectedCategories.length > 0 || selectedEntities.length > 0) && (
                <div
                  data-testid="news-feed-active-filters"
                  className="flex flex-wrap gap-2 items-center border-t border-b border-[var(--rule)] py-2 font-mono-tx text-[11px] uppercase-eyebrow text-foreground-soft"
                >
                  <span className="mr-2">filtered &#9656;</span>
                  {/* The inner <span> carrying just the raw `cat` text
                      keeps the e2e contract intact: news-feed.spec.ts asserts
                      `activeFilters.getByText(chipCategory, { exact: true })`,
                      which matches an element whose textContent equals the
                      value exactly. Bracket decoration lives in aria-hidden
                      sibling spans so the visual "[ AI ]" survives. */}
                  {selectedCategories.map((cat) => (
                    <span
                      key={`cat-${cat}`}
                      className="px-1.5 py-0.5 border border-[var(--rule)] text-foreground"
                    >
                      <span aria-hidden="true">[&nbsp;</span>
                      <span>{cat}</span>
                      <span aria-hidden="true">&nbsp;]</span>
                    </span>
                  ))}
                  {selectedEntities.map((ent) => (
                    <span
                      key={`ent-${ent}`}
                      className="px-1.5 py-0.5 border border-[var(--rule)] text-signal"
                    >
                      <span aria-hidden="true">[&nbsp;</span>
                      <span>{ent}</span>
                      <span aria-hidden="true">&nbsp;]</span>
                    </span>
                  ))}
                  <button
                    type="button"
                    onClick={() => {
                      setSelectedCategories([]);
                      setSelectedEntities([]);
                    }}
                    className="ml-auto hover:text-signal"
                  >
                    Clear Filters &#215;
                  </button>
                </div>
              )}

              {/* News-feed body -- asymmetric 12-col broadsheet composition
                  in detailed view, single-column mono list in compact view.
                  Lead story always renders first so the LeadStoryCard sits
                  before any secondary NewsCard in the DOM (this matters for
                  the news-feed.spec.ts "Linear-dense" assertion -- see
                  NewsCard.tsx header for the full explanation). */}
              {loading ? (
                <div className="flex items-center justify-center py-12">
                  <Loader2 className="w-8 h-8 animate-spin text-primary" />
                </div>
              ) : filteredArticles.length === 0 ? (
                <div
                  data-testid="news-feed-list"
                  className="text-center py-12 border-t border-b border-[var(--rule)] space-y-3"
                >
                  <Newspaper className="w-12 h-12 text-foreground mx-auto" />
                  <h3 className="font-display text-[22px] font-medium text-foreground">No articles found</h3>
                  <p className="text-[14px] text-foreground-soft">
                    Try adjusting your filters or search query
                  </p>
                  <Button
                    onClick={() => {
                      setSearchQuery("");
                      setShowTrendingOnly(false);
                      setSelectedCategories([]);
                      setSelectedEntities([]);
                    }}
                  >
                    Reset Filters
                  </Button>
                </div>
              ) : viewMode === "detailed" ? (
                <div data-testid="news-feed-list" className="space-y-6">
                  {/* Lead + deck -- 12-col grid. Lead spans cols 1-8 with a
                      16:9 image and a 44px Fraunces headline; the deck of up
                      to 3 secondary cards stacks in cols 9-12. */}
                  <div className="grid grid-cols-12 gap-6">
                    <div className="col-span-12 lg:col-span-8">
                      <LeadStoryCard article={filteredArticles[0]} />
                    </div>
                    {filteredArticles.length > 1 && (
                      <div className="col-span-12 lg:col-span-4 flex flex-col">
                        {filteredArticles.slice(1, 4).map((article) => (
                          <NewsCard
                            key={article.id}
                            article={article}
                            viewMode="detailed"
                          />
                        ))}
                      </div>
                    )}
                  </div>
                  {/* Section break -- tick-rule with mono "more" label. Only
                      rendered when there are remainder articles. */}
                  {filteredArticles.length > 4 && (
                    <>
                      <div className="flex items-center gap-3">
                        <span className="font-mono-tx text-[11px] uppercase-eyebrow text-foreground-soft">more</span>
                        <div className="tick-rule flex-1" />
                      </div>
                      <div className="grid grid-cols-1 lg:grid-cols-3 gap-6">
                        {filteredArticles.slice(4).map((article) => (
                          <NewsCard
                            key={article.id}
                            article={article}
                            viewMode="detailed"
                          />
                        ))}
                      </div>
                    </>
                  )}
                </div>
              ) : (
                /* Compact view -- single-column mono list. Each row is a
                   timestamp + a Fraunces 18px title (hover -> signal) + a
                   mono source name on the right. No images, no chrome. */
                <div data-testid="news-feed-list" className="border-t border-[var(--rule)]">
                  {filteredArticles.map((article) => {
                    const date = new Date(article.publishedAt);
                    const hours = Math.floor(
                      (Date.now() - date.getTime()) / (1000 * 60 * 60)
                    );
                    const stamp =
                      hours < 1
                        ? "just now"
                        : hours < 24
                          ? `${hours}h ago`
                          : `${Math.floor(hours / 24)}d ago`;
                    return (
                      <div
                        key={article.id}
                        data-slot="card"
                        data-testid="news-card"
                        className="flex items-baseline gap-3 py-3 px-3 border-b border-[var(--rule)] hover:bg-[var(--background-tint)] transition-colors"
                      >
                        <span className="font-mono-tx text-[11px] uppercase-eyebrow text-foreground-soft w-24 shrink-0">
                          {stamp}
                        </span>
                        <a
                          href={article.url}
                          target="_blank"
                          rel="noopener noreferrer"
                          data-slot="card-title"
                          className="font-display text-[18px] leading-snug text-foreground hover:text-signal flex-1"
                        >
                          {article.title}
                        </a>
                        <span className="font-mono-tx text-[11px] uppercase-eyebrow text-foreground-soft text-gray-500">
                          {article.source}
                        </span>
                      </div>
                    );
                  })}
                </div>
              )}
              </motion.div>
            </TabsContent>

            {/* Research Mode Tab — unchanged in M1; M2 will polish content. */}
            <TabsContent value="research" className="mt-0">
              <motion.div
                initial={panelInitial}
                animate={panelAnimate}
                transition={panelTransition}
              >
                <ResearchMode />
              </motion.div>
            </TabsContent>

            {/* Knowledge Graph Tab */}
            <TabsContent value="knowledge" className="mt-0">
              <motion.div
                initial={panelInitial}
                animate={panelAnimate}
                transition={panelTransition}
              >
                <KnowledgeGraph />
              </motion.div>
            </TabsContent>

            {/* Daily Digest Tab */}
            <TabsContent value="digest" className="mt-0">
              <motion.div
                initial={panelInitial}
                animate={panelAnimate}
                transition={panelTransition}
              >
                {digest ? (
                  <DigestView
                    digest={digest}
                    dailySummary={dailySummary}
                    dailySummaryLoading={dailySummaryLoading}
                    curatedHeadlines={curatedHeadlines}
                    topicClusters={topicClusters}
                  />
                ) : (
                  <div className="flex items-center justify-center py-12">
                    <Loader2 className="w-8 h-8 animate-spin text-primary" />
                  </div>
                )}
              </motion.div>
            </TabsContent>

            {/* Saved Research Tab — M3.M5. Lists every persisted
                research report, opens them inline via MarkdownReport,
                and supports per-row deletion. */}
            <TabsContent value="saved" className="mt-0">
              <motion.div
                initial={panelInitial}
                animate={panelAnimate}
                transition={panelTransition}
              >
                <SavedResearchList />
              </motion.div>
            </TabsContent>

            {/* Preferences (Settings) Tab — M3.M4: theme + density toggles
                above the existing topic-preferences card. */}
            <TabsContent value="preferences" className="mt-0">
              <motion.div
                initial={panelInitial}
                animate={panelAnimate}
                transition={panelTransition}
                className="max-w-4xl mx-auto"
              >
                <Settings
                  selectedCategories={selectedCategories}
                  onCategoriesChange={setSelectedCategories}
                  onSave={savePreferences}
                  isSaving={isSavingPreferences}
                  hasUnsavedChanges={hasUnsavedChanges}
                />
              </motion.div>
            </TabsContent>
            </div>
          </div>

          {/* Toast Notifications */}
          <Toaster position="bottom-right" />

          {/* M1 footer — single hairline + mono colophon. */}
          <footer className="border-t border-[var(--rule)] mt-8">
            <div className="px-6 py-3 font-mono-tx text-[11px] uppercase-eyebrow text-foreground-soft flex justify-between">
              <span>— end of issue — set in fraunces &amp; ibm plex</span>
              <span>© techpulse 2026 · agentic desk</span>
            </div>
          </footer>
        </main>
      </CommandPaletteProvider>
    </Tabs>
  );
}

/**
 * Top-level App — wraps the shell in ThemeProvider so the rest of the app
 * (including the inline-bootstrap-set `<html class="dark">`) shares one
 * source of truth for the current theme.
 */
export default function App() {
  return (
    <ThemeProvider>
      <AppShell />
    </ThemeProvider>
  );
}
