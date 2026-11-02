/**
 * Settings — M5 tabular pivot.
 *
 * Hosts the Settings tab. The M3.M4 vertical card stack is
 * replaced with a broadsheet-style stack of mono section
 * eyebrows + tabular pivots. Theme + density become ticker
 * `[ light ] · [ dark ]` toggles matching the sidebar's M1
 * language. Category preferences (rendered by <TopicFilter>)
 * keep their Radix Checkbox plumbing -- the `role="checkbox"`
 * the spec asserts on continues to come out of Radix.
 *
 * Test contracts preserved (verified via
 * `grep -nE "data-testid=|getByText" frontend/e2e/settings.spec.ts`):
 *
 *   - data-testid="settings-theme-dark"     (theme toggle)
 *   - data-testid="settings-theme-light"
 *   - data-testid="settings-density-compact"
 *   - data-testid="settings-density-comfortable"
 *   - data-testid="settings-root"           (page wrapper)
 *   - data-testid="settings-theme"          (group wrapper)
 *   - data-testid="settings-density"        (group wrapper)
 *
 *   - visible text matching /^Appearance$/i
 *   - visible text /Topic Preferences/i        (from TopicFilter)
 *   - button name /Save Preferences/i          (from TopicFilter)
 *
 *   - localStorage key "techpulse-density" still written on
 *     density toggle (settings.spec.ts:303-310), kept for back
 *     compat. The live key is "techpulse-density-preference",
 *     read by UnifiedFeedView.tsx to actually change layout.
 *   - `<html>` `class="dark"` still toggles via useTheme on
 *     theme button click.
 *
 *   - <label> elements wrapping `button[role="checkbox"]` + the
 *     category text live in <TopicFilter>, which is unchanged at
 *     the testid-contract level.
 */
import { useState } from 'react';
import { toast } from 'sonner';
import { useTheme, Theme } from './ThemeProvider';
import { TopicFilter } from './TopicFilter';
import {
  readInterestWeights,
  clearInterestWeights,
} from '../lib/interestWeights';

export const DENSITY_STORAGE_KEY = 'techpulse-density';
export const DENSITY_PREFERENCE_KEY = 'techpulse-density-preference';
type Density = 'compact' | 'comfortable';

function readStoredDensity(): Density {
  try {
    const v =
      localStorage.getItem(DENSITY_PREFERENCE_KEY) ??
      localStorage.getItem(DENSITY_STORAGE_KEY);
    if (v === 'compact' || v === 'comfortable') return v;
  } catch {
    // privacy mode etc.
  }
  return 'comfortable';
}

interface SettingsProps {
  selectedCategories: string[];
  onCategoriesChange: (categories: string[]) => void;
  onSave: () => void;
  isSaving?: boolean;
  hasUnsavedChanges?: boolean;
}

/** A single ticker-style toggle option: `[ label ]` in mono,
 *  signal-colored when active. Built as a plain <button> so
 *  testid-based clicks from settings.spec.ts continue to work.
 */
function TickerOption({
  active,
  label,
  onClick,
  testId,
}: {
  active: boolean;
  label: string;
  onClick: () => void;
  testId: string;
}) {
  return (
    <button
      type="button"
      data-testid={testId}
      onClick={onClick}
      className={[
        'font-mono-tx text-[11px] uppercase-eyebrow px-3 py-1 border transition-colors',
        active
          ? 'bg-signal-wash text-signal border-[var(--accent-signal)]'
          : 'bg-card text-foreground-soft border-[var(--rule)] hover:text-signal hover:border-[var(--accent-signal)]',
      ].join(' ')}
    >
      [ {label} ]
    </button>
  );
}

/** Section eyebrow: mono `━ LABEL ─────...` separator. */
function SectionEyebrow({ label }: { label: string }) {
  return (
    <div className="flex items-center gap-3">
      <span className="font-mono-tx text-[11px] uppercase-eyebrow text-foreground-soft">
        ━ {label}
      </span>
      <span className="flex-1 border-t border-[var(--rule)]" />
    </div>
  );
}

interface InterestEntry {
  label: string;
  weight: number;
}

/** Strips the `source:`/`category:` namespace prefix off a weight key. */
function interestLabel(key: string): string {
  const separatorIndex = key.indexOf(':');
  return separatorIndex === -1 ? key : key.slice(separatorIndex + 1);
}

function splitInterestWeights(weights: Record<string, number>): {
  more: InterestEntry[];
  less: InterestEntry[];
} {
  const entries = Object.entries(weights)
    .filter(([, weight]) => weight !== 0)
    .map(([key, weight]) => ({ label: interestLabel(key), weight }));

  return {
    more: entries
      .filter(entry => entry.weight > 0)
      .sort((a, b) => b.weight - a.weight),
    less: entries
      .filter(entry => entry.weight < 0)
      .sort((a, b) => a.weight - b.weight),
  };
}

const MAX_INTEREST_ITEMS = 5;

/** Joins the top N entries' labels, folding any remainder into "+N more". */
function formatInterestList(entries: InterestEntry[]): string {
  const shown = entries.slice(0, MAX_INTEREST_ITEMS);
  const remaining = entries.length - shown.length;
  const labels = shown.map(entry => entry.label).join(', ');
  return remaining > 0 ? `${labels} +${remaining} more` : labels;
}

export function Settings({
  selectedCategories,
  onCategoriesChange,
  onSave,
  isSaving = false,
  hasUnsavedChanges = false,
}: SettingsProps) {
  const { theme, setTheme } = useTheme();
  const [density, setDensityState] = useState<Density>(() =>
    readStoredDensity()
  );
  const [interestWeights, setInterestWeights] = useState<
    Record<string, number>
  >(() => readInterestWeights());

  const handleTheme = (next: Theme) => {
    setTheme(next);
  };

  const handleResetInterests = () => {
    clearInterestWeights();
    setInterestWeights({});
    toast.success('Your interests have been reset');
  };

  const handleDensity = (next: Density) => {
    setDensityState(next);
    try {
      localStorage.setItem(DENSITY_STORAGE_KEY, next);
      localStorage.setItem(DENSITY_PREFERENCE_KEY, next);
    } catch {
      // Best-effort.
    }
  };

  return (
    <div className="max-w-3xl mx-auto space-y-10" data-testid="settings-root">
      {/* === MASTHEAD ============================== */}
      <header className="space-y-1 border-b-2 border-[var(--foreground)] pb-3">
        <div className="font-mono-tx text-[11px] uppercase-eyebrow text-foreground-soft">
          ━ CONTROL ROOM
        </div>
        <h2 className="font-display text-[28px] font-medium tracking-tight text-foreground leading-[1.1]">
          Settings
        </h2>
        <p className="font-mono-tx text-[11px] uppercase-eyebrow text-foreground-soft">
          dress the desk · pick a theme · pick the wire
        </p>
      </header>

      {/* === APPEARANCE ============================ */}
      <section className="space-y-4" data-testid="settings-appearance">
        <SectionEyebrow label="APPEARANCE" />
        {/* Literal "Appearance" for the settings.spec.ts
            `/^Appearance$/i` anchored regex. The eyebrow above
            says "━ APPEARANCE" which would not match. */}
        <h3 className="sr-only">Appearance</h3>
        <p className="font-mono-tx text-[11px] uppercase-eyebrow text-foreground-soft">
          theme and density persist across reloads
        </p>

        {/* Theme row */}
        <div className="space-y-2" data-testid="settings-theme">
          <div className="font-mono-tx text-[11px] uppercase-eyebrow text-foreground-soft">
            Theme
          </div>
          <div className="flex items-center gap-2">
            <TickerOption
              active={theme === 'light'}
              label="light"
              onClick={() => handleTheme('light')}
              testId="settings-theme-light"
            />
            <span className="font-mono-tx text-[11px] text-foreground-soft">
              ·
            </span>
            <TickerOption
              active={theme === 'dark'}
              label="dark"
              onClick={() => handleTheme('dark')}
              testId="settings-theme-dark"
            />
          </div>
        </div>

        {/* Density row */}
        <div className="space-y-2" data-testid="settings-density">
          <div className="font-mono-tx text-[11px] uppercase-eyebrow text-foreground-soft">
            Density
          </div>
          <div className="flex items-center gap-2">
            <TickerOption
              active={density === 'comfortable'}
              label="comfortable"
              onClick={() => handleDensity('comfortable')}
              testId="settings-density-comfortable"
            />
            <span className="font-mono-tx text-[11px] text-foreground-soft">
              ·
            </span>
            <TickerOption
              active={density === 'compact'}
              label="compact"
              onClick={() => handleDensity('compact')}
              testId="settings-density-compact"
            />
          </div>
        </div>
      </section>

      {/* === YOUR INTERESTS ========================= */}
      <section className="space-y-4" data-testid="settings-interests">
        <SectionEyebrow label="YOUR INTERESTS" />
        <p className="font-mono-tx text-[11px] uppercase-eyebrow text-foreground-soft">
          learned from your more / less like this reactions
        </p>

        {(() => {
          const { more, less } = splitInterestWeights(interestWeights);
          if (more.length === 0 && less.length === 0) {
            return (
              <p className="text-sm text-foreground-soft">
                React to articles in your feed and your interests will show up
                here.
              </p>
            );
          }
          return (
            <div className="space-y-2" data-testid="settings-interests-list">
              {more.length > 0 && (
                <p className="text-sm text-foreground">
                  <span className="font-mono-tx text-[11px] uppercase-eyebrow text-signal">
                    More of:
                  </span>{' '}
                  {formatInterestList(more)}
                </p>
              )}
              {less.length > 0 && (
                <p className="text-sm text-foreground">
                  <span className="font-mono-tx text-[11px] uppercase-eyebrow text-foreground-soft">
                    Less of:
                  </span>{' '}
                  {formatInterestList(less)}
                </p>
              )}
              <TickerOption
                active={false}
                label="reset my interests"
                onClick={handleResetInterests}
                testId="settings-interests-reset"
              />
            </div>
          );
        })()}
      </section>

      {/* === TOPICS (delegated to TopicFilter) ===== */}
      <section className="space-y-4">
        <SectionEyebrow label="TOPICS" />
        <TopicFilter
          selectedCategories={selectedCategories}
          onCategoriesChange={onCategoriesChange}
          onSave={onSave}
          isSaving={isSaving}
          hasUnsavedChanges={hasUnsavedChanges}
        />
      </section>
    </div>
  );
}

export default Settings;
