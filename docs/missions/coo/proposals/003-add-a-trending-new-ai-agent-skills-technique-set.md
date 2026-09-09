---
title: >-
  add a trending new ai agent skills/technique/setup that need to learn, add to
  your ai agent setup
status: proposed
attempts: 0
branch: null
---
# add a trending new ai agent skills/technique/setup that need to learn, add to your ai agent setup

# Trending AI Agent Skills — a "Learning" feed for the developer setup toolkit

## What you get

A new **Learning** tab in TechPulse that surfaces trending AI agent
skills, techniques, and setups the developer community is actively
adopting right now — new Claude Code skills, Cursor rules, autonomous
coding-agent workflows, notable agent frameworks and "everything you can
do with X" roundups. Each item is a short card: what it is, why it's
gaining traction, a link to the source, and (where TechPulse already
extracts entities) tags linking it to related tools/techniques already
in the knowledge graph. Users get a running, always-fresh list of "what
should I add to my agent setup this week" instead of having to piece it
together from scattered tweets, Discords, and blog posts.

## Why start this now

TechPulse's core loop is already "ingest → summarize → surface," and the
AI-agent-tooling space (Claude Code, Cursor, autonomous dev workflows) is
one of the fastest-moving, highest-engagement topics in the current tech
news cycle — exactly the kind of content that drives return visits and
sharing. Proposal 002 (personalized feed reactions) just shipped and
proved the pattern of adding a lightweight, no-new-infra content surface
on top of the existing pipeline; a Learning feed is the natural next
increment on the same rails, riding current interest before it cools.

## Problem

There is currently no dedicated place in TechPulse where a developer can
see, at a glance, which new AI agent skills/techniques/setups are
trending in the community. General tech news items get mixed into the
main feed with no distinction between "here's a headline" and "here's a
concrete thing you could add to your own agent setup today." The request
specifically calls out examples like pstack-style skill packs, the Grok
bot, "everything Claude Code," and autonomous-development workflows —
recurring, learnable patterns that today have no home in the product.

## Proposed solution

Backend (FastAPI):
- Add a new content category `learning_item` alongside the existing
  news-article model, reusing the existing ingestion → summarization
  pipeline rather than building a parallel one.
- Extend the RSS/source ingestion config to include a curated set of
  high-signal sources for agent tooling: e.g. GitHub trending
  (`agent`, `skills`, `mcp`, `claude-code` topics), the Anthropic/OpenAI/
  Cursor engineering blogs, and 1-2 community aggregators (Hacker News
  "AI agents" search, a relevant subreddit). Keep the source list in
  config, not hardcoded, so it can be tuned without a redeploy.
- Filter incoming items using tags/patterns that indicate "skill",
  "technique", or "setup" content (e.g. title/body regex for "skill",
  "workflow", "agent setup", "MCP", "subagent") before running the
  existing summarizer, so the feed doesn't just become "AI news" again.
- Run the existing summarization step to produce a short "what it is /
  why it matters" card, and reuse the existing entity-extraction step to
  tag each item with the tools/techniques it references, so it links
  into the existing knowledge graph like any other entity.
- Add a `GET /api/learning` endpoint (paginated, same shape as the
  existing feed endpoint) serving these items sorted by recency/signal
  score.

Frontend (Vite/React):
- Add a new top-level tab, **Learning**, alongside the existing
  news/search/digest/knowledge-graph tabs.
- Reuse the existing feed card component styling; each card shows title,
  one-line summary, source link, and entity tags (clicking a tag jumps
  into the existing knowledge graph view filtered to that entity).
- No new personalization/reaction mechanics required for v1 — this can
  layer on top of the existing feed-reactions work later if desired, but
  is out of scope here.

## Effort estimate

**Medium** — no new infrastructure or services, but it touches both the
ingestion config, a new content category/endpoint on the backend, and a
new tab + card view on the frontend, so it's more than a docs-only or
single-file change.

## Validation contract

- Backend: `pytest` passes; new tests cover the `learning_item` model,
  the `/api/learning` endpoint (pagination, empty state), and that
  ingestion correctly tags an item as `learning_item` vs. regular news
  given sample source content.
- Frontend: `tsc`/typecheck and lint pass; a component test renders the
  Learning tab with a mocked API response and confirms cards render
  title, summary, source link, and entity tags.
- Manual check: with at least one seeded learning item, load the
  Learning tab in the running app and confirm it displays without
  errors, the source link opens the original post, and clicking an
  entity tag navigates to the knowledge graph filtered to that entity.
- No regressions in the existing news feed, search, digest, or knowledge
  graph tabs (existing test suites for those must still pass).

## Risks

- Source quality/noise: community "trending" sources (Reddit, HN) are
  noisier than curated blogs and may need a signal/keyword filter to
  avoid surfacing low-value posts — start with a small, high-trust
  source list and expand only if the signal holds up.
- Duplicate/near-duplicate items across sources covering the same tool
  release; dedup logic may need tuning after the first real ingestion
  run rather than being fully solved upfront.
- Out of scope for this proposal: personalized ranking/reactions on
  Learning items, notifications/alerts for new items, and any ingestion
  source that requires paid API access or new credentials.
