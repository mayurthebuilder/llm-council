# LLM Council for Digital Marketing — Specialization Design

**Status:** Approved for implementation  
**Date:** 2026-09-01  
**Extends:** `2026-08-30-llm-council-portfolio-v2-design.md`

## Product position

LLM Council is a privacy-conscious, multi-agent decision-support tool for digital
marketing. Five specialist advisors independently evaluate a marketing question,
blind-review one another's recommendations, and produce one structured chairman
synthesis with consensus, dissent, risks, assumptions, and next actions.

It is strategy-first and execution-aware. It supports campaign planning and
content direction, but it is not an autonomous campaign publisher, an analytics
platform, or a substitute for verified market and performance data.

## Default marketing council

1. **Brand and audience strategist** — positioning, segmentation, customer insight,
   messaging, differentiation, and brand consistency.
2. **Growth and channel strategist** — acquisition, lifecycle, paid/organic channel
   mix, funnel design, budget tradeoffs, and experimentation.
3. **SEO, AEO, and GEO strategist** — technical/on-page SEO, answer-engine
   eligibility, entity clarity, structured content, citation-worthiness, and
   discoverability in generative experiences.
4. **Creative and content strategist** — campaign concepts, content systems,
   distribution formats, conversion journeys, and creative feasibility.
5. **Measurement and marketing-risk analyst** — KPI design, incrementality,
   attribution limits, privacy, compliance, reputational risk, and unsupported
   assumptions.

The chairman must reconcile these perspectives without exposing advisor or model
identity during peer review.

## AEO and GEO boundary

- **SEO** improves discovery and ranking in conventional search.
- **AEO** structures trustworthy, concise answers for answer engines, featured
  answers, and conversational retrieval.
- **GEO** improves how clearly a brand or source can be understood, retrieved,
  and cited by generative search systems.

The council must not promise rankings, citations, traffic, or revenue. It should
recommend testable tactics such as entity consistency, original evidence,
structured pages, answer-first content, expert attribution, crawlability, and
measurement plans. It must distinguish supplied facts from recommendations and
call out when current search-platform evidence is missing.

## Primary workflow

```bash
llm-council run \
  --question "How should a fictional B2B SaaS launch build qualified demand?" \
  --context-file examples/digital-marketing-launch-context.md \
  --format markdown
```

The offline demo returns a fixed, explicitly labelled simulation for a fictional
B2B SaaS launch. A live Google-provider run analyzes the supplied question and
optional context only after explicit provider selection.

## Structured output

The existing `CouncilDecision` contract remains stable. Marketing recommendations
map to:

- recommendation and rationale;
- consensus and material dissent;
- assumptions and evidence gaps;
- channel, content, SEO/AEO/GEO, measurement, and brand risks;
- prioritized next actions and experiments;
- bounded confidence.

This avoids a marketing-only schema fork while keeping outputs useful for both
humans and downstream tooling.

## Evaluation scenarios

Offline deterministic fixtures will cover at least:

- B2B SaaS go-to-market and channel mix;
- AEO/GEO content and authority plan;
- paid-versus-organic budget allocation;
- campaign positioning and creative direction.

Tests verify structure, specialist coverage, dissent, evidence gaps, safe output,
and deterministic execution. They do not claim that simulated recommendations are
factually superior or commercially effective.

## Public presentation

The repository name remains `llm-council`; the title, description, README, CLI
help, examples, diagrams, metadata, and CV language must consistently say
**LLM Council for Digital Marketing**. The README will explicitly include SEO,
AEO, GEO, growth, content, paid/organic channels, measurement, privacy, and the
limitations of model-generated strategy.

## Acceptance criteria

1. All five default advisors are marketing specialists, including one explicit
   SEO/AEO/GEO role.
2. No billing or generic build-versus-buy demo remains in user-facing assets.
3. Offline demo and evaluation fixtures are fictional, deterministic, and clearly
   labelled simulated.
4. README and CLI explain AEO and GEO without promising outcomes.
5. Existing privacy, anonymity, quorum, output-safety, and provider-boundary tests
   continue to pass.
6. Full tracked-content and Git-history scans contain no personal Gmail address,
   private path, session URL, or secret.

