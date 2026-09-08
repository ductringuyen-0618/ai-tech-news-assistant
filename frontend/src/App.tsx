import { useState, useEffect, useRef } from "react";
import { motion, useReducedMotion } from "framer-motion";
import { Tabs, TabsContent } from "./components/ui/tabs";
import { Button } from "./components/ui/button";
import { Badge } from "./components/ui/badge";
import { Toaster } from "./components/ui/sonner";
import { toast } from "sonner";
import { Settings } from "./components/Settings";
import { SearchBar } from "./components/SearchBar";
import { DigestView } from "./components/DigestView";
import { TrendingRail } from "./components/TrendingRail";
import { ResearchMode } from "./components/ResearchMode";
import { SavedResearchList } from "./components/SavedResearchList";
import SavedArticlesList from "./components/SavedArticlesList";
import UnifiedFeedView from "./components/UnifiedFeedView";
import ArticleReader from "./components/ArticleReader";
import { ThemeProvider } from "./components/ThemeProvider";
import { CommandPaletteProvider } from "./components/CommandPalette";
import { Sidebar } from "./components/Sidebar";
import {
  Newspaper,
  TrendingUp,
  Loader2,
  Grid,
  List,
} from "lucide-react";
import { API_ENDPOINTS, apiFetch } from "./config/api";
import { useUrlSearchState } from "./hooks/useUrlSearchState";

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
  // Infinite-scroll state for the News Feed tab (Facebook-style: cursor
  // into the DB, appended as the user scrolls near the bottom).
  const [feedCursor, setFeedCursor] = useState<string | null>(null);
  const [hasMoreFeed, setHasMoreFeed] = useState<boolean>(true);
  const [loadingMore, setLoadingMore] = useState<boolean>(false);
  // Search query + topic filters are persisted into the URL
  // (?q=...&topics=...) via useUrlSearchState so a search/filter is
  // shareable and survives a refresh. Seed searchQuery/selectedCategories
  // from whatever was in the URL at mount; a ref remembers whether the
  // URL specified topics so the backend-settings loader below (which
  // wants to write selectedCategories too) doesn't clobber a shared link.
  const [urlSearchState, setUrlSearchState] = useUrlSearchState();
  const urlHadTopicsAtMount = useRef(urlSearchState.topics.length > 0);
  const lastAppliedUrlSearchState = useRef(urlSearchState);
  // Start with no category filters so the News Feed shows every ingested
  // article on first load (unless the URL says otherwise). Previously we
  // pre-applied ["AI", "Machine Learning"] which hid every article whose
  // RSS categories didn't include those exact strings -- 'No articles
  // found' on a fully-populated DB.
  const [selectedCategories, setSelectedCategories] = useState<string[]>(
    () => urlSearchState.topics
  );
  // Entity filter lens -- knowledge-graph entities (companies, people,
  // etc.) the user has selected, either by chip-toggling the TrendingRail
  // or by choosing "View in Feed" from a Knowledge Graph entity. Sent to
  // the backend as repeatable ?entity_id= params, OR-ed together, and
  // joined against the real entity_mentions table -- this replaced an
  // older client-side title/summary substring match that could miss
  // mentions buried in the article body (or loaded feed pages that
  // hadn't been scrolled to yet under infinite scroll).
  const [selectedEntities, setSelectedEntities] = useState<
    { id: number; name: string }[]
  >([]);
  const [searchQuery, setSearchQuery] = useState(() => urlSearchState.q);
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
  // "New since you last visited" -- the newest article timestamp seen as
  // of the *previous* visit, read once at mount before we stamp today's
  // newest timestamp back into localStorage. Used only to compute a count
  // for the banner above the feed; never touched again this session.
  const LAST_SEEN_KEY = "techpulse-last-seen-timestamp";
  // Read once at mount and never updated again this session -- the
  // freshest timestamp gets written straight to localStorage (see the
  // effect below) without needing to flow back through state.
  const [lastSeenTimestamp] = useState<number | null>(() => {
    try {
      const raw = localStorage.getItem(LAST_SEEN_KEY);
      return raw ? Number(raw) : null;
    } catch {
      return null;
    }
  });
  // "Scroll for more ↓" affordance -- shown once per browser until
  // dismissed (manually, or automatically the first time infinite scroll
  // actually fires), since there's no other visual signal that the feed
  // keeps loading as you scroll.
  const SCROLL_HINT_KEY = "techpulse-scroll-hint-dismissed";
  const [scrollHintDismissed, setScrollHintDismissed] = useState<boolean>(
    () => {
      try {
        return localStorage.getItem(SCROLL_HINT_KEY) === "1";
      } catch {
        return false;
      }
    }
  );
  const dismissScrollHint = () => {
    setScrollHintDismissed(true);
    try {
      localStorage.setItem(SCROLL_HINT_KEY, "1");
    } catch {
      // Best-effort; ignore quota / privacy-mode failures.
    }
  };
  // Article reader overlay -- `/article/:id` client-side route. Driven by
  // its own bit of state (rather than folding into `activeTab`) since the
  // reader opens *on top of* whichever tab was active, not instead of it.
  const readArticleIdFromPath = (): string | null => {
    if (typeof window === "undefined") return null;
    const m = window.location.pathname.match(/^\/article\/([^/]+)\/?$/);
    return m ? decodeURIComponent(m[1]) : null;
  };
  const [readerArticleId, setReaderArticleId] = useState<string | null>(() =>
    readArticleIdFromPath()
  );
  const openArticleReader = (articleId: string) => {
    setReaderArticleId(articleId);
    if (typeof window !== "undefined") {
      window.history.pushState(null, "", `/article/${encodeURIComponent(articleId)}`);
    }
  };
  const closeArticleReader = () => {
    setReaderArticleId(null);
    if (typeof window !== "undefined" && readArticleIdFromPath()) {
      const desired = TAB_TO_PATH[activeTab] || `/${activeTab}`;
      window.history.pushState(null, "", desired);
    }
  };
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
  //   /digest      -> Daily Digest
  //   /saved       -> Saved Research
  //   /settings    -> Settings (renamed from /preferences for shorter URL)
  //
  // Deployment note: any SPA-fallback dev/prod server is required so
  // refreshing /research returns index.html (Vite dev does this by
  // default; production needs a catch-all route in the static host).
  // "knowledge" removed -- the canvas graph tab was cut; entity filtering
  // now lives in SearchBar's onSelectEntity dropdown. Any old /knowledge
  // bookmark falls through readPathTab's `|| null` -> defaults to feed.
  const VALID_TABS = ["feed", "research", "digest", "saved", "preferences"] as const;
  // Internal tab id -> URL path segment. Most are identical; preferences
  // maps to /settings because that's the user-facing label and the
  // shorter URL reads better.
  const TAB_TO_PATH: Record<string, string> = {
    feed: "/feed",
    research: "/research",
    digest: "/digest",
    saved: "/saved",
    preferences: "/settings",
  };
  const PATH_TO_TAB: Record<string, string> = {
    feed: "feed",
    research: "research",
    digest: "digest",
    saved: "saved",
    settings: "preferences",
    // Backwards-compat: keep /preferences working for any old bookmarks.
    preferences: "preferences",
  };
  // No welcome/splash screen -- "/" and any unrecognized path land
  // straight on the News Feed tab.
  const readPathTab = (): string | null => {
    if (typeof window === "undefined") return null;
    const seg = window.location.pathname.replace(/^\/+/, "").split("/")[0];
    if (!seg) return null; // "/" -> feed
    return PATH_TO_TAB[seg] || null;
  };
  const [activeTab, setActiveTabState] = useState<string>(
    () => readPathTab() || "feed"
  );

  // Tab setter that also pushes the new path into history. Wrapped so
  // every callsite (Sidebar, CommandPalette) updates the URL
  // automatically. Uses pushState so back/forward navigates between tabs.
  const setActiveTab = (next: string) => {
    setActiveTabState(next);
    if (typeof window !== "undefined") {
      const desired = TAB_TO_PATH[next] || `/${next}`;
      if (window.location.pathname !== desired) {
        window.history.pushState(null, "", desired);
      }
    }
  };

  // Navigate to the News Feed (home). Sidebar logo uses this.
  const goHome = () => {
    setActiveTab("feed");
  };

  // Listen for popstate (back/forward button, manual URL edit) and
  // reflect the new path into state.
  useEffect(() => {
    const onPop = () => {
      setActiveTabState(readPathTab() || "feed");
      setReaderArticleId(readArticleIdFromPath());
    };
    window.addEventListener("popstate", onPop);
    return () => window.removeEventListener("popstate", onPop);
  }, []);

  // Keep the URL's ?q=/?topics= in sync whenever the user changes the
  // search box or topic filters.
  useEffect(() => {
    setUrlSearchState({ q: searchQuery, topics: selectedCategories });
  }, [searchQuery, selectedCategories, setUrlSearchState]);

  // Reflect the URL back into the actual filter state -- only matters for
  // browser back/forward or a hand-edited URL (useUrlSearchState's own
  // popstate listener updates `urlSearchState`; the effect above already
  // no-ops when the values it would write are unchanged, so this can't
  // loop against it).
  useEffect(() => {
    const prev = lastAppliedUrlSearchState.current;
    const changed =
      urlSearchState.q !== prev.q ||
      urlSearchState.topics.length !== prev.topics.length ||
      urlSearchState.topics.some((t, i) => t !== prev.topics[i]);
    if (!changed) return;
    lastAppliedUrlSearchState.current = urlSearchState;
    setSearchQuery(urlSearchState.q);
    setSelectedCategories(urlSearchState.topics);
  }, [urlSearchState]);


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

  // Feed ordering: articles with an image sort first (newest first);
  // articles without one sink to the bottom (also newest first within
  // that group), so a missing image never bumps a story above ones that
  // have art.
  const sortArticles = (list: any[]): any[] => {
    return [...list].sort((a, b) => {
      const aHasImage = Boolean(a.imageUrl);
      const bHasImage = Boolean(b.imageUrl);
      if (aHasImage !== bHasImage) return aHasImage ? -1 : 1;
      return (
        new Date(b.publishedAt).getTime() - new Date(a.publishedAt).getTime()
      );
    });
  };

  // Raw API article -> the shape NewsCard/LeadStoryCard-era code expects.
  // Shared by the initial feed fetch and the infinite-scroll continuation
  // so both stay in sync.
  const mapApiArticle = (a: any) => {
    // Prefer the longer of `summary` vs `content` so cards feel
    // substantive even when the backend's `summary` field is a one-line
    // teaser. Falls back to either if only one is present.
    const summary = (a.summary || "").toString().trim();
    const content = (a.content || "").toString().trim();
    const body = content.length > summary.length * 1.5 ? content : (summary || content);
    // Bumped from 200 -> 280 chars so the 2-3 line summary preview
    // actually fills the line-clamp-3 box on cards. Medium stays at
    // 800 for the expanded "Read more" view.
    const summaryShort = !body
      ? ""
      : body.length > 280
        ? body.slice(0, 280).trimEnd() + "..."
        : body;
    const summaryMedium = !body
      ? ""
      : body.length > 800
        ? body.slice(0, 800).trimEnd() + "..."
        : body;
    return {
      id: a.id,
      title: a.title,
      content: a.content,
      summaryShort,
      summaryMedium,
      url: a.url,
      publishedAt: a.published_at,
      // Polish iter (design-review #9): pass the raw image_url through
      // without an unconditional placeholder fallback -- NewsCard omits
      // the image slot entirely when this is empty.
      imageUrl: a.image_url || "",
      category: a.categories || [],
      source: a.source,
      // Was a hardcoded 85 for every card regardless of the actual
      // article -- read whatever the backend sends (once/if a
      // `credibility_score` field lands on /api/news/) and fall back to
      // an honest, non-fake-precise default rather than a flat number
      // dressed up as a real score.
      credibilityScore: a.credibility_score ?? a.credibilityScore ?? 70,
      trending: false,
      sentiment: "neutral",
      keyInsights: [],
      sourcesUsed: [a.source],
      // Present only when a search query is active -- backend-computed
      // excerpt around the match (see article_repository/news routes).
      matchedSnippet: a.matched_snippet || undefined,
    };
  };

  // Query params shared between the initial feed fetch and the
  // infinite-scroll continuation -- keeps category/search filters
  // identical across both so a scroll-triggered page can't silently drift
  // from what's already on screen.
  const buildFeedParams = (pageSize: number): URLSearchParams => {
    const params = new URLSearchParams();
    params.append("page_size", String(pageSize));
    // The default browse view only shows articles with art (filtering
    // server-side means every page is full-sized instead of shrinking as
    // image-less rows get dropped client-side). But once someone is
    // actively searching or filtering by company, that restriction does
    // more harm than good: ~70% of articles matching a typical keyword
    // search have no scraped image, so forcing has_image=true made search
    // silently drop most real matches -- it looked like "search doesn't
    // find older news" when really it just couldn't find image-less news
    // at all, regardless of age.
    const isSearchingOrFiltering =
      Boolean(searchQuery) || selectedEntities.length > 0;
    if (!isSearchingOrFiltering) {
      params.append("has_image", "true");
    }
    if (selectedCategories.length > 0) {
      for (const cat of selectedCategories) {
        if (cat && cat.trim()) {
          params.append("category", cat);
        }
      }
    }
    if (searchQuery) {
      // Backend note: this used to be sent as `author`, which the API
      // validated but never actually applied to the query -- typing a
      // search term silently did nothing. `q` does a real title/content
      // substring match (see article_repository.list_articles).
      params.append("q", searchQuery);
    }
    for (const entity of selectedEntities) {
      params.append("entity_id", String(entity.id));
    }
    return params;
  };

  const FEED_PAGE_SIZE = 24;

  // -------------------------------------------------------------------------
  // Data fetchers (unchanged from M2 — behavior is out of scope for M3.M1).
  // -------------------------------------------------------------------------
  const fetchArticles = async () => {
    try {
      setLoading(true);
      setHasMoreFeed(true);
      const params = buildFeedParams(FEED_PAGE_SIZE);
      params.append("page", "1");

      const data = await apiFetch<any>(`${API_ENDPOINTS.news}?${params}`);
      console.log("API Response:", data);

      const rawArticles = data.data || data.items || [];
      const mapped = rawArticles.map(mapApiArticle);
      const sorted = sortArticles(mapped);
      setArticles(sorted);
      setFilteredArticles(sorted);

      const nextCursor = data.pagination?.next_cursor ?? null;
      setFeedCursor(nextCursor);
      setHasMoreFeed(Boolean(nextCursor));
    } catch (error) {
      console.error("Error fetching articles:", error);
      toast.error("Failed to fetch articles. Please try again.");
      setHasMoreFeed(false);
    } finally {
      setLoading(false);
    }
  };

  // Infinite-scroll continuation -- Facebook-style: fetch the next batch
  // by cursor and append, rather than re-fetching everything with a bigger
  // page_size. Guarded against overlapping calls (fast scrolling can fire
  // the observer more than once before a fetch resolves) and against
  // firing once the feed is exhausted.
  const fetchMoreArticles = async () => {
    if (loadingMore || !hasMoreFeed || !feedCursor) return;
    // Infinite scroll just fired for real -- the "scroll for more" hint
    // has done its job.
    dismissScrollHint();
    try {
      setLoadingMore(true);
      const params = buildFeedParams(FEED_PAGE_SIZE);
      params.append("cursor", feedCursor);

      const data = await apiFetch<any>(`${API_ENDPOINTS.news}?${params}`);
      const rawArticles = data.data || data.items || [];
      const mapped = rawArticles.map(mapApiArticle);

      setArticles((prev) => {
        const seen = new Set(prev.map((a) => a.id));
        const fresh = mapped.filter((a: any) => !seen.has(a.id));
        return [...prev, ...fresh];
      });

      const nextCursor = data.pagination?.next_cursor ?? null;
      setFeedCursor(nextCursor);
      setHasMoreFeed(Boolean(nextCursor));
    } catch (error) {
      console.error("Error fetching more articles:", error);
      // Don't toast here -- a failed background page-load shouldn't
      // interrupt someone mid-scroll. They can just scroll again to retry.
      setHasMoreFeed(false);
    } finally {
      setLoadingMore(false);
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
            // Don't clobber topic filters a shared/reloaded URL already
            // specified -- still track what's actually persisted server-
            // side via savedCategories so the unsaved-changes indicator
            // stays accurate.
            if (!urlHadTopicsAtMount.current) {
              setSelectedCategories(data.categories);
            }
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
  }, [selectedCategories, searchQuery, showTrendingOnly, selectedEntities]);

  // Stamp the newest article timestamp seen so the *next* visit can show
  // a "new since you were here" count. Keyed on `loading` flipping to
  // false (a full reload), not on `articles` directly, so appending pages
  // during infinite scroll doesn't re-stamp mid-session.
  useEffect(() => {
    if (loading || articles.length === 0) return;
    try {
      const newest = articles.reduce((max, a) => {
        const t = new Date(a.publishedAt).getTime();
        return Number.isFinite(t) && t > max ? t : max;
      }, 0);
      if (newest > 0) {
        localStorage.setItem(LAST_SEEN_KEY, String(newest));
      }
    } catch {
      // Best-effort; ignore quota / privacy-mode failures.
    }
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [loading]);

  // `filteredArticles` used to be a client-side post-filter (entity
  // substring match). Entity filtering now happens server-side (real
  // entity_mentions join, see buildFeedParams/fetchArticles), so this is
  // just a passthrough -- kept as its own state rather than removed
  // outright to avoid touching every downstream read of it.
  useEffect(() => {
    setFilteredArticles(articles);
  }, [articles]);

  // The default News Feed browse view only shows articles that have an
  // image -- image-less stories are hidden rather than shown as bare
  // text. That restriction is dropped while actively searching or
  // filtering by company (see buildFeedParams for why), so a real text
  // match without art still surfaces instead of being silently swallowed.
  // `articles`/`filteredArticles` themselves stay untouched either way so
  // Research, Digest, and Knowledge (which fetch independently) still see
  // every story regardless of image availability.
  const isSearchingOrFiltering =
    Boolean(searchQuery) || selectedEntities.length > 0;
  const visibleFeedArticles = isSearchingOrFiltering
    ? filteredArticles
    : filteredArticles.filter((a) => Boolean(a.imageUrl));

  // "New since you last visited" -- count of currently-visible articles
  // newer than the previous visit's newest-seen timestamp. Not shown
  // while actively searching/filtering (the count would be misleading --
  // it's about what's new in your feed, not in the filtered results) or
  // on the very first-ever visit (nothing to compare against yet).
  const newSinceLastVisitCount =
    lastSeenTimestamp == null || isSearchingOrFiltering
      ? 0
      : visibleFeedArticles.filter(
          (a) => new Date(a.publishedAt).getTime() > lastSeenTimestamp
        ).length;

  // Infinite scroll -- observe a sentinel just past the end of the feed
  // list and fetch the next cursor page once it enters the viewport.
  // Re-runs whenever the fetch guards change so the observer's closure
  // never calls a stale fetchMoreArticles. rootMargin front-loads the
  // fetch ~600px before the sentinel is actually visible so new cards
  // are ready before the user scrolls into blank space.
  const feedSentinelRef = useRef<HTMLDivElement | null>(null);
  useEffect(() => {
    const el = feedSentinelRef.current;
    if (!el || activeTab !== "feed" || !hasMoreFeed) return;
    const observer = new IntersectionObserver(
      (entries) => {
        if (entries[0]?.isIntersecting) {
          fetchMoreArticles();
        }
      },
      { rootMargin: "600px" }
    );
    observer.observe(el);
    return () => observer.disconnect();
  }, [activeTab, feedCursor, hasMoreFeed, loadingMore, selectedCategories, searchQuery, selectedEntities]);

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
      <CommandPaletteProvider
        activeTab={activeTab}
        onSelectTab={setActiveTab}
        onOpenArticle={openArticleReader}
      >
        <Sidebar
          activeTab={activeTab}
          onGoHome={goHome}
          badges={hasUnsavedChanges ? { preferences: "unsaved" } : undefined}
        />

        <main
          id="main-content"
          data-slot="main-content"
          className="flex-1 min-w-0 flex flex-col overflow-x-hidden"
          onClick={(e) => {
            // Article reader route -- delegated so it catches clicks on
            // any NewsCard rendered anywhere under here (including inside
            // UnifiedFeedView), without that component needing to know
            // about routing. Clicking the headline opens the in-app
            // reader; the "read at <host> ->" link (and share buttons)
            // are untouched and still open the external publisher URL.
            const titleEl = (e.target as HTMLElement).closest(
              '[data-slot="card-title"]'
            );
            if (!titleEl) return;
            const cardEl = titleEl.closest<HTMLElement>("[data-article-id]");
            const articleId = cardEl?.dataset.articleId;
            if (articleId) {
              e.preventDefault();
              openArticleReader(articleId);
            }
          }}
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
            </div>
          </header>

          <div className="px-6 py-6 flex-1">
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
                  recast as mono [ ] / [+] pills. SearchBar's onSelectEntity
                  replaces the cut Knowledge Graph tab: typing shows matching
                  entities in a dropdown, picking one adds it to the same
                  entity_id filter the TrendingRail chips below drive. */}
              <div className="flex flex-col md:flex-row gap-3 items-start md:items-center justify-between">
                <div className="flex-1 w-full md:max-w-md">
                  <SearchBar
                    onSearch={setSearchQuery}
                    initialQuery={searchQuery}
                    onSelectEntity={(entity) => {
                      setSelectedEntities((prev) =>
                        prev.some((e) => e.id === entity.id)
                          ? prev
                          : [...prev, entity]
                      );
                    }}
                  />
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

              {/* Polish iter 3 / Part D — Trending Now rail. Driven by the
                  knowledge-graph trending-entities endpoint (top entities
                  this week). Clicking a chip toggles the entity in
                  ``selectedEntities``, which drives the real backend
                  entity_id filter (see buildFeedParams). */}
              <TrendingRail
                selectedEntityIds={selectedEntities.map((e) => e.id)}
                onSelectEntity={(entity) => {
                  setSelectedEntities((prev) =>
                    prev.some((e) => e.id === entity.id)
                      ? prev.filter((e) => e.id !== entity.id)
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
                  {/* Each chip is its own remove button (click anywhere on
                      it, including the ×, to drop just that one filter) --
                      no need to hit "Clear Filters" to remove a single term.
                      The inner <span> carrying just the raw `cat` text keeps
                      the e2e contract intact: news-feed.spec.ts asserts
                      `activeFilters.getByText(chipCategory, { exact: true })`,
                      which matches an element whose textContent equals the
                      value exactly. Bracket/× decoration lives in aria-hidden
                      sibling spans so the visual "[ AI × ]" survives. */}
                  {selectedCategories.map((cat) => (
                    <button
                      key={`cat-${cat}`}
                      type="button"
                      onClick={() =>
                        setSelectedCategories((prev) =>
                          prev.filter((c) => c !== cat)
                        )
                      }
                      aria-label={`Remove filter ${cat}`}
                      className="inline-flex items-center px-1.5 py-0.5 border border-[var(--rule)] text-foreground hover:border-[var(--accent-signal)] hover:text-signal transition-colors"
                    >
                      <span aria-hidden="true">[&nbsp;</span>
                      <span>{cat}</span>
                      <span aria-hidden="true">&nbsp;&#215;]</span>
                    </button>
                  ))}
                  {selectedEntities.map((ent) => (
                    <button
                      key={`ent-${ent.id}`}
                      type="button"
                      onClick={() =>
                        setSelectedEntities((prev) =>
                          prev.filter((e) => e.id !== ent.id)
                        )
                      }
                      aria-label={`Remove filter ${ent.name}`}
                      className="inline-flex items-center px-1.5 py-0.5 border border-[var(--rule)] text-signal hover:border-[var(--accent-signal)] hover:text-foreground transition-colors"
                    >
                      <span aria-hidden="true">[&nbsp;</span>
                      <span>{ent.name}</span>
                      <span aria-hidden="true">&nbsp;&#215;]</span>
                    </button>
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

              {/* "New since you last visited" -- small localStorage-only
                  banner comparing the newest article timestamp from the
                  previous visit against what's in the feed now. */}
              {newSinceLastVisitCount > 0 && (
                <div
                  data-testid="news-feed-new-since-banner"
                  className="flex items-center gap-2 border-t border-b border-[var(--rule)] py-2 font-mono-tx text-[11px] uppercase-eyebrow text-signal"
                >
                  <span aria-hidden="true">&#9650;</span>
                  <span>
                    {newSinceLastVisitCount} new{" "}
                    {newSinceLastVisitCount === 1 ? "story" : "stories"} since
                    your last visit
                  </span>
                </div>
              )}

              {/* News-feed body -- REDESIGN Phase F: a single density-aware
                  UnifiedFeedView replaces the old mode==="mission"
                  MissionShell/DenseArticleRow branch and the Atelier
                  NewsCard grid/compact-list branch (the review flagged
                  maintaining Atelier and Mission Control as two entirely
                  separate full views as unnecessary upkeep). `density`
                  mirrors the existing detailed/compact toggle; loading and
                  the "no results" state (with a Reset Filters action) are
                  its own, passed through so the feed keeps the same UX it
                  had before the merge. Image-less articles are hidden from
                  this tab entirely (no bare-text cards) rather than shown
                  at the bottom -- `articles`/`filteredArticles` themselves
                  stay untouched so Research and Digest (which fetch
                  independently) still see every story regardless of image
                  availability. */}
              <UnifiedFeedView
                articles={visibleFeedArticles}
                density={viewMode === "compact" ? "compact" : "comfortable"}
                loading={loading}
                emptyState={
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
                }
              />

              {/* Infinite-scroll sentinel -- an IntersectionObserver
                  watches this and fetches the next cursor page once it
                  nears the viewport. Only rendered once the initial load
                  has settled and there's actually more to fetch. */}
              {!loading && visibleFeedArticles.length > 0 && (
                <div ref={feedSentinelRef} className="h-px" aria-hidden="true" />
              )}
              {loadingMore && (
                <div className="flex items-center justify-center py-6">
                  <Loader2 className="w-5 h-5 animate-spin text-foreground-soft" />
                </div>
              )}
              {!loading && !hasMoreFeed && visibleFeedArticles.length > 0 && (
                <div className="text-center py-6 font-mono-tx text-[11px] uppercase-eyebrow text-foreground-soft">
                  — end of feed —
                </div>
              )}

              {/* "Scroll for more ↓" hint -- infinite scroll has no other
                  visual affordance signaling more content loads on
                  scroll. Dismissible; auto-dismisses the first time
                  fetchMoreArticles actually fires (see there). */}
              {!scrollHintDismissed &&
                !loading &&
                hasMoreFeed &&
                visibleFeedArticles.length > 0 && (
                  <div className="fixed bottom-5 left-1/2 -translate-x-1/2 z-40 flex items-center gap-2 px-3 py-1.5 rounded-full border border-[var(--rule)] bg-background/95 backdrop-blur shadow-lg font-mono-tx text-[11px] uppercase-eyebrow text-foreground-soft">
                    <span>scroll for more &#8595;</span>
                    <button
                      type="button"
                      onClick={dismissScrollHint}
                      aria-label="Dismiss scroll hint"
                      className="text-foreground-mute hover:text-foreground"
                    >
                      &#215;
                    </button>
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

            {/* Saved Tab — persisted research reports (M3.M5) plus saved
                articles (localStorage `techpulse-saved-articles`,
                written by NewsCard's Save button). Two independent lists;
                SavedArticlesList fetches its own article data. */}
            <TabsContent value="saved" className="mt-0">
              <motion.div
                initial={panelInitial}
                animate={panelAnimate}
                transition={panelTransition}
                className="space-y-8"
              >
                <SavedArticlesList />
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

          {/* Toast Notifications */}
          <Toaster position="bottom-right" />

          {/* M1 footer — single hairline + mono colophon. */}
          <footer className="border-t border-[var(--rule)] mt-8">
            <div className="px-6 py-3 font-mono-tx text-[11px] uppercase-eyebrow text-foreground-soft flex justify-between">
              <span>— end of issue — set in fraunces &amp; ibm plex</span>
              <span>© techpulse 2026 · agentic desk</span>
            </div>
          </footer>

          {/* Article reader overlay -- `/article/:id` client-side route.
              Renders on top of whichever tab is active rather than
              replacing it, so closing it returns to exactly where the
              user was. */}
          {readerArticleId && (
            <ArticleReader
              articleId={readerArticleId}
              onClose={closeArticleReader}
            />
          )}
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
