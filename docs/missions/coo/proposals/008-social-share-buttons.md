---
status: proposed
attempts: 0
branch: null
---
# Social Share Buttons

## What you get
A "Share" button appears on every article card and inside the full article view. Tapping it on a phone opens the normal share sheet (Messages, WhatsApp, Mail, etc.); on a desktop it offers a one-click post to X and LinkedIn plus a "copy link" option. Either way, the link that goes out points straight at that one article, so whoever receives it lands on the exact story, not the homepage.

## Why start this now
Every visitor TechPulse gets today is one it found on its own — there is no built-in way for a reader to hand a story to a friend or colleague in one tap, which is the single cheapest source of new visitors a content product has. A recent review round flagged this exact gap on the competitive front, and nothing shipped since (the Learning tab, feed reactions, per-article Q&A, and the digest RSS feed) touched sharing at all. The article pages this would sit on already have stable, linkable URLs, so this is wiring a button onto something that already works, not building new plumbing — a day or two of frontend-only work with no backend change and no new service to pay for.

## Problem / opportunity
Articles and the article reader have no share affordance anywhere in the UI. The only way to pass a story along today is to copy the browser address bar manually, which most people simply don't do. Social share buttons are one of the best-understood, lowest-cost growth levers for a content site, and TechPulse has none.

## Proposed solution
- **Frontend only** (`frontend/src/components/NewsCard.tsx`, `frontend/src/components/ArticleReader.tsx`, plus a small new shared helper e.g. `frontend/src/lib/share.ts`): add a "Share" action that:
  - Calls `navigator.share()` when the browser supports it (mobile Safari/Chrome), passing the article's title and its canonical `/article/:id` URL.
  - Falls back to a small popover/menu with "Copy link" (reuses the existing clipboard-copy pattern already used by the RSS subscribe link), "Share to X", and "Share to LinkedIn" (both are plain `window.open` calls to each platform's public share-intent URL — no API key, no app registration, no backend call).
- No new backend route, no new dependency, no new database column — the article URL this reuses already exists from the existing `/article/:id` routing.
- User sees: a share icon next to the existing save/react controls on each card and in the article reader; tapping it either opens their device's native share sheet or a small "copy link / X / LinkedIn" menu.

## Effort estimate
S — a self-contained UI addition using only `navigator.share` and plain share-intent URLs, reusing an existing copy-link pattern and an already-stable article URL scheme. No backend, no schema, no new dependency.

## Validation contract
- Functional assertions:
  - The share control renders on every `NewsCard` and inside `ArticleReader`.
  - When `navigator.share` is available, invoking it is attempted with the article's title and its full `/article/:id` URL.
  - When `navigator.share` is unavailable (desktop), the fallback menu offers copy-link, X, and LinkedIn, and each opens the correct target (clipboard write, or a new tab to the platform's share-intent URL with the right article URL encoded).
  - Nothing is sent to any backend route as part of sharing — this is 100% client-side.
- Behavioral assertions:
  - The share control is reachable by keyboard and has an accessible label (not icon-only with no `aria-label`).
  - Opening the fallback menu does not block or shift the rest of the card/article layout (no layout jump).
  - Works the same whether the article came from the main feed, search results, or the article reader.
- Negative assertions (should NOT happen):
  - No new dependency added to `package.json`.
  - No backend file touched.
  - No popup blocked silently with no feedback — `window.open` fallback (e.g. clipboard copy) if a share-intent tab fails to open.
- Test commands the build will need to pass:
  - Frontend, from `frontend/`: `npm run lint`, `npx prettier --check "src/**/*.{js,jsx,ts,tsx,json,css,md}"`, `npx tsc --noEmit`, `npm run build`

## Risks / open questions
- `navigator.share` requires a secure context (HTTPS) — both Vercel production and the local dev server over `localhost` satisfy this, but it's worth a quick manual check that the fallback menu (not a silent failure) is what non-HTTPS/non-supporting browsers actually get.
- Share-intent URL formats for X/LinkedIn are stable public conventions, not an official API, so they carry a small risk of each platform tweaking query-param names in the future — low-maintenance to fix if it ever happens, not worth hedging against now.
