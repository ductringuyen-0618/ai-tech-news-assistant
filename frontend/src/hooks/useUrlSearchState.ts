/**
 * useUrlSearchState — persists the News Feed's search query and topic
 * filters into the URL's query string (?q=openai&topics=ai-ml,security)
 * so a search/filter is shareable and survives a refresh.
 *
 * Writes use `history.replaceState` (not `pushState`) so every keystroke
 * doesn't spam browser history -- the feed's tab navigation already owns
 * `pushState` for path changes (see App.tsx's `setActiveTab`). Reading
 * back on `popstate` lets an actual back/forward navigation (or a
 * hand-edited URL) flow into whatever state the caller drives from this
 * hook.
 */
import { useCallback, useEffect, useState } from 'react';

export interface UrlSearchState {
  q: string;
  topics: string[];
}

const EMPTY_STATE: UrlSearchState = { q: '', topics: [] };

function readFromUrl(): UrlSearchState {
  if (typeof window === 'undefined') return EMPTY_STATE;
  const params = new URLSearchParams(window.location.search);
  const q = params.get('q') || '';
  const topicsParam = params.get('topics') || '';
  const topics = topicsParam
    ? topicsParam
        .split(',')
        .map(t => t.trim())
        .filter(Boolean)
    : [];
  return { q, topics };
}

function writeToUrl(state: UrlSearchState) {
  if (typeof window === 'undefined') return;
  const params = new URLSearchParams(window.location.search);
  if (state.q) {
    params.set('q', state.q);
  } else {
    params.delete('q');
  }
  if (state.topics.length > 0) {
    params.set('topics', state.topics.join(','));
  } else {
    params.delete('topics');
  }
  const query = params.toString();
  const nextUrl = `${window.location.pathname}${query ? `?${query}` : ''}`;
  const currentUrl = `${window.location.pathname}${window.location.search}`;
  if (nextUrl !== currentUrl) {
    window.history.replaceState(window.history.state, '', nextUrl);
  }
}

/**
 * Returns `[state, update]`. `update` merges a partial state into the
 * current one and writes the result to the URL. Bails out (no state
 * change, no history write) when the merged result is identical to the
 * current state, which keeps a caller's "sync app state -> URL" effect
 * from looping against this hook's own "sync URL -> app state" popstate
 * listener.
 */
export function useUrlSearchState(): [
  UrlSearchState,
  (next: Partial<UrlSearchState>) => void,
] {
  const [state, setState] = useState<UrlSearchState>(() => readFromUrl());

  useEffect(() => {
    const onPopState = () => setState(readFromUrl());
    window.addEventListener('popstate', onPopState);
    return () => window.removeEventListener('popstate', onPopState);
  }, []);

  const update = useCallback((next: Partial<UrlSearchState>) => {
    setState(prev => {
      const merged: UrlSearchState = { ...prev, ...next };
      const unchanged =
        merged.q === prev.q &&
        merged.topics.length === prev.topics.length &&
        merged.topics.every((t, i) => t === prev.topics[i]);
      if (unchanged) return prev;
      writeToUrl(merged);
      return merged;
    });
  }, []);

  return [state, update];
}
