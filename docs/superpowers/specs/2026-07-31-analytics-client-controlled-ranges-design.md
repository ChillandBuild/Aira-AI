# Client-Controlled Analytics Ranges

## Job and audience

Business owners and operations managers use `/dashboard/analytics` to decide what requires action and how a chosen reporting period performed. The page must never infer that a comparison is wanted or imply that unrelated time scopes are comparable.

## Outcome and proof

- The client chooses a reporting period from presets or an explicit start/end date.
- Comparison is disabled by default; when enabled, the client chooses either a prior-period preset or a separate custom start/end range.
- Every performance metric, funnel, and trend in Overview uses the chosen reporting period; service-risk items remain explicitly labelled “Last 24 hours”.
- The UI visibly states the active reporting period and, only when enabled, the exact comparison period.

## Selected direction

- Retain the product’s existing quiet card-and-chart visual language, but replace the eight equal KPIs with decision order: Needs attention, selected-period performance, then diagnostic pipeline/trend.
- Use the existing range picker as the reporting-period control, extended by a dedicated comparison control with Off as its initial state.
- Reuse the period-summary RPC family behind `/api/v1/analytics/compare` so every selected-period metric is calculated from one coherent period; do not change the legacy `/overview` contract consumed by Dashboard home and operator console.

## Scope and boundaries

- Modify the dashboard Analytics page, shared range controls, comparison API contract, API client types, and focused backend/frontend tests.
- Keep dedicated Acquisition, Messaging, Campaigns/Templates, and Compare diagnostic views available; their filters must be explicit about whether they inherit the reporting period.
- Do not change database schema or existing RPC signatures.
- Do not remove the existing all-time dashboard-home overview or silently convert it to a custom-range report.

## States and interactions

- Reporting period: existing presets plus Custom with valid inclusive start/end dates; incomplete or invalid custom periods do not issue a request.
- Comparison: Off, Previous comparable period, or Custom. Custom comparison stays disabled until both valid dates are selected.
- If comparison is Off, show current-period values with no delta, previous series, or comparison copy. If ranges differ in length, label both date spans and avoid claiming a like-for-like total comparison; charts use day index only when comparing.
- Retain retry states. Secondary operational data failures must be visible rather than silently rendering missing content.

## Constraints and open decisions

- Preserve IST calendar-date semantics already used by the period-comparison endpoint.
- Use labelled controls, selected-state ARIA attributes, accessible chart summaries, and direct links from attention items to the relevant lead/conversation queue.
- No automatic comparison is introduced anywhere in the redesigned Overview. Existing Compare behavior changes only as part of the explicit comparison control.
