import { useEffect, useState } from 'react';
import { Badge } from './ui/badge';
import { Button } from './ui/button';
import {
  Card,
  CardContent,
  CardDescription,
  CardHeader,
  CardTitle,
} from './ui/card';
import { Checkbox } from './ui/checkbox';
import { Filter, X, Loader2, Check } from 'lucide-react';
import { API_ENDPOINTS, apiFetch } from '../config/api';

interface TopicFilterProps {
  selectedCategories: string[];
  onCategoriesChange: (categories: string[]) => void;
  onSave: () => void;
  isSaving?: boolean;
  hasUnsavedChanges?: boolean;
}

interface CategoryOption {
  id: string;
  label: string;
  icon: string;
}

// Best-effort emoji map for the categories the ingestion pipeline emits today.
// New categories that aren't in the map fall back to a neutral icon, so the
// UI never crashes when the backend introduces a new tag.
const CATEGORY_ICONS: Record<string, string> = {
  'AI/ML': '🤖',
  'AI Agents': '🎯',
  Robotics: '🦾',
  Biotech: '🧬',
  'Military Tech': '⚔️',
  Hardware: '💻',
  Cloud: '☁️',
  Security: '🔒',
  'Quantum Computing': '⚛️',
  Healthcare: '🏥',
};

const FALLBACK_ICON = '📰';

export function TopicFilter({
  selectedCategories,
  onCategoriesChange,
  onSave,
  isSaving = false,
  hasUnsavedChanges = false,
}: TopicFilterProps) {
  // Categories now come from the backend's ``/api/news/categories`` endpoint
  // — the union of distinct ``categories`` values actually present in the DB
  // — so the chip list is in sync with what the user can really filter to.
  // Previously the list was hard-coded to 10 chips and 7 of them produced
  // "No articles found" because no feed mapped to them.
  const [categories, setCategories] = useState<CategoryOption[]>([]);
  const [loadingCategories, setLoadingCategories] = useState(true);
  const [categoryLoadError, setCategoryLoadError] = useState<string | null>(
    null
  );

  useEffect(() => {
    let cancelled = false;

    const loadCategories = async () => {
      try {
        const envelope = await apiFetch<any>(API_ENDPOINTS.newsCategories);
        if (cancelled) return;
        const data = envelope?.data ?? envelope;
        const list: string[] = Array.isArray(data?.categories)
          ? data.categories
          : [];
        const opts: CategoryOption[] = list.map(id => ({
          id,
          label: id,
          icon: CATEGORY_ICONS[id] ?? FALLBACK_ICON,
        }));
        setCategories(opts);
      } catch (err) {
        if (cancelled) return;
        console.error('Failed to load categories:', err);
        setCategoryLoadError("Couldn't load topics from the server.");
      } finally {
        if (!cancelled) {
          setLoadingCategories(false);
        }
      }
    };

    loadCategories();
    return () => {
      cancelled = true;
    };
  }, []);

  const toggleCategory = (categoryId: string) => {
    if (selectedCategories.includes(categoryId)) {
      onCategoriesChange(selectedCategories.filter(c => c !== categoryId));
    } else {
      onCategoriesChange([...selectedCategories, categoryId]);
    }
  };

  const clearAll = () => {
    onCategoriesChange([]);
  };

  const selectAll = () => {
    onCategoriesChange(categories.map(c => c.id));
  };

  return (
    <Card>
      <CardHeader>
        <div className="flex items-center justify-between">
          <div className="flex items-center gap-2">
            <Filter className="w-5 h-5" />
            <CardTitle>Topic Preferences</CardTitle>
          </div>
          <div className="flex gap-2">
            <Button variant="outline" size="sm" onClick={clearAll}>
              Clear All
            </Button>
            <Button
              variant="outline"
              size="sm"
              onClick={selectAll}
              disabled={categories.length === 0}
            >
              Select All
            </Button>
          </div>
        </div>
        <CardDescription>
          Choose topics you're interested in to personalize your news feed
        </CardDescription>
      </CardHeader>
      <CardContent>
        {loadingCategories ? (
          <div className="flex items-center justify-center py-8 text-muted-foreground">
            <Loader2 className="w-5 h-5 mr-2 animate-spin" />
            Loading topics...
          </div>
        ) : categories.length === 0 ? (
          <div className="py-8 text-center text-muted-foreground">
            {categoryLoadError ??
              "No topics yet — ingest some articles and they'll appear here."}
          </div>
        ) : (
          <div className="grid grid-cols-1 md:grid-cols-2 gap-3 mb-4">
            {categories.map(category => (
              <label
                key={category.id}
                className="flex items-center gap-3 p-3 border border-border rounded-lg cursor-pointer hover:bg-accent transition-colors"
              >
                <Checkbox
                  checked={selectedCategories.includes(category.id)}
                  onCheckedChange={() => toggleCategory(category.id)}
                />
                <span className="text-2xl">{category.icon}</span>
                <span className="flex-1">{category.label}</span>
              </label>
            ))}
          </div>
        )}

        {selectedCategories.length > 0 && (
          <div className="border-t pt-4">
            <div className="flex items-center justify-between mb-3">
              <p className="text-sm text-muted-foreground">
                Selected Topics ({selectedCategories.length})
              </p>
              {hasUnsavedChanges && (
                <Badge
                  variant="secondary"
                  className="bg-yellow-100 text-yellow-800 border-yellow-300"
                >
                  Unsaved changes
                </Badge>
              )}
            </div>
            <div className="flex flex-wrap gap-2 mb-4">
              {selectedCategories.map(catId => {
                const category = categories.find(c => c.id === catId);
                const icon =
                  category?.icon ?? CATEGORY_ICONS[catId] ?? FALLBACK_ICON;
                const label = category?.label ?? catId;
                return (
                  <Badge key={catId} variant="default" className="gap-1">
                    <span>{icon}</span>
                    <span>{label}</span>
                    <button
                      onClick={() => toggleCategory(catId)}
                      className="ml-1 hover:bg-white/20 rounded-full"
                    >
                      <X className="w-3 h-3" />
                    </button>
                  </Badge>
                );
              })}
            </div>
            <Button onClick={onSave} className="w-full" disabled={isSaving}>
              {isSaving ? (
                <>
                  <Loader2 className="w-4 h-4 mr-2 animate-spin" />
                  Saving...
                </>
              ) : (
                <>
                  <Check className="w-4 h-4 mr-2" />
                  Save Preferences
                </>
              )}
            </Button>
          </div>
        )}
      </CardContent>
    </Card>
  );
}
