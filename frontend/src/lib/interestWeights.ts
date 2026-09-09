/**
 * Interest weights — the client-side signal behind the feed's "more like
 * this" / "less like this" reactions (proposal 002). Entirely local: a
 * flat map of namespaced keys (`source:<name>`, `category:<name>`) to a
 * small integer, clamped so one click can never permanently bury a whole
 * source or category. No backend calls, no schema.
 */

const INTEREST_WEIGHTS_KEY = 'techpulse-interest-weights';
const MIN_WEIGHT = -3;
const MAX_WEIGHT = 3;

export interface WeightSubject {
  source?: string;
  category?: string[];
}

function clamp(value: number): number {
  return Math.max(MIN_WEIGHT, Math.min(MAX_WEIGHT, value));
}

function subjectKeys(subject: WeightSubject): string[] {
  const keys: string[] = [];
  if (subject.source) keys.push(`source:${subject.source}`);
  for (const category of subject.category ?? []) {
    if (category) keys.push(`category:${category}`);
  }
  return keys;
}

export function readInterestWeights(): Record<string, number> {
  try {
    const raw = localStorage.getItem(INTEREST_WEIGHTS_KEY);
    if (!raw) return {};
    const parsed = JSON.parse(raw);
    if (!parsed || typeof parsed !== 'object' || Array.isArray(parsed))
      return {};
    const weights: Record<string, number> = {};
    for (const [key, value] of Object.entries(parsed)) {
      const num = Number(value);
      if (Number.isFinite(num)) weights[key] = clamp(num);
    }
    return weights;
  } catch {
    return {};
  }
}

function persistInterestWeights(weights: Record<string, number>): void {
  try {
    localStorage.setItem(INTEREST_WEIGHTS_KEY, JSON.stringify(weights));
  } catch {
    /* ignore quota / privacy errors */
  }
}

export interface NudgeResult {
  weights: Record<string, number>;
  /** False when every affected key was already at the clamp -- the click had no real effect. */
  changed: boolean;
}

/** Nudges the weight for a subject's source and every category up/down by one step. */
export function nudgeInterestWeight(
  subject: WeightSubject,
  delta: 1 | -1
): NudgeResult {
  const weights = readInterestWeights();
  let changed = false;
  for (const key of subjectKeys(subject)) {
    const previous = weights[key] ?? 0;
    const next = clamp(previous + delta);
    if (next !== previous) changed = true;
    weights[key] = next;
  }
  persistInterestWeights(weights);
  return { weights, changed };
}

export function clearInterestWeights(): void {
  try {
    localStorage.removeItem(INTEREST_WEIGHTS_KEY);
  } catch {
    /* ignore quota / privacy errors */
  }
}

/** Sum of a subject's source + category weights — the raw interest score for one article. */
export function articleInterestScore(
  subject: WeightSubject,
  weights: Record<string, number>
): number {
  return subjectKeys(subject).reduce(
    (sum, key) => sum + (weights[key] ?? 0),
    0
  );
}

/**
 * Reorders articles by interest score within fixed-size windows of
 * adjacent, already-recency-sorted articles. Recency stays the primary
 * key -- articles never move across a window boundary, so a liked article
 * can rise within its neighborhood but never bury breaking news several
 * windows away. A no-op (same array, same order) when there are no
 * weights yet, so a fresh visitor sees byte-identical chronological order.
 */
export function reorderByInterest<T extends WeightSubject>(
  articles: T[],
  weights: Record<string, number>,
  windowSize = 6
): T[] {
  if (Object.keys(weights).length === 0 || articles.length === 0)
    return articles;

  const result: T[] = [];
  for (let start = 0; start < articles.length; start += windowSize) {
    const window = articles.slice(start, start + windowSize);
    const ranked = window
      .map((article, index) => ({
        article,
        index,
        score: articleInterestScore(article, weights),
      }))
      .sort((a, b) => b.score - a.score || a.index - b.index);
    result.push(...ranked.map(entry => entry.article));
  }
  return result;
}
