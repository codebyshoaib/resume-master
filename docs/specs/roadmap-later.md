# Roadmap — Next / Later (Resume Master)

Companion to [`now-features-spec.md`](./now-features-spec.md). These are **deferred on purpose**. Each item names the metric that would justify building it — gate on data from Feature 3 (Instrumentation), not gut.

**North Star:** interview callbacks per user. **Guardrail everywhere:** zero fabricated skills.

---

## NEXT — build once instrumentation shows the signal

| Item | Outcome | Gate to build (metric) | Effort | Risk |
|------|---------|------------------------|--------|------|
| **JD-from-URL** — paste a job link, auto-scrape the JD instead of pasting text | Kills per-application friction; feeds the tracker | Users paste JD text on ≥3 distinct jobs/week (from `tailor_started` events) | M | Scraper fragility across job boards; needs a resilient fetch + readability extraction, per-site fallbacks |
| **Gap coaching** — for each missing keyword, suggest how to honestly reframe existing experience to cover it | Higher after-score without fabrication; deepens the value moment | Median before→after delta < target, i.e. tailoring leaves gaps users can't self-close | M | Must lean on existing truthfulness/alignment guardrails — coaching suggests reframing, never invents |
| **Wire cover-letter / interview-prep into the post-tailor moment** | Increases feature discovery + session value (both already exist, just not in the win loop) | `cover_letter_generated` fires on < ~20% of `tailor_completed` | S | Low — mostly surfacing existing endpoints at the right moment |

---

## LATER — explicit NO for now (with the trigger that flips it to YES)

| Item | Why NO now | Flips to YES when |
|------|-----------|-------------------|
| **More templates / more languages** | Vanity breadth; you already have multiple templates and 5 languages. Opportunity cost = the NOW bets | Users request a specific missing template/locale, or download rate is high but users cite "design" as the drop reason |
| **Chrome extension (Simplify-style JD capture + autofill)** | High desirability but heavy build; premature without proof of repeat use | Instrumentation shows users tailoring **>5 resumes/week** — i.e. per-application friction is the real bottleneck |
| **Accounts / multi-user / billing (SaaS)** | This is a personal/self-hosted tool today; auth + multi-tenancy + billing is a different product | You decide to productize for others (deliberate strategic pivot, not a feature request) |
| **AI resume *generation* from scratch** | Truthfulness risk is highest here; tailoring existing truth is the defensible position | Never, unless paired with a strict source-of-truth intake that forbids fabrication |

---

## Sequencing rationale

1. **NOW** sharpens the core loop (visible score) + delivers the literal ATS promise (linter) + removes the blindfold (instrumentation).
2. **NEXT** reduces friction and closes score gaps — but only after data confirms those are the bottlenecks.
3. **LATER** items are big-surface bets that should never be taken on faith; each has an explicit, measurable trigger.

Every "yes" above is a "no" to something else. For a solo builder, the discipline *is* the strategy.
