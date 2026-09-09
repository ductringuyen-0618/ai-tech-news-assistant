import { useEffect, useRef, useState } from 'react';
import { Search, X } from 'lucide-react';
import { Input } from './ui/input';
import { API_ENDPOINTS, apiFetch } from '../config/api';

interface EntityResult {
  id: number;
  name: string;
  type: string;
  mention_count: number;
}

interface SearchBarProps {
  onSearch: (query: string) => void;
  placeholder?: string;
  /** Initial query to seed the input with (e.g. restored from the URL on
   *  load) -- uncontrolled after mount, this only affects first render. */
  initialQuery?: string;
  /** When provided, typing shows a live dropdown of matching knowledge-
   *  graph entities (companies, people, etc.) below the input. Picking
   *  one calls this instead of the plain-text onSearch -- this is the
   *  News Feed's entity filter lens (formerly a separate Knowledge Graph
   *  tab), folded into the search box everyone already uses rather than
   *  a second box competing for the same space. */
  onSelectEntity?: (entity: { id: number; name: string }) => void;
}

export function SearchBar({
  onSearch,
  placeholder = 'Search tech news...',
  initialQuery = '',
  onSelectEntity,
}: SearchBarProps) {
  const [query, setQuery] = useState(initialQuery);
  const [entityResults, setEntityResults] = useState<EntityResult[]>([]);
  const [entityLoading, setEntityLoading] = useState(false);
  const [showResults, setShowResults] = useState(false);
  const containerRef = useRef<HTMLFormElement>(null);
  const debounceRef = useRef<ReturnType<typeof setTimeout>>();
  const searchDebounceRef = useRef<ReturnType<typeof setTimeout>>();
  // Skip the very first debounce firing -- it would immediately re-call
  // onSearch(initialQuery) with the same value the parent already has,
  // which is a wasted refetch on every mount (including tab switches
  // that remount this component).
  const isFirstRun = useRef(true);

  // Live-filter search: fire onSearch ~300ms after the user stops typing,
  // instead of requiring Enter/submit. The feed list re-renders from
  // this on every settle, not just on submit -- see App.tsx's
  // `fetchArticles` effect keyed on `searchQuery`.
  useEffect(() => {
    if (isFirstRun.current) {
      isFirstRun.current = false;
      return;
    }
    clearTimeout(searchDebounceRef.current);
    searchDebounceRef.current = setTimeout(() => {
      onSearch(query.trim());
    }, 300);
    return () => clearTimeout(searchDebounceRef.current);
  }, [query, onSearch]);

  useEffect(() => {
    if (!onSelectEntity) return;
    const q = query.trim();
    if (q.length === 0) {
      setEntityResults([]);
      setEntityLoading(false);
      return;
    }
    setEntityLoading(true);
    clearTimeout(debounceRef.current);
    debounceRef.current = setTimeout(async () => {
      try {
        const params = new URLSearchParams({ q, limit: '6' });
        const data = await apiFetch<{ entities: EntityResult[] }>(
          `${API_ENDPOINTS.knowledgeGraphSearch}?${params}`
        );
        setEntityResults(data.entities || []);
      } catch (err) {
        console.error('SearchBar: entity search failed', err);
        setEntityResults([]);
      } finally {
        setEntityLoading(false);
      }
    }, 300);
    return () => clearTimeout(debounceRef.current);
  }, [query, onSelectEntity]);

  useEffect(() => {
    const onDocClick = (e: MouseEvent) => {
      if (
        containerRef.current &&
        !containerRef.current.contains(e.target as Node)
      ) {
        setShowResults(false);
      }
    };
    document.addEventListener('mousedown', onDocClick);
    return () => document.removeEventListener('mousedown', onDocClick);
  }, []);

  const handleSubmit = (e: React.FormEvent) => {
    e.preventDefault();
    setShowResults(false);
    onSearch(query);
  };

  const handleClear = () => {
    setQuery('');
    setEntityResults([]);
    setShowResults(false);
    onSearch('');
  };

  const pickEntity = (entity: EntityResult) => {
    onSelectEntity?.({ id: entity.id, name: entity.name });
    setQuery('');
    setEntityResults([]);
    setShowResults(false);
  };

  // Only pop the dropdown open once there's something worth showing --
  // a genuine entity match, or the brief loading state while we check.
  // A normal keyword search (e.g. "iphone launch") almost never matches
  // an entity name; without this the dropdown would sit open showing
  // "no matching entities" for the entire time someone types an ordinary
  // search, which read as the search box being broken/cluttered.
  const dropdownOpen =
    Boolean(onSelectEntity) &&
    showResults &&
    query.trim().length >= 2 &&
    (entityLoading || entityResults.length > 0);

  const handleKeyDown = (e: React.KeyboardEvent<HTMLInputElement>) => {
    if (e.key === 'Escape' && showResults) {
      e.preventDefault();
      setShowResults(false);
    }
  };

  return (
    <form
      onSubmit={handleSubmit}
      className="relative w-full"
      ref={containerRef}
    >
      <div className="relative">
        <Search className="absolute left-3 top-1/2 -translate-y-1/2 w-4 h-4 text-muted-foreground" />
        <Input
          type="text"
          value={query}
          onChange={e => setQuery(e.target.value)}
          onFocus={() => setShowResults(true)}
          onKeyDown={handleKeyDown}
          placeholder={
            onSelectEntity ? `${placeholder} or find a company...` : placeholder
          }
          className="pl-10 pr-10"
        />
        {query && (
          <button
            type="button"
            onClick={handleClear}
            aria-label="Clear search"
            className="absolute right-3 top-1/2 -translate-y-1/2 text-muted-foreground hover:text-foreground"
          >
            <X className="w-4 h-4" />
          </button>
        )}
      </div>

      {/* Entity suggestions dropdown. `top`/`maxHeight` are set inline
          rather than via Tailwind utility classes -- this project ships a
          frozen, hand-authored index.css (no live Tailwind JIT/PostCSS
          build step), so any class not already used elsewhere in the
          codebase silently applies no styles at all. Inline styles sidestep
          that trap entirely for the couple of properties without an
          already-verified utility class available. */}
      {dropdownOpen && (
        <div
          data-testid="entity-search-results"
          className="absolute z-50 mt-1 border border-input rounded-md bg-card shadow-lg overflow-y-auto"
          style={{ top: '100%', left: 0, right: 0, maxHeight: '16rem' }}
        >
          {entityLoading ? (
            <div className="px-3 py-2 text-[13px] text-muted-foreground">
              searching...
            </div>
          ) : (
            entityResults.map(r => (
              <button
                key={r.id}
                type="button"
                data-testid={`entity-search-result-${r.id}`}
                onClick={() => pickEntity(r)}
                className="w-full flex items-center gap-2 px-3 py-2 text-left border-l-2 border-transparent hover:border-[var(--accent-signal)] hover:bg-[var(--background-tint)] transition-colors"
              >
                <span className="flex-1 truncate text-[13px] text-foreground">
                  {r.name}
                </span>
                <span className="shrink-0 tabular-nums text-[11px] text-muted-foreground">
                  {r.mention_count}
                </span>
              </button>
            ))
          )}
        </div>
      )}
    </form>
  );
}
