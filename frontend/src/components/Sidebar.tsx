/**
 * Sidebar -- Mission 3 / Milestone 1 (Broadsheet Terminal rebuild).
 *
 * Left vertical nav. Now a typographic stack: no rounded card slabs,
 * a Fraunces italic wordmark with a mono "vol. iii" superscript, a
 * numbered list of nav items with a 3px signal-color active block, and
 * a [ light ] / [ dark ] ticker theme toggle pinned to the bottom.
 * (The "> jump anywhere" Cmd+K affordance was removed from here; the
 * command palette's own keyboard shortcut still works independently.)
 *
 * Responsive: below the md breakpoint (768px, via `useIsMobile`) the
 * fixed w-72 rail is replaced by a hamburger trigger + a `Sheet`
 * slide-out drawer carrying the same nav content, so it no longer
 * permanently eats ~40%+ of a mobile viewport. Desktop (>=768px)
 * renders the original sticky `<aside>` unchanged.
 *
 * Test-contract preservation (53-test Playwright suite):
 *   - `data-slot="sidebar"` on the sidebar root (the `<aside>` on
 *     desktop, the `SheetContent` on mobile).
 *   - Radix `TabsList` + `TabsTrigger` keep emitting role="tablist" /
 *     role="tab" with the visible label as the accessible name; the
 *     "01." numeric prefix is rendered in an aria-hidden span AND
 *     each trigger carries an explicit aria-label so screen readers
 *     and getByRole("tab", { name: <Label> }) keep working. Only one
 *     of the desktop/mobile branches is ever mounted at a time, so
 *     there is never more than one tablist in the tree.
 *   - `data-testid="theme-toggle"` on the bottom toggle.
 *
 * IMPORTANT: this component MUST be rendered inside a Radix `<Tabs>`
 * root. App.tsx wraps the whole layout in <Tabs value=... onValueChange=...>.
 */
import { useState, type ReactNode } from "react";
import { TabsList, TabsTrigger } from "./ui/tabs";
import { useTheme } from "./ThemeProvider";
import { useIsMobile } from "./ui/use-mobile";
import {
  Sheet,
  SheetContent,
  SheetHeader,
  SheetTitle,
  SheetDescription,
} from "./ui/sheet";
import {
  Newspaper,
  Lightbulb,
  Mail,
  Settings,
  Bookmark,
  Menu,
} from "lucide-react";

export interface SidebarNavItem {
  /** Tab id (matches the Radix Tabs `value`). */
  value: string;
  /** Visible text -- also the accessible name for `getByRole("tab", { name })`. */
  label: string;
  icon: React.ComponentType<{ className?: string }>;
  /** When true, the tab content is a placeholder; click is allowed but
   * the tab body just shows "Coming soon". M5 will wire this up. */
  placeholder?: boolean;
}

export const SIDEBAR_NAV_ITEMS: SidebarNavItem[] = [
  { value: "feed", label: "News Feed", icon: Newspaper },
  { value: "research", label: "Research", icon: Lightbulb },
  { value: "digest", label: "Digest", icon: Mail },
  { value: "saved", label: "Saved", icon: Bookmark },
  { value: "preferences", label: "Settings", icon: Settings },
];

interface SidebarProps {
  /** Currently active tab value. Drives the active-state styling. */
  activeTab: string;
  /** Optional click-tap visual hint (e.g. unsaved-changes pill on Settings). */
  badges?: Partial<Record<string, "unsaved" | "warn">>;
  /** Navigate to the home page (welcome screen). Wired to the
   *  branding-header logo click so users can always return to `/`. */
  onGoHome?: () => void;
}

/**
 * Vertical sidebar nav. The TabsList wraps the per-item TabsTriggers; the
 * theme toggle and Cmd+K hint sit outside the TabsList so they don't get
 * roving-focus selected by the tablist arrow-key handler.
 */
export function Sidebar({ activeTab, badges, onGoHome }: SidebarProps) {
  const { theme, toggleTheme } = useTheme();
  const isMobile = useIsMobile();
  const [mobileOpen, setMobileOpen] = useState(false);

  // Shared nav body rendered on both desktop (inside <aside>) and mobile
  // (inside the Sheet drawer). `onNavigate` closes the drawer after a tap.
  function renderSidebarBody(onNavigate?: () => void): ReactNode {
    return (
      <>
        {/* Top hairline -- 2px ink bar that anchors the wordmark to the
            page top, broadsheet style. */}
        <div className="rule-h-thick" />

        {/* Wordmark -- Fraunces italic with a mono volume mark. Click
            navigates home. Renders as a full-row button so the hit
            target spans the whole header. */}
        <button
          type="button"
          onClick={() => {
            onGoHome?.();
            onNavigate?.();
          }}
          aria-label="Go to home page"
          className="px-4 pt-5 pb-4 flex items-baseline gap-1 text-left hover:bg-[var(--background-tint)] transition-colors w-full"
        >
          <span className="font-display italic font-medium text-2xl text-foreground">
            TechPulse
          </span>
          <span className="font-mono-tx text-[10px] uppercase-eyebrow ml-1">
            vol. iii
          </span>
        </button>

        {/* Nav items -- Radix TabsList provides role="tablist", TabsTrigger
            provides role="tab" and aria-selected state. We override the
            default horizontal layout with flex-col + full-width items.

            Each row gets:
              - a 3px-wide signal-color block in the gutter when active
                (the "terminal cursor" reading), absorbed back into the
                row via negative left margin so it sits flush with the
                sidebar edge;
              - a mono numeric prefix (01., 02., ...) marked aria-hidden;
              - the lucide icon (14px);
              - the visible label.
            aria-label on the trigger forces the accessible name to the
            unprefixed label so Playwright's getByRole("tab", { name })
            binds to the same string regardless of the prefix glyphs. */}
        <TabsList
          aria-orientation="vertical"
          className="flex flex-col items-stretch gap-0 px-0 py-2 h-auto w-full bg-transparent rounded-none"
        >
          {SIDEBAR_NAV_ITEMS.map((item, idx) => {
            const Icon = item.icon;
            const isActive = activeTab === item.value;
            const badge = badges?.[item.value];
            const num = String(idx + 1).padStart(2, "0") + ".";
            return (
              <TabsTrigger
                key={item.value}
                value={item.value}
                aria-label={item.label}
                onClick={() => onNavigate?.()}
                className={[
                  "group relative flex items-center w-full px-4 py-2 gap-3",
                  "text-left font-medium text-[14px] text-foreground-soft",
                  "hover:text-foreground hover:bg-[var(--background-tint)]",
                  "transition-colors rounded-none",
                  isActive ? "text-foreground bg-[var(--background-tint)]" : "",
                ].join(" ")}
              >
                {/* Left rule: 3px signal bar when active, hairline
                    rule fade on hover when inactive. The transition
                    animates the background between transparent →
                    foreground-soft so the cursor reveals on hover
                    without a hard step. */}
                <span
                  aria-hidden="true"
                  className={[
                    "w-[3px] h-5 ml-[-16px] mr-[13px] transition-colors",
                    isActive
                      ? "bg-[var(--accent-signal)]"
                      : "bg-transparent group-hover:bg-[var(--rule)]",
                  ].join(" ")}
                />
                <span
                  aria-hidden="true"
                  className="font-mono-tx text-[10px] text-foreground-soft uppercase-eyebrow w-7"
                >
                  {num}
                </span>
                <Icon className="w-[14px] h-[14px] shrink-0" />
                <span className="flex-1">{item.label}</span>
                {badge === "unsaved" && (
                  <span
                    aria-label="Unsaved changes"
                    className="w-1.5 h-1.5 rounded-full bg-[var(--accent-signal)]"
                  />
                )}
              </TabsTrigger>
            );
          })}
        </TabsList>

        <div className="flex-1" />

        {/* Theme toggle -- bottom of the sidebar. Renders as a ticker
            row: [ light ] · [ dark ], active option in --foreground,
            inactive in --foreground-soft. Preserves data-testid for the
            existing Playwright theme-toggle suite. */}
        <button
          type="button"
          onClick={toggleTheme}
          data-testid="theme-toggle"
          aria-label={`Switch to ${theme === "dark" ? "light" : "dark"} theme`}
          className="mx-3 mb-3 mt-2 px-3 py-2 border-t border-[var(--rule)] flex items-center gap-2 font-mono-tx text-[11px] uppercase-eyebrow"
        >
          <span
            className={theme === "light" ? "text-foreground" : "text-foreground-soft"}
          >
            [ light ]
          </span>
          <span className="text-foreground-soft">·</span>
          <span
            className={theme === "dark" ? "text-foreground" : "text-foreground-soft"}
          >
            [ dark ]
          </span>
        </button>
      </>
    );
  }

  if (isMobile) {
    return (
      <>
        {/* Hamburger trigger -- fixed top-left, replaces the always-on
            rail below the md breakpoint. Sits behind the Sheet overlay
            (z-40 vs Radix Dialog's z-50) so it's inert while the
            drawer is open. */}
        <button
          type="button"
          onClick={() => setMobileOpen(true)}
          aria-label="Open navigation menu"
          data-testid="sidebar-mobile-trigger"
          className="fixed top-3 left-3 z-40 flex items-center justify-center w-9 h-9 border border-[var(--rule)] bg-background text-foreground"
        >
          <Menu className="w-4 h-4" />
        </button>

        <Sheet open={mobileOpen} onOpenChange={setMobileOpen}>
          <SheetContent
            side="left"
            data-slot="sidebar"
            aria-label="Primary navigation"
            className="w-72 p-0 flex flex-col bg-background text-foreground border-[var(--rule)]"
          >
            {/* Visually-hidden title/description for the Radix Dialog
                a11y contract -- the wordmark button below is the
                visible heading. */}
            <SheetHeader className="sr-only">
              <SheetTitle>Navigation</SheetTitle>
              <SheetDescription>Primary navigation menu</SheetDescription>
            </SheetHeader>
            {renderSidebarBody(() => setMobileOpen(false))}
          </SheetContent>
        </Sheet>
      </>
    );
  }

  return (
    <aside
      data-slot="sidebar"
      aria-label="Primary navigation"
      className="flex flex-col w-72 shrink-0 h-screen sticky top-0 border-r border-[var(--rule)] bg-background text-foreground"
    >
      {renderSidebarBody()}
    </aside>
  );
}
