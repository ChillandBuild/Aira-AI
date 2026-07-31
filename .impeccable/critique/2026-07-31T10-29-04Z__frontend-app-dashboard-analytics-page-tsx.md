---
target: Analytics page in dashboard
total_score: 18
max_score: 40
na_heuristics: 
p0_count: 0
p1_count: 3
timestamp: 2026-07-31T10-29-04Z
slug: frontend-app-dashboard-analytics-page-tsx
---
Method: dual-agent (A: /root/analytics_design_review · B: /root/analytics_evidence_review)

## Design Health Score

| # | Heuristic | Score | Key Issue |
|---|---|---:|---|
| 1 | Visibility of system status | 2 | A single range selector conceals several incompatible time scopes. |
| 2 | Match system / real world | 3 | Familiar terms, but internal concepts such as Segment A and AI Automation lack explanation. |
| 3 | User control and freedom | 2 | Presets and tabs exist; custom dates, saved views, and in-context drill-downs are absent. |
| 4 | Consistency and standards | 2 | Equal cards imply comparable scope when they are not comparable. |
| 5 | Error prevention | 1 | The interface permits confident decisions based on incompatible metrics. |
| 6 | Recognition rather than recall | 2 | Users must remember which cards honor the selected range. |
| 7 | Flexibility and efficiency | 2 | Overview lacks owner/channel/campaign filters and decision shortcuts. |
| 8 | Aesthetic and minimalist design | 2 | Eight same-weight cards flatten priority and repeat the lead-pipeline story. |
| 9 | Error recovery | 2 | Primary fetches retry, but secondary overview failures are silently hidden. |
| 10 | Help and documentation | 0 | No definitions, freshness state, or scope guidance. |
| **Total** | | **18/40** | **Needs structural simplification** |

## Design Specificity Verdict

The visual treatment is calm and professional, but the dashboard is category-interchangeable: a grid of equal white KPI cards followed by generic charts. More importantly, its data story is not coherent. The selected range is global in appearance, while Total Leads, Hot Leads, Conversions, segment distribution, channel split, and funnel are calculated from all leads; AI automation, money, reply time, and daily charts are range-scoped; unreplied is a rolling 24 hours; average score, hot-lead aging, and stale leads are supplied by separate unscoped requests. This is the main source of confusion, not merely visual density.

The deterministic scan found 0 mechanical style-rule findings. It did not contradict the human assessment because its rules do not evaluate metric semantics. Browser inspection could not run: there was no local app listener on common development ports, and navigation to localhost:3000 returned ERR_CONNECTION_REFUSED.

## Overall Impression

This is a capable reporting surface masquerading as an operational home. It lets an experienced user find answers, but it does not make the next decision obvious. Its biggest opportunity is to replace a broad inventory of metrics with a clear decision hierarchy: what needs attention now, how the selected period performed, and only then how the overall pipeline is shaped.

## What's Working

- The visual system is restrained and consistent: cards and section containers are easy to scan.
- It includes meaningful operational information, especially unreplied conversations and stale hot leads, rather than vanity metrics alone.
- Daily lead and message activity are useful diagnostic charts once the primary decision is already clear.

## Priority Issues

### [P1] One range selector, several incompatible periods

**Why it matters:** Choosing 7 Days appears to change the whole page but does not. Users can compare all-time leads against seven-day cost and response time as though the cards describe one period.

**Fix:** Make the selected period govern every metric in the performance band. If all-time/current-pipeline facts are needed, move them to a separate, explicitly labelled Pipeline Health section. Put a visible scope label on every exception metric, for example “Last 24 hours” and “All time”.

**Suggested command:** `$impeccable distill`

### [P1] The first fold has no priority

**Why it matters:** Eight equal cards ask the user to decide what matters before the product offers a point of view. Total Leads, Hot Leads, Conversions, funnel, and segment distribution repeat the same pipeline story at different levels.

**Fix:** Replace the grid with three groups: Needs attention (unreplied, stale hot leads, SLA); Selected-period performance (new leads, qualified rate, conversions, cost per qualified lead, deltas); Pipeline health (one compact funnel or segment distribution, not both). Remove the standalone Hot Leads total; use Hot leads needing action or hot-lead conversion rate instead.

**Suggested command:** `$impeccable shape`

### [P1] Actionable exceptions do not resolve directly

**Why it matters:** Unreplied 24h is visually urgent but there is no action from the card, and each stale-lead row goes to a generic Segment A list rather than the exact lead or a reply queue.

**Fix:** Make the attention block a real work queue: show owner, channel, age, and next action; link each row to the exact conversation. Add one dominant CTA such as “Resolve 12 waiting hot leads”.

**Suggested command:** `$impeccable harden`

### [P2] Tabs overlap and ignore filters inconsistently

**Why it matters:** Overview, Channels, and Inbound each repeat message/lead volume, but with different cuts. Templates ignores the visible date pills entirely. The Channels tab combines Today KPIs with selected-range charts, and one “split” omits unknown source messages.

**Fix:** Rename tabs by job: Overview, Acquisition, Messaging, Campaigns, Compare. Hide or disable a global date control wherever it does not apply, or make it apply. Keep “today” indicators only in the attention strip. Include Unknown in the reply-source total or label the split as partial.

**Suggested command:** `$impeccable clarify`

### [P2] Critical semantics and accessible states are hidden

**Why it matters:** A manager cannot learn how metrics are calculated or if data is current. Tab and channel selected states are visual only; charts provide generic labels but not accessible summaries or data alternatives.

**Fix:** Add metric definitions/tooltips, last-updated state, and explicit tab/pressed ARIA semantics. Add a short textual summary and table download/view for every chart; retain a persistent legend for color-encoded charts.

**Suggested command:** `$impeccable audit`

## Persona Red Flags

**Business owner:** Cannot answer “Did we improve this week?” because conversion count, lead total, cost, and quality do not share a consistent denominator or time period. ROI is not presented as a decision.

**Operations manager:** Sees an unreplied warning but not the queue owner, age, channel, or direct resolution path. The useful signal stops just before the operational step.

**Power user:** Cannot set a custom range, preserve a view, or filter Overview by channel, campaign, or owner; has to leave the central view to investigate.

## Minor Observations

- “Conversions” visually reads as current-period beside “today”, although its total is all-time.
- Total Leads hides Upload and Manual in the tiny channel breakdown although the API returns them.
- The range selector stays visible for Templates despite having no effect.
- Secondary overview requests fail silently, which can turn unavailable data into an em dash or missing section without explanation.
- The message charts have no persistent legend, so their colors must be remembered from hover state.

## Questions to Consider

- In the first 20 seconds, should the page answer “what should my team do now?” or “what has happened?”
- Which metric earns a fixed place on the overview only if it changes the next action?
- Would a business owner trust a 7-day view if every number clearly stated its period?
