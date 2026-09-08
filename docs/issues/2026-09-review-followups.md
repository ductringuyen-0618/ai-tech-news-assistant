# Review follow-ups (deferred from the 2026-09 implementation batch)

**Status:** tracking only — not scheduled. This batch (20 agents implementing findings
from the 10-agent review round dated 2026-09) deliberately left these out because
they're too large, too speculative, or blocked on secrets/infra this batch doesn't
have access to configure. Captured here so they aren't lost. See
`docs/issues/personalized-company-digest.md` for the same treatment of an earlier
deferred idea.

---

## 1. Real email sending for the digest subscribe flow

**What it is:** Actually emailing subscribers a daily digest, not just collecting
addresses. This batch's `impl-subscriber-capture` agent builds capture-only
plumbing — a `Subscriber` table and a working form that stores the email — but
stops short of sending anything.

**Recommended by:** review-02 (monetization) #2, review-06 (retention-growth) #1,
review-09 (competitive) #4 — all three flag this as the single highest-leverage
retention feature for a daily-news product (Morning Brew/Axios/TLDR all lead with
email).

**Why deferred:** needs a third-party ESP (Resend/Postmark/SES) API key this batch
can't provision, plus a scheduled send job (cron/worker) that doesn't exist yet.
Capture-first is the correct sequencing — no point sending until there's a list.

**Next step:** once `Subscriber` rows exist, wire a daily cron (Fly.io scheduled
machine or GitHub Actions) that renders the existing digest payload and sends via
Resend/Postmark free tier. Small scope once the API key is in hand.

---

## 2. Story clustering / multi-source threading

**What it is:** Techmeme-style grouping of the same event across outlets — e.g.
one thread for a story covered by The Verge, Ars Technica, MIT Tech Review,
TechCrunch, and HN, with per-outlet links under one headline, instead of parallel
standalone cards.

**Recommended by:** review-09 (competitive) as the top "missing vs. Techmeme"
item; review-03 (content-reading) #5 as the "ambitious version" of the article
reader (uses entity co-mentions as a similarity proxy); review-09 also flags a
cheaper adjacent win — a "3 sources covered this" coverage-diversity chip (vs.
Ground News) — as a fallback if full clustering is too big.

**Why deferred:** genuinely large — backend clustering/similarity logic (likely
built on the existing entity-co-mention data) plus new frontend thread UI. The
entity-linking groundwork exists and is idle, but turning it into reliable
same-story clustering across sources is its own project, not a fits-in-a-batch
fix.

**Next step:** scope as its own effort. Cheapest first slice: surface a "N
sources covered this" count/chip per article using existing entity co-mentions
(no clustering UI needed) before attempting full thread grouping.

---

## 3. Live Mission Control agent telemetry

**What it is:** Making the "IDLE — scan → surface → cluster" agent-status panel
show real ingestion activity instead of sitting permanently on "IDLE." The
`techpulse:agent-event` window `CustomEvent` it listens for is never dispatched
by the ingestion job.

**Recommended by:** review-04 (ai-differentiation) #2 ("make it real or cut it");
review-10 (keep-cut-audit) rates the panel "Keep-but-fix."

**Why deferred:** this batch's `impl-unified-feed-view` agent is merging Mission
Control into a density toggle on the main feed (per review-09's and review-10's
"cut the second full nav destination" recommendation), so the dedicated
telemetry page this finding assumes may not survive in its current form. Wiring
real-time/polling telemetry into a panel that's about to be restructured risked
wasted work — worth revisiting once the post-merge UI shape is settled and it's
clear whether a telemetry element still earns a place in the merged view.

**Next step:** after the density-toggle merge lands, decide whether an
agent-status indicator still belongs in the unified feed (even a small "last
ingested Xm ago" line polling `/api/news/stats`) or whether it's better cut
entirely per the keep/cut audit's broader "don't dilute the wedge" lesson.

---

## 4. Rate-limiting / soft-paywall UI on the Research agent

**What it is:** Surfacing the Research agent's existing concurrency gate
(`backend/src/api/routes/research.py` limits to 1 in-flight run process-wide) as
user-facing framing — e.g. "3 free research dispatches/day, sign in for more" —
rather than a silent backend constraint.

**Recommended by:** review-02 (monetization) #1, called out as the top
recommendation — "the single most credible signal to a technical reviewer" that
the builder understands unit economics (LLM calls cost money).

**Why deferred:** depends on the client-identity work (`impl-settings-and-identity`
/ `impl-settings-identity-backend`, adding an anonymous `client_id`) landing
first, since a per-user/per-day limit needs something to key the count on. It
also brushes against billing-adjacent UX decisions (what happens at the limit,
whether "sign in for more" implies auth that doesn't exist yet) worth a
deliberate pass rather than bolting on inside this batch.

**Next step:** once `client_id` identity is live, add a request-count column
(or a simple in-memory/DB counter keyed by `client_id` + date) and a UI state
for "limit reached" on the Research page. Keep the copy honest — no fake
upgrade CTA until there's something to upgrade to.

---

## 5. A `/developers` API-access teaser page

**What it is:** A page documenting the entity-linked article API (entity graph,
relevance scoring) with a "request a key" form — showcasing the data asset as a
product rather than building ads/affiliate monetization this app has no traffic
to support.

**Recommended by:** review-02 (monetization) #3.

**Why deferred:** not blocking on secrets, but out of scope for this batch's
file assignments — no agent owns new marketing/docs surface, and it's a
standalone addition rather than a fix to existing broken behavior (which is
where this batch focused effort).

**Next step:** small, self-contained — a static page + a form that posts to a
simple "API access requests" table (same shape as the Subscriber capture work).
Good candidate for a future single-agent task.

---

## 6. Full user accounts/auth

**What it is:** Real authentication — the `User` table in
`backend/src/database/models.py` already has `email`/`hashed_password` columns,
but there are zero wired auth routes (login/register/session).

**Recommended by:** review-06 (retention-growth) flags it as "dead scaffolding"
— either build minimal auth on top of it or drop it, since half-scaffolding
signals unfinished work to a reviewer poking at the schema.

**Why deferred:** this batch adds a lighter-weight anonymous `client_id`
identity instead (localStorage-generated UUID sent via `X-Client-Id`, see
`impl-settings-and-identity` / `impl-settings-identity-backend`), which covers
the immediate need (de-singleton the settings row, key rate limits per visitor)
without the much larger scope of real auth — password hashing/reset flows,
session management, migrating anonymous data to accounts, etc.

**Next step:** once `client_id` identity is live and used in a few places
(settings, Research rate-limit, maybe Saved articles), revisit whether real
accounts are worth it — likely only if/when the product has actual multi-device
or paid-tier needs. Until then, consider explicitly documenting the `User`
table as reserved-for-future rather than leaving it silently unused.

---

## Other deferred items spotted while reading the reviews

Smaller items, not assigned to any agent in this batch, worth keeping on the
list rather than losing track of:

- **Per-digest permalinks** (e.g. `/digest/2026-09-07`) and **RSS/JSON export
  of the digest** — review-06 #3/#4, both small effort, make each day's edition
  shareable/indexable/scriptable. No agent in this batch owns digest routing.
- **Shareable permalinks for Research reports** (`/research/:id`) — review-05
  #5, review-06 keep-and-double-down. The strongest advocate-loop candidate in
  the product (cited, agentic reports are inherently link-worthy) but needs its
  own route/storage design, not a drive-by addition.
- **Interest-weighted re-ranking** from Save/read/topic-click behavior —
  review-01 #4, review-09 #5 (vs. Feedly Leo). Depends on read-state tracking
  landing first; this batch's card-level UX fixes (read-state dimming, "new
  since last visit") are more likely in scope than the re-ranking logic itself.
- **Lightweight reaction mechanic** (thumbs up/down or "more/less like this")
  — review-05 #3. Same dependency as above; worth bundling with the re-ranking
  work rather than doing standalone.
- **Per-article inline Q&A** ("ask about this story," vs. Particle) — review-09
  #2, medium effort. Distinct from this batch's citation-rendering work
  (`impl-research-citations`), which only makes existing Research citations
  render as real source chips, not a new per-article entry point into Research.
- **Tip jar / GitHub Sponsors badge** — review-02 #4. Trivial but not assigned;
  a one-line addition to a footer/settings page whenever someone's touching
  that surface next.
