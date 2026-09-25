# TeleCMI Call Scoring — Phase 1 (Sort + Mark) Design

**Date:** 2026-09-25
**Source method:** "Telecaller Evaluation – Complete Method, CallIQ Steps 1 to 6" (client document). This spec covers **Step 1 (sorting calls)** and **Step 2 (marking each real conversation)** for **TeleCMI calls only**.
**Out of scope (later phases):** red cards + review actions (Phase 2), overall score / effort / hours worked (Phase 3), ranking + winners (Phase 4), daily coaching card (Phase 5), disputes, admin-editable settings, rule versions UI (Phase 6), SIM calls (after TeleCMI).

---

## 1. Decisions made with the user

| # | Decision |
|---|---|
| Q1 | Build in phases; Phase 1 = Step 1 + Step 2 only. |
| Q2 | Talk share by **words** from the transcript (document rule). Interruptions from the **two audio tracks** (real overlap), with "telecaller keeps talking ≥ ~1s" standing in for the document's "≥ 3 words". |
| Q3 | CRM check (check 10 + early-exit check) uses the **existing** wrap-up: outcome, manual status, do-not-call, callback date, notes. "interested" is accepted for both Hot and Warm. The manual outcome marking is **not changed** in this phase. |
| Q4 | Nine checks are marked as soon as the recording is processed; check 10 is marked when the wrap-up is saved. The score shows **provisional** until then. No wrap-up within **2 hours** → check 10 = **Missing**, score final. |
| Q5 | The admin "which criteria to score" setting and the audio **Tone** check are **removed completely**. |
| Q6 → Q8 | Every transcript line carries its time in the call. Because the AI swapped telecaller/customer on the 2026-09-25 test call, each audio track is **transcribed separately**, which makes speaker labels certain and times exact. |
| Q7 | All warnings go to the **admin** (no "manager" role). No per-warning notifications: a **Needs attention** list with a sidebar count, one **morning summary** notification, and instant alerts only for **rudeness** and **wrong product information**, capped at 1 per telecaller per hour. Telecallers see their own warnings on the call card only. |
| — | Calls under 30s and not-connected calls get no AI at all and are labelled **"Not scored · under 30s"** / **"Not scored · not connected"**. |

## 2. Verified facts this design relies on

- **TeleCMI recordings are stereo WAV, 8 kHz, 16-bit, one person per channel.** Checked on 2 real recordings (`9c1c3907…`, `ed296fa2…`); on the second, speech bursts alternate cleanly between channels and only ~5% of samples are identical across channels.
- **Right channel = telecaller, left channel = customer.** Confirmed by the user on call `ed296fa2…` (they were the caller; their speech is on the right channel). Stored as one constant (`TELECALLER_CHANNEL = 1`) so it can be flipped if TeleCMI ever changes.
- **The current single-pass transcript swapped the speakers** on that call, so AI-guessed labels cannot be trusted.
- **`call_logs.duration_seconds` for TeleCMI is the customer leg's `answeredsec`**, which already excludes ringing (`routes/calls.py` CDR handler). The 30-second rule needs no change.
- **No call has ever been given a score** (`call_logs.score` is null on every row) and **no tenant has a custom `score_criteria`**. The /10 → /100 switch and criteria removal affect no historical data.
- On the test call the old system gave **7.9/10, "real conversation"** to a casual chat with no sales content. The new rules give **0 signs → Early exit**.

## 3. Call flow

```
TeleCMI CDR arrives
 ├─ not answered / failed ─────────────► group = not_connected   (no AI)
 ├─ answered, duration < 30s ──────────► group = very_short      (no AI, no transcription)
 └─ answered, ≥ 30s → recording queued
        │
        ▼
  1. Split stereo into two mono tracks (telecaller = right, customer = left)
  2. Voice-activity timeline per track (no AI)
  3. Transcribe each track separately (Gemini), lines with start times
  4. Merge both tracks' lines by start time → speaker-certain transcript
  5. Talk share (words) + interruptions (tracks) (no AI)
  6. AI step A: find the 6 signs, each with quote + speaker
  7. System validates quotes (exists in transcript, right speaker) and counts signs
        ├─ < 2 valid signs → group = early_exit → early-exit check (answered in the same AI step A call)
        └─ ≥ 2 valid signs → group = real_conversation → AI step B: 10 checks
  8. System computes marks, applies caps, totals, top-2 weakest
  9. Check 10 waits for wrap-up (or 2h cut-off) → score final
```

Transcript failure: retried once (existing retry mechanism). If the second attempt fails, the call gets a `transcript_failed` warning in Needs attention and stays out of all scoring.

## 4. Components

Each unit has one job and is testable on its own.

### 4.1 `services/call_tracks.py` (new, no AI)
- `split_stereo(wav_bytes) -> (telecaller_pcm, customer_pcm, sample_rate)`. Mono or unreadable audio → raises `NotStereo`. That call falls back to a single-track transcript; interruptions become `null` and a warning is logged.
- `speech_segments(pcm, sample_rate) -> list[(start_s, end_s)]`. Energy per 100 ms frame against a noise floor estimated from the track's own quietest frames, with a minimum speech run and gap-merging. This makes steady line hiss (seen on the left track of call `9c1c3907…`) read as silence.
- `count_interruptions(telecaller_segs, customer_segs) -> int`. Counts one when the customer segment has started, the telecaller segment starts inside it, the overlap is ≥ 1.0 s, and the telecaller segment lasts ≥ 1.0 s. Customer-over-telecaller overlaps are not counted.
- `per_5_min(count, duration_s)`.

### 4.2 Transcription (in `call_summarizer.py`)
- Each mono track is encoded and transcribed with a per-track prompt: *"Only one speaker is on this track… return one line per utterance as `[mm:ss] text`, verbatim, original language/script, `[inaudible]` when unclear, nothing if silent."* Chunking (`split_audio`) applies per track as today.
- Lines are merged by time into the stored `call_logs.transcript` format `"[mm:ss] Telecaller: …"` / `"[mm:ss] Customer: …"`.
- Each line's AI time is snapped to the nearest start of a speech segment on its own track (within ±3 s). If no segment is near, the AI time is kept.
- Transcription runs with **temperature 0**.
- **Word-clue backup (user's suggestion, 2026-09-25).** If the recording is not stereo (`NotStereo`), the mixed audio is transcribed in one pass. The prompt then tells the AI to identify the telecaller by clues: saying the company name, "calling from…", introducing themselves, referring to the enquiry, or explaining the product/price. The customer is the one asking about it.
- **Word-clue cross-check.** On stereo calls, the same clues are checked on both tracks by plain text matching (company name from tenant settings, plus phrases like "calling from", "பேசுறேன்", "from … company"). If the clues appear only on the customer track, a `tracks_swapped` warning is raised. It's a hint for the admin; the channel mapping is not changed automatically.

### 4.3 `services/call_metrics.py` (new, no AI)
- `talk_share(lines) -> float | None`. Words per speaker, ignoring filler tokens (`hmm, uh, um, aah, ah, ok ok, mm`, Tamil/Hindi equivalents like `ம்ம்`, `ஆ`, `haan`). Tamil/English/mixed words each count as one word. Returns `None` under 50 total words.
- Level caps (the document's tables):
  - Listening: ≤65% and ≤1/5min → any; >65–75% or >1–3/5min → Good; >75% or >3/5min → Partial; >75% **and** >3/5min → Poor.
  - Courtesy: >3/5min → Good at most.
  - A `None` metric imposes no cap.
- Tips shown when a limit is crossed: talk share >65% → *"Let the customer speak more. Aim to talk less than 65% of the time."*; interruptions >1/5min → *"Let the customer finish before you reply."*; talk share <30% → *"Guide the conversation more: ask questions and explain the next step."*

### 4.4 `services/call_sorting.py` (new): Step 1
- **AI step A** (Gemini, temperature 0, JSON output): the transcript + sign definitions + never-count list. It returns `signs: [{sign: 1..6, speaker, quote, time}]`, plus the fields the early-exit check needs (`language_barrier: bool`, `not_enquired: bool`, `voicemail_ivr: bool`) with quotes.
- `validate_signs(signs, lines)`. A sign counts only if its quote is found in a transcript line (whitespace/punctuation-insensitive substring match, with a small edit-distance tolerance for spelling differences) **and** that line's speaker is allowed for the sign (1, 4, 5 → customer; 2 → telecaller; 3, 6 → either). One valid instance per sign number.
- `group_for(valid_sign_count)` → `real_conversation` if ≥ `MIN_SIGNS` (2), otherwise `early_exit`.
- **Early-exit check** (same AI call as step A, to avoid a second request): `polite` (bool + quote), `enquiry_confirmed_early` (bool: said in the first 30 s), `expected_crm` (one of `wrong_number | not_enquired | callback | language_barrier | voicemail | other`). The system compares `expected_crm` with the saved wrap-up once it exists (see 4.6).

### 4.5 `services/call_marking.py` (new): Step 2
- **AI step B** (Gemini, temperature 0, JSON output). Inputs: the transcript, knowledge-base context (`get_knowledge_context`), the lead's previous notes/summaries (for the follow-up rule on check 3), talk share, interruptions per 5 min, and the caps already in force. It returns, for checks 1–9: `level ∈ {excellent, good, partial, poor, missing}`, a one-line `reason`, a `quote`, and a `time`. Check 5 also returns `wrong_info: [{quote, time, kb_fact}]` and `unverified_claims: [quote]`. Check 2 also returns `rude: bool` with a quote, and `interruption_excused` with a reason (the document's "sorry to cut in" exception).
- **The AI never returns marks.** The system:
  1. Validates each quote as in 4.4. A level with no valid quote is kept but `proof_missing = true`, which raises a `no_proof` warning.
  2. Applies caps: `level = min(ai_level, cap)`, recording `capped_from` when lowered.
  3. Forces check 5 to `missing` when `wrong_info` is non-empty.
  4. Computes `marks = CHECK_MARKS[check] × LEVEL_SHARE[level]`, sums all 10 in full precision, and rounds to 1 decimal only at the end.
  5. Picks the top 2 to improve: lowest `marks / full_marks`, tie → the check with more rubric marks.
- `CHECK_MARKS = {opening:5, courtesy:10, questions:15, listening:10, product_info:15, doubts:10, clarity:10, next_step:10, decision:8, crm_update:7}`. `LEVEL_SHARE = {excellent:1, good:.75, partial:.5, poor:.25, missing:0}`.
- Golden test: the document's full example must total **78.5**.

### 4.6 Check 10 / CRM (`call_marking.py`)
- It runs when the wrap-up is saved (existing outcome route in `routes/calls.py`) or when the 2-hour sweep fires, whichever comes first.
- Real conversation: a small Gemini call (temperature 0) given the transcript summary, the 6 signs, and the saved wrap-up (outcome, manual status, do-not-call, callback date, notes). It returns level + reason. The status guide from the document is mapped onto existing outcomes: converted/interested = Hot or Warm, callback requires a future date, not_interested = Cold/Disqualified, do_not_call on a hard no. The "Warm vs Hot → Partial" case cannot occur (Q3).
- No wrap-up after `WRAPUP_CUTOFF_HOURS` (2) → `missing`, no AI call.
- Early exit: no AI. `expected_crm` is compared to the wrap-up by a fixed mapping (`wrong_number` ↔ manual_status `wrong_number`; `not_enquired` ↔ `not_interested`; `callback` ↔ `callback` + future date; `language_barrier` / `voicemail` → no matching status exists, so a note only, never a mismatch). A mismatch raises a `crm_mismatch` warning.
- Each re-run replaces check 10 and recomputes the total; the other 9 checks are never re-marked.

### 4.7 Warnings: `call_alerts` table + `services/call_alerts.py` (new)
Types in Phase 1: `rude` (instant), `wrong_info` (instant), `crm_mismatch`, `no_proof`, `transcript_failed`, `language_barrier`, `lead_source_quality`, `tracks_swapped`.
- `raise_alert(db, call, type, quote, detail)` inserts a row, deduped on `(call_log_id, type)`.
- Instant types send `notify_user` to the tenant owner/admins, **max 1 per telecaller per hour**; extras only land in the list.
- `lead_source_quality`: a daily job per tenant per `leads.source`. If ≥ 10 answered TeleCMI calls that day and ≥ 30% of them are wrong-number or not-enquired early exits, one alert is raised (no call_log_id).
- Morning summary: a scheduled job at **09:00 IST** sends one notification per tenant admin with counts by type for the previous day, linking to Needs attention. It is skipped when there are zero alerts.
- Telecaller-visible: `crm_mismatch` and `no_proof` show on the telecaller's own call card. No push.

### 4.8 Removed
- `SCORE_CRITERIA`, `DEFAULT_CRITERIA`, `AUDIO_CRITERIA`, `normalize_criteria`, `_selected_criteria`, the tone check and the audio attachment to analysis; `score_criteria` in app settings (route + `TelecallingConfigPanel.tsx` section).
- The no-answer safety gate: `raise_flag`, `_notify_flag`, `/calls/flagged`, the flag-resolve routes, the "flagged → outcome locked" rule, and `flag_status/flag_reason/flagged_at/flag_resolved_by/flag_resolved_at` columns. A no-answer-marked call with real content is now a real conversation, check 10 marks the wrong wrap-up, and `crm_mismatch` is raised.
- The old 7+3 points scorer (`compute_call_score` body, `AI_POINTS`, `ACCURACY_POINTS`, `CLOSING_POINTS`, `acceptable_outcomes`, `closing_move`).
- `FlaggedCalls.tsx` is replaced by `NeedsAttention.tsx`.

## 5. Data (migration `205_call_scoring_v4.sql`)

`call_logs`, new columns:
- `call_group text check in ('not_connected','very_short','early_exit','real_conversation')`
- `talk_share numeric(5,2)`, `interruptions_per_5min numeric(6,2)`, `interruption_count int`
- `score_final boolean default false` (false = provisional)
- `rules_version text` (`'v1'`)
- `score` stays `numeric`, now 0–100. `evaluation` jsonb holds `{evaluation_version: 4, signs, valid_sign_count, early_exit_check | checks[10], caps, top_improve, tips, unverified_claims}`. `score_status` values: `not_connected | very_short | processing | early_exit | provisional | scored | failed`.
- Drop the five `flag_*` columns.

`call_alerts` (new): `id uuid pk, tenant_id uuid not null, call_log_id uuid null references call_logs on delete cascade, caller_id uuid null, type text not null, quote text, detail jsonb, created_at timestamptz default now(), seen_at timestamptz, seen_by uuid`. Unique `(call_log_id, type)` where `call_log_id` is not null. Index `(tenant_id, seen_at, created_at desc)`. RLS enabled, tenant-scoped SELECT (same pattern as `call_logs`). Writes go through the backend service role only.

## 6. Screens

- **Call card** (`CallAi.tsx`, used in Recent calls, lead notes, QA feed): the score `/100` with a *provisional* tag; group label; the talk share + interruptions line with tips; top 2 to improve; the 10 checks grouped by stage (Connect / Understand / Explain / Close), each showing level, marks/full, and an expandable reason + `[mm:ss]` quote. A capped level shows "capped by talk share/interruptions". Unverified claims are shown as notes. Early exit shows its 3 small checks. Non-scored groups show only the "Not scored · …" label. The transcript view shows `[mm:ss]` per line.
- **Needs attention** (admin only, replaces Flagged calls on the Telecalling page): filters by type and telecaller, rows with telecaller / lead / type / quote / time, open call, **Mark as seen**. Sidebar badge = unseen count. Routes: `GET /calls/alerts?type&caller_id&seen`, `POST /calls/alerts/{id}/seen`, `GET /calls/alerts/count`.
- **Scale switch**: every screen showing call scores as `/10` switches to `/100` (`CallScorePill`, analytics CompareTab, ProfileClient, WinnerBanner, performance-view, operator analytics/team). `rank_winner` scales its volume term to 0–100 so quality and volume stay comparable until Phase 4 rebuilds it.
- UI follows the existing dashboard design language. Every changed screen is rendered and screenshotted before it's presented.

## 7. Settings (Phase 1 = constants, Phase 6 = admin-editable)

One module `services/scoring_rules.py` holds: `MIN_SCORED_SECONDS=30`, `MIN_SIGNS=2`, `WRAPUP_CUTOFF_HOURS=2`, `TALK_SHARE_MIN_WORDS=50`, talk-share bands (30/65/75), interruption bands (1/3), `OVERLAP_MIN_S=1.0`, `TELECALLER_RUN_MIN_S=1.0`, `CHECK_MARKS`, `LEVEL_SHARE`, `TELECALLER_CHANNEL=1`, `RULES_VERSION='v1'`, `LEAD_SOURCE_MIN_CALLS=10`, `LEAD_SOURCE_BAD_RATE=0.30`, `ALERT_RATE_LIMIT_PER_HOUR=1`, `MORNING_SUMMARY_IST="09:00"`.

## 8. Testing

- **Unit (no network)**: stereo split; speech segments on synthetic tones + noise floor; interruption counting (overlap < 1 s, backchannel < 1 s, customer-interrupts-telecaller → not counted); talk share with fillers and < 50 words; transcript merge + time snapping; quote validation (fabricated quote, wrong speaker); sign counting → group; caps table (all 4 rows + courtesy); marks maths; document example = **78.5**; top-2 tie rule; check 10 cut-off; alert dedupe + hourly cap; lead-source threshold.
- **Real AI**: the document's example transcripts (early exit ~2 min, real conversation ~95 s) plus test call `ed296fa2…` (expected: early exit, 0–1 signs). Each run twice to confirm identical output at temperature 0.
- **Before enabling for clients**: re-run the pipeline on 2–3 real TeleCMI sales calls and check the channel mapping, the noise floor and the marks by hand.
- `python -m pytest` from `backend/`; frontend `npm run lint` **and** `npm run typecheck`.

## 9. Risks

- **Channel mapping is confirmed on one conversational call.** A sanity check logs a warning when the "telecaller" track has zero speech while the other track has speech.
- **Two transcriptions per call** roughly doubles transcription cost. Calls under 30 s are no longer transcribed at all, which offsets part of it.
- **Quote matching on Tamil script**: the AI may normalise spelling differently from the transcript. Matching is whitespace/punctuation-insensitive with a small edit-distance tolerance per quote. If false rejections show up in the real-call test, the tolerance is tuned there.
