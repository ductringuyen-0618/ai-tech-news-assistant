/**
 * RecentDispatches -- compact LIVE-WIRE-style panel of recently saved
 * research runs (design-review #7).
 *
 * Fetches ``GET /api/saved-research`` on mount, renders the last five
 * entries as monospaced ``HH:MM ▸ Question`` rows under a `-- RECENT
 * DISPATCHES` eyebrow. Sits below the Research input on desktop so the
 * empty Research state has visual weight and a recall affordance.
 *
 * Clicking a row navigates to ``/saved`` -- a v2 enhancement would be
 * to open the report in-place, but the route hop keeps the surface
 * area small and matches the existing SavedResearchList view.
 */
import { useEffect, useState } from "react";
import { motion, useReducedMotion } from "framer-motion";
import { API_ENDPOINTS, apiFetch } from "../config/api";

interface SavedListItem {
  id: number;
  question: string;
  created_at: string;
}

function formatTime(iso: string): string {
  try {
    const dt = new Date(iso.replace(" ", "T"));
    if (Number.isNaN(dt.getTime())) return "--:--";
    return dt.toLocaleTimeString("en-US", {
      hour: "2-digit",
      minute: "2-digit",
      hour12: false,
    });
  } catch {
    return "--:--";
  }
}

export function RecentDispatches() {
  const reduceMotion = useReducedMotion();
  const [items, setItems] = useState<SavedListItem[] | null>(null);
  const [errored, setErrored] = useState(false);

  useEffect(() => {
    let cancelled = false;
    (async () => {
      try {
        const data = await apiFetch<SavedListItem[] | { items: SavedListItem[] }>(
          API_ENDPOINTS.savedResearch
        );
        if (cancelled) return;
        const raw = Array.isArray(data)
          ? data
          : Array.isArray((data as any)?.items)
            ? (data as any).items
            : [];
        setItems(raw.slice(0, 5));
      } catch (err) {
        if (!cancelled) {
          setErrored(true);
          setItems([]);
        }
      }
    })();
    return () => {
      cancelled = true;
    };
  }, []);

  // While loading, keep the panel placeholder visible so the layout
  // doesn't jump when the API resolves.
  const isLoading = items === null;

  const handleSelect = (id: number) => {
    if (typeof window === "undefined") return;
    // Minimum-viable navigation: hop to /saved. The deeper "open this
    // specific report in-place" gesture is a v2 add.
    void id;
    window.history.pushState(null, "", "/saved");
    // Force a popstate-style re-read so App.tsx's existing listener
    // picks up the new path without a full reload.
    window.dispatchEvent(new PopStateEvent("popstate"));
  };

  return (
    <section
      data-testid="research-recent-dispatches"
      className="border-t border-[var(--rule)] mt-8 pt-6"
    >
      <div className="font-mono-tx text-[11px] uppercase-eyebrow text-foreground-soft mb-3 flex items-center gap-3">
        <span>{"━ RECENT DISPATCHES"}</span>
        <span className="flex-1 border-t border-[var(--rule)]" />
        {!isLoading && items && items.length > 0 && (
          <span>{items.length} archived</span>
        )}
      </div>

      {isLoading && (
        <p className="font-mono-tx text-[12px] text-foreground-soft">
          Reading the file room
          <span className="live-cursor"></span>
        </p>
      )}

      {!isLoading && errored && (
        <p className="font-mono-tx text-[12px] text-foreground-soft">
          File room offline. Try again in a moment.
        </p>
      )}

      {!isLoading && !errored && items && items.length === 0 && (
        <p className="font-mono-tx text-[12px] text-foreground-soft">
          No dispatches filed yet. Run a query above to start the archive.
        </p>
      )}

      {!isLoading && !errored && items && items.length > 0 && (
        <ol className="font-mono-tx text-[12px] space-y-1.5">
          {items.map((item, idx) => (
            <motion.li
              key={item.id}
              initial={reduceMotion ? false : { opacity: 0, y: 4 }}
              animate={{ opacity: 1, y: 0 }}
              transition={{
                duration: reduceMotion ? 0 : 0.18,
                delay: reduceMotion ? 0 : idx * 0.05,
              }}
            >
              <button
                type="button"
                data-testid={`research-recent-dispatch-${item.id}`}
                onClick={() => handleSelect(item.id)}
                className="w-full flex gap-3 items-start text-left hover:bg-[var(--background-tint)] px-1 py-0.5 transition-colors"
              >
                <span className="text-foreground-soft shrink-0 w-12">
                  {formatTime(item.created_at)}
                </span>
                <span className="text-foreground leading-[1.4] flex-1 truncate">
                  <span className="text-signal mr-1">{"▸"}</span>
                  {item.question}
                </span>
              </button>
            </motion.li>
          ))}
        </ol>
      )}
    </section>
  );
}
