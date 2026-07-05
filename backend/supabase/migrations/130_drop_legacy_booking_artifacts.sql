-- Remove legacy booking-flow artifacts after the booking state machine and
-- [COLLECT_DONE] data collection path were retired.

alter table if exists lead_conversation_state
  drop column if exists booking_id,
  drop column if exists flow_name;

alter table if exists leads
  drop column if exists collected_data;

delete from app_settings
where key in (
  'booking_event_name',
  'booking_ref_prefix',
  'booking_amount_paise',
  'booking_types'
);

drop table if exists bookings cascade;
