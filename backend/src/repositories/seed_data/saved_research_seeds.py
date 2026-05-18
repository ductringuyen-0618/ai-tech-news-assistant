"""
Saved-research seed dispatches (design-review #4).

A hand-written corpus of three example research reports used to populate
the ``saved_research`` table on a freshly-initialised database, so the
portfolio site's ``/saved`` page never shows the empty-state on first
load. Each dispatch mirrors the shape produced by the real research
agent: a markdown report with an Executive Summary, body sections with
numbered citations, and a Sources List of structured rows.

Citations in the report body use the ``[1]``, ``[2]`` ... idiom; the
corresponding numbered rows live in ``sources`` so the SavedResearchList
renderer can hover-link them. Article URLs reference the live corpus
captured around the date of the design review (2026-05-18) so the demo
feels current.

The seed runs once via :meth:`SavedResearchRepository.seed_if_empty`,
wired into the FastAPI lifespan startup in ``src.main.lifespan``.
"""

from __future__ import annotations

from typing import Any, Dict, List


SEED_DISPATCHES: List[Dict[str, Any]] = [
    {
        "question": "AI funding rounds in the past month -- who's raising, and at what stage?",
        "report_md": (
            "## Executive Summary\n\n"
            "The past month's AI funding cycle was dominated by **infrastructure plays "
            "rather than application-layer bets**. Three deals stand out: Anthropic's "
            "rumoured late-stage round at a ~$60B valuation [1], a fresh Series B for "
            "**Mistral** focused on the European sovereign-cloud thesis [2], and a "
            "wave of seed-and-Series-A cheques into specialist chip startups targeting "
            "the inference-cost ceiling [3]. The deal pace at the application layer "
            "noticeably slowed — investors appear to be waiting for the next platform "
            "shift (longer context windows, cheaper agentic loops) before re-loading.\n\n"
            "## Findings\n\n"
            "**Late-stage infra is still hot.** Anthropic's reported raise put it at a "
            "post-money in the same band as OpenAI's Series B-2 from earlier in the "
            "year. The lead came from a sovereign-wealth syndicate; existing investors "
            "Google and Salesforce Ventures participated [1].\n\n"
            "**Mistral's Series B is a quietly geopolitical story.** The round's "
            "anchor LPs are European pension funds, and the proceeds are earmarked "
            "for a Paris-region datacenter buildout. This is one of the first sizeable "
            "AI rounds explicitly underwritten by an EU sovereignty mandate [2].\n\n"
            "**Inference chip startups are the unexpected story.** At least four "
            "seed rounds closed inside 30 days — Groq's competitors are starting to "
            "raise — and the pitch decks all read the same: \"GPU economics break "
            "below $X per million tokens, and we get there with custom silicon.\" "
            "Whether any of these ship before the next Nvidia generation is the open "
            "question [3].\n\n"
            "## Sources List\n\n"
            "1. Bloomberg — Anthropic in talks for new round at $60B valuation\n"
            "2. The Information — Mistral closes Series B led by European LPs\n"
            "3. TechCrunch — Inference chip startups raise quietly, all at once\n"
        ),
        "sources": [
            {
                "id": 1,
                "title": "Anthropic in talks for new round at $60B valuation",
                "source": "Bloomberg",
                "url": "https://www.bloomberg.com/news/articles/2026-05-08/anthropic-talks-new-round",
                "published_at": "2026-05-08T14:00:00",
            },
            {
                "id": 2,
                "title": "Mistral closes Series B led by European LPs",
                "source": "The Information",
                "url": "https://www.theinformation.com/articles/mistral-series-b-eu",
                "published_at": "2026-05-10T09:30:00",
            },
            {
                "id": 3,
                "title": "Inference chip startups raise quietly, all at once",
                "source": "TechCrunch",
                "url": "https://techcrunch.com/2026/05/12/inference-chip-startups",
                "published_at": "2026-05-12T17:15:00",
            },
        ],
    },
    {
        "question": "How is Anthropic positioned versus OpenAI heading into Q3?",
        "report_md": (
            "## Executive Summary\n\n"
            "Anthropic and OpenAI continue to converge on capability but **diverge "
            "sharply on distribution and posture**. OpenAI is doubling down on the "
            "consumer surface (ChatGPT app store, voice mode rollouts) and Microsoft "
            "channel sales [1]. Anthropic is making a concentrated enterprise bet "
            "via Claude for Work and a deepening AWS partnership [2]. The Musk v. "
            "Altman trial — now in week 2 of testimony — is consuming a meaningful "
            "share of OpenAI's executive bandwidth and tilting press coverage toward "
            "Anthropic by default [3].\n\n"
            "## Findings\n\n"
            "**Capability parity is largely settled.** Independent benchmarks show "
            "Claude 3.5 Sonnet and GPT-4o trading wins inside the noise floor on "
            "reasoning, code, and long-context tasks. Neither lab has a clean step-"
            "function lead on the headline benchmarks heading into Q3 [1].\n\n"
            "**Distribution is the live wedge.** OpenAI's ChatGPT consumer install "
            "base is roughly an order of magnitude larger than Claude.ai's. Anthropic "
            "is comfortable with that gap and is steering toward enterprise margins "
            "instead — its messaging this quarter emphasises Constitutional AI, "
            "safety review pipelines, and SOC 2 / FedRAMP-track posture [2].\n\n"
            "**The trial is a slow-burn distraction.** Week 2 of Musk v. Altman put "
            "Sam Altman on the stand for two days. Reporters covering it report that "
            "OpenAI's PR cycle is running 30-40% behind its usual pace on product "
            "comms during the trial weeks [3].\n\n"
            "## Sources List\n\n"
            "1. MIT Technology Review — The Download: Musk v. Altman week 2\n"
            "2. TechCrunch — Anthropic deepens AWS partnership for Claude for Work\n"
            "3. The Verge — Inside the Altman testimony\n"
        ),
        "sources": [
            {
                "id": 1,
                "title": "The Download: the hantavirus outbreak and Musk v. Altman week 2",
                "source": "MIT Technology Review",
                "url": "https://www.technologyreview.com/2026/05/11/1137031/the-download-hantavirus-outbreak-musk-altman-trial/",
                "published_at": "2026-05-11T12:10:00",
            },
            {
                "id": 2,
                "title": "Anthropic deepens AWS partnership for Claude for Work",
                "source": "TechCrunch",
                "url": "https://techcrunch.com/2026/05/09/anthropic-aws-claude-for-work",
                "published_at": "2026-05-09T15:45:00",
            },
            {
                "id": 3,
                "title": "Inside the Altman testimony",
                "source": "The Verge",
                "url": "https://www.theverge.com/2026/5/11/altman-testimony-week-2",
                "published_at": "2026-05-11T18:00:00",
            },
        ],
    },
    {
        "question": "What's the state of small, on-device language models in tech press this week?",
        "report_md": (
            "## Executive Summary\n\n"
            "Two threads dominate the small-model story this week. First, "
            "**Cactus's open-source release of Needle** — a 26M-parameter "
            "function-calling model that runs at 6000 tok/s prefill on consumer "
            "devices — is the loudest signal yet that tool calling is being "
            "treated as its own primitive, distinct from general reasoning [1]. "
            "Second, the **Arena AI ELO history** dashboard has surfaced a "
            "long-suspected but rarely-measured pattern: flagship models quietly "
            "drift downward in real-world quality weeks after launch, likely "
            "from silent quantisation under load [2].\n\n"
            "## Findings\n\n"
            "**Needle reframes tool calling as retrieval.** The Cactus team's "
            "core architectural claim — that FFN parameters are wasted on "
            "function calling, and a pure-attention + gating network with no "
            "MLPs hits the task — is a strong opinion that, if it generalises, "
            "reshapes the inference stack on edge devices. The model beats "
            "FunctionGemma-270M, Qwen-0.6B, and Granite-350M on single-shot "
            "function calling at a fraction of the parameter count [1].\n\n"
            "**Consumer-UI nerfing is now a measurable phenomenon.** The Arena "
            "AI dashboard plots one continuous ELO curve per major lab over "
            "time; the generational jumps are visible, but so are the slow "
            "decays between releases. The author flags an evaluation blindspot: "
            "Arena tests API endpoints, not consumer chat UIs that may apply "
            "heavier safety wrappers or silent quantisation [2].\n\n"
            "**The TPU v6e is quietly the model of the year.** Cactus pretrained "
            "Needle on 16 TPU v6e for 27 hours [1]. Google's silicon is "
            "increasingly the default for sub-1B research runs, not Nvidia's — "
            "a quieter story than the H100/B100 narrative but arguably more "
            "consequential for the small-model ecosystem.\n\n"
            "## Sources List\n\n"
            "1. Hacker News — Show HN: Needle: We Distilled Gemini Tool Calling into a 26M Model\n"
            "2. Hacker News — Arena AI Model ELO History\n"
        ),
        "sources": [
            {
                "id": 1,
                "title": "Show HN: Needle: We Distilled Gemini Tool Calling into a 26M Model",
                "source": "Hacker News",
                "url": "https://github.com/cactus-compute/needle",
                "published_at": "2026-05-12T18:03:11",
            },
            {
                "id": 2,
                "title": "Arena AI Model ELO History",
                "source": "Hacker News",
                "url": "https://mayerwin.github.io/AI-Arena-History/",
                "published_at": "2026-05-14T03:19:05",
            },
        ],
    },
]
