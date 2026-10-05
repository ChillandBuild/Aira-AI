# Template Builder — Meta Safety Checks

Goal: cut template rejections by catching Meta's rules on screen, before submit — without scaring new clients
with warnings that aren't real rules.

## Principle (from the user, 2026-10-05)

1. **If we can fix it safely, fix it automatically** and show a small grey note saying what changed.
   The client sees the final text, so what they approve is exactly what Meta receives.
2. **Block only what we can't fix for them.** Continue / Submit stay disabled, with one calm line under the
   field at fault saying how to fix it.
3. **Advisory rules are calm tips**, never blocking, never orange alarm text.
4. Every rule is sourced from Meta's official docs. No invented thresholds.
5. **Keep the existing design.** No restyle of the builder: same layout, step flow, `.input` fields, emerald
   Continue/Submit button, WhatsApp preview, fonts and spacing. This build only adds the safety checks and the
   missing features (sample boxes, auto-fix notes, disabled-with-reason button). New pieces reuse the page's
   existing classes and the existing message style (`font-body text-[11px]`, red-600 for blockers as today).

## Design decisions (approved 2026-10-05, specimen: claude.ai/artifact/832nwajGmSYi2cnJYnjDw1)

- **Messages under each field.** Three kinds, each with its own lucide icon so colour is never the only signal:
  auto-fix note = emerald-700 + `CheckCircle2`; blocker = red-600 + `AlertCircle` (matches today's red);
  tip = `text-ink-muted` + `Lightbulb`. Auto-fix notes fade after 6 s; blockers and tips stay while true.
  The old orange ratio warning and the purple "mixing buttons" box are removed.
- **Continue / Submit disabled with a reason.** Existing emerald button keeps its `disabled:opacity-50` look.
  To its left: "**Fix N things** to continue" — the link is a real button that focuses and scrolls to the
  first field at fault. With nothing to fix, nothing extra shows.
- **Sample boxes right under the text.** Under the body (and the header, and a URL button) as soon as a
  variable exists: one row per variable, `{{n}}` chip (same green chip as today's VARS row) + `.input`.
  The live preview shows sample values in place of `{{n}}`; a missing sample shows as the plain `{{n}}`.
- **Accessibility + phone width required.** Message areas are `aria-live="polite"` and linked with
  `aria-describedby`; fields with a blocker get `aria-invalid`; fix links/buttons are keyboard reachable with
  a visible focus ring; existing responsive grid unchanged (preview already drops under the form on mobile).

## Rules and how each is handled

| Rule (Meta source) | Today | New behaviour |
|---|---|---|
| Name: lowercase, letters/numbers/underscore, ≤512 (Overview) | Auto-cleaned, preview shown | Keep as is |
| Body ≤1024 chars (Components) | `maxLength` | Keep |
| No variable at very start / end (Template review) | Blocks on Next | **Block live**, message: "Add a word before/after {{1}}" |
| Variables numbered {{1}}, {{2}}… no gaps (Overview) | Blocks on Next | **Block live** + one-click **"Fix numbering"** button that renumbers in order |
| Broken braces `{{1}`, `{{ 1 }}` (Template review) | Not checked | **Auto-fix** `{{ 1 }}` → `{{1}}` with note. Unclosed / stray braces → block |
| Named or special-char variable `{{name}}`, `{{#}}` in a numbered template (Template review) | Silently ignored, Meta rejects | **Block**: "Use Insert Variable to add numbered variables" |
| **Sample value for every variable** (Components, Utility) | Server invents "Rajan Kumar" / "Sample text" | **New "Sample value" box per variable** under body, header, URL. Block until filled |
| Too many variables for the length (Template review — no number published) | Orange warning at <6 words/var | **Calm tip only**, only below 3×vars+1 words (industry-reported floor). Grey, not orange |
| Text header ≤60, max 1 variable (Components) | 60 enforced; variables not checked | **Block** a 2nd header variable; sample box for the 1 allowed |
| Header: no emoji, no `* _ ~ \`` (Components) | Emoji blocks; symbols silently stripped on server | **Auto-remove as typed** + note "Removed emoji/formatting — WhatsApp doesn't allow it in headers" |
| Footer ≤60, no variables (Components) | 60 enforced | **Block** `{{…}}` in footer |
| Button label ≤25, letters/numbers/spaces (Utility) | 25 enforced; emoji stripped silently on server | **Auto-remove emoji/symbols as typed** + note |
| Button label unique (Template review) | Red box | Keep, make it inline under the label |
| Quick replies grouped together, not mixed between others (Components) | Shows an unnecessary "mixing is supported" warning | **Auto-group**: quick replies kept together, note "Reordered so quick replies sit together". **Remove** the old mixing warning |
| ≤10 buttons, ≤2 URL, ≤1 phone, ≤1 copy code (Components) | Enforced in picker | Keep |
| URL ≤2000, starts with https, max 1 variable, only at the end (Components) | Not checked; sample sent wrong | **Auto-add `https://`** on blur with note; **block** variable not at end / >1 variable; sample box for the variable |
| Phone ≤20, digits only (Components, Utility) | Not checked | **Auto-strip** spaces, dashes, brackets as typed |
| Copy-code value ≤20 (Components) | Enforced | Keep |
| Duplicate body+footer of an existing template, non-auth (Template review) | Not checked | **Block on submit** (server), message names the existing template |
| Utility with marketing wording gets re-categorised (Utility) | Nothing | **Calm tip** under category when Utility chosen |

## Where

- `frontend/app/dashboard/templates/template-rules.ts` (new, pure functions): `checkBody`, `checkHeader`,
  `checkFooter`, `checkButtons`, `autoFixLabel`, `autoFixHeader`, `autoFixPhone`, `autoFixUrl`,
  `groupQuickReplies`, `renumberVariables`. Each returns `{ fixed?, notes[], blockers[], tips[] }`.
  Replaces `validateTemplateBody` / `templateBodyWarning` in `types.ts`.
- `components/variable-inserter.tsx` — live blockers, tip, "Fix numbering", sample-value boxes.
- `components/button-builder.tsx` — label/phone/URL auto-fixes, URL sample box, auto-grouping, drop mixing warning.
- `new/page.tsx`, `[id]/page.tsx` — header/footer auto-fix + blockers; Continue/Submit disabled while any
  blocker exists; send samples in the payload.
- `carousel/page.tsx` — body rules + samples for the main body and each card.
- `backend/app/routes/templates.py` + `services/meta_cloud.py` — accept `body_examples`, `header_example`,
  per-button `url_example`; use them instead of invented samples; repeat every blocking rule as a 400 so the
  API can't be bypassed; duplicate body+footer check.

**No DB migration.** Samples are only needed at submit time. The edit page asks for them again (empty boxes).

## Out of scope (found, noted for later)

- Authentication templates: Meta's body text is fixed, but our builder lets the client type one. Separate job.
- Escalation alert: clean line breaks from the AI-written reason (`whatsapp_notify.py:126`). One-line fix, separate commit.
- Escalation variable picker + silent-failure fixes — next after this.
- Location header — our builder doesn't offer it, so no rule needed.

## Tests

- Backend pytest: payload builder uses client samples (body, header, URL); each blocking rule returns 400;
  duplicate check; old invented-sample path gone.
- Frontend: `template-rules.ts` is pure — typecheck + lint clean; verify each rule by rendering the builder
  locally and screenshotting the states (clean, auto-fixed note, blocker, tip) before showing the user.
- Regression: an existing approved template (e.g. `escalation_alert`) opens in the edit page with no warnings.

## GSTACK REVIEW REPORT

| Run | Status | Findings |
|---|---|---|
| plan-design-review (focused: 4 gaps, user choice) | issues_found → resolved | 4 found, 4 approved (D2–D5), 0 deferred |

| Gap | Before | After | Decision |
|---|---|---|---|
| Message styles (fix / blocker / tip) | 3/10 | 9/10 | D2: under each field, icon + colour per kind |
| Reason for disabled Continue | 2/10 | 9/10 | D3: disabled + "Fix N things" jump link |
| Sample-value boxes | 4/10 | 9/10 | D4: right under the text, preview fills in |
| Accessibility + phone width | 1/10 | 9/10 | D5: required |

Overall design completeness: 5/10 → 9/10. Remaining point: final copy for each blocker is drafted in the
specimen and will be checked on the real page during build QA. Constraint added by the user: keep the
existing design, add only safety checks and missing features. Outside voices: not run (focused review).
Mockups: live coded specimen instead of generated images (user choice).

VERDICT: Design-ready for implementation.

NO UNRESOLVED DECISIONS
