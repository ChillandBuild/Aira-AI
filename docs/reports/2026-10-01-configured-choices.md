# Configured WhatsApp choices — verification, 1 October 2026

Implemented locally; backend not deployed. Migration 214 (`messages.interactive_id`) was applied to the Aira Supabase project and verified nullable text, with messages RLS enabled.

## Changes

- Configured package choices use saved package IDs and button labels, including fallback resolution of the screenshot's AI-generated names with prices.
- Configured detail choices use a field key and session-bound canonical values. Male/Female taps save through the guarded executor before the reply model runs.
- Stale sessions, removed options, paid bookings and a booking changed during capture cannot receive those tap values. Bound detail taps are excluded from later extraction and model history. Historical messages without stored IDs cannot be retrospectively classified.
- Explicit field references support corrections to already answered details; natural text extraction remains available for multiple details supplied together.
- The choice tool's message stays paired with its options, retrying a reply drops obsolete choices, mismatched package/detail menus are refused, and missing package names/prices are supplied from configuration.
- Long replies send their full text before the menu. Oversized detail IDs preserve full options as text. Transcript recording distinguishes interactive delivery from text fallback.
- Existing missing booking-tool constant and price-change helper were restored so the booking/payment code could import and run its checks.

## Verification

258 focused tests passed across configured choices, choice parsing, deal actions, reply turns, written tool calls and WhatsApp menu delivery. The focused tests include the screenshot, Tanglish questions, canonical gender saving, field corrections, out-of-order fields, malformed/stale/paid taps, a booking-change race, menus exceeding button limits and long Unicode options.

Full backend suite: 3,205 passed, 39 failed, 7 warnings. Every remaining failure below also reproduced in an isolated HEAD baseline, with only the prerequisite deal_engine import/price-change restores copied in to allow the tests to run. The baseline export omitted frontend files; the three frontend-file failures it produced were excluded from the comparison.

The remaining failures are in existing booking return/lifecycle APIs and prompt contracts. The full suite is not green, and those failures limit any claim about resumed bookings. No live WhatsApp message or paid model evaluation was sent; live model choice behavior has not been verified. Database migration applied; application code remains local.

## Existing failures

- `tests/test_deal_engine_prompt.py::TestTools::test_tool_names_are_the_contract`
- `tests/test_deal_engine_prompt.py::TestLinkLiveness::test_expired_link_is_not_reported_as_sent`
- `tests/test_deal_engine_prompt.py::TestLinkLiveness::test_link_without_an_expiry_is_not_reported_as_sent`
- `tests/test_deal_engine_prompt.py::TestLinkLiveness::test_link_at_a_stale_price_is_not_reported_as_sent`
- `tests/test_deal_return_prompt.py::TestAwayLine::test_days_away`
- `tests/test_deal_return_prompt.py::TestAwayLine::test_hours_away`
- `tests/test_deal_return_prompt.py::TestAwayLine::test_a_minute_ago_reads_as_just_now`
- `tests/test_deal_return_prompt.py::TestAwayLine::test_accepts_a_supabase_timestamp_string`
- `tests/test_deal_return_prompt.py::TestAwayLine::test_no_away_line_without_a_last_seen_value`
- `tests/test_deal_return_prompt.py::TestLinkExpiryLine::test_a_live_link_shows_its_expiry_in_indian_time`
- `tests/test_deal_return_prompt.py::TestLinkExpiryLine::test_an_expired_link_is_reported_and_a_new_one_promised`
- `tests/test_deal_return_prompt.py::TestLinkExpiryLine::test_a_stored_link_past_its_expiry_says_when_it_expired`
- `tests/test_deal_return_prompt.py::TestLinkExpiryLine::test_no_link_yet_is_not_called_expired`
- `tests/test_deal_return_prompt.py::TestReturningInstruction::test_appears_after_a_day_away_with_an_open_deal`
- `tests/test_deal_return_prompt.py::TestReturningInstruction::test_the_model_judges_intent_and_asks_when_unsure`
- `tests/test_deal_return_prompt.py::TestReturningInstruction::test_not_shown_under_24_hours`
- `tests/test_deal_return_prompt.py::TestReturningInstruction::test_shown_at_exactly_24_hours`
- `tests/test_deal_return_prompt.py::TestReturningInstruction::test_not_shown_without_an_open_deal`
- `tests/test_deal_return_prompt.py::TestReturningInstruction::test_not_shown_for_a_paid_deal`
- `tests/test_deal_return_prompt.py::TestReturningInstruction::test_not_shown_when_the_away_time_is_unknown`
- `tests/test_deal_return_prompt.py::TestReturningInstruction::test_a_bare_greeting_alone_no_longer_triggers_it`
- `tests/test_deal_return_prompt.py::TestCloseDealTool::test_is_a_deal_tool`
- `tests/test_deal_return_prompt.py::TestCloseDealTool::test_description_demands_an_explicit_decline_and_names_the_non_declines`
- `tests/test_deal_return_prompt.py::TestNewBookingAndPreviousDetails::test_select_offering_can_flag_a_separate_booking`
- `tests/test_deal_return_prompt.py::TestNewBookingAndPreviousDetails::test_previous_details_are_shown_for_confirmation_never_for_silent_reuse`
- `tests/test_deal_return_prompt.py::TestNewBookingAndPreviousDetails::test_no_previous_details_no_block`
- `tests/test_deal_return_prompt.py::TestNewBookingAndPreviousDetails::test_the_prompt_carries_the_previous_details_block`
- `tests/test_deal_return_wiring.py::test_a_lead_back_after_days_with_an_open_deal_gets_the_return_instruction`
- `tests/test_deal_return_wiring.py::test_the_instruction_is_language_free_so_tamil_and_tanglish_reach_it_too`
- `tests/test_deal_return_wiring.py::test_a_bare_greeting_within_a_day_no_longer_triggers_it`
- `tests/test_deal_return_wiring.py::test_no_open_deal_no_return_instruction`
- `tests/test_deal_return_wiring.py::test_an_unknown_idle_clock_asks_nothing`
- `tests/test_deal_return_wiring.py::test_earlier_booking_details_are_offered_for_confirmation_when_no_deal_is_open`
- `tests/test_deal_return_wiring.py::test_no_previous_booking_block_while_a_deal_is_open`
- `tests/test_deal_return_wiring.py::test_a_message_restarts_the_clock_even_when_the_ai_will_not_reply`
- `tests/test_engine_sim_lifecycle.py::test_away_time_reaches_deal_state_and_the_return_instruction`
- `tests/test_engine_sim_lifecycle.py::test_a_per_turn_away_overrides_and_the_message_restarts_the_clock`
- `tests/test_engine_sim_lifecycle.py::test_an_expired_seeded_link_is_reported_in_deal_state`
- `tests/test_engine_sim_lifecycle.py::test_a_previous_booking_is_seeded_and_offered_back`
