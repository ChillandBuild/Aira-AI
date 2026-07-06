-- Migration 135: Add start_date and end_date to subscription_requests for custom date ranges (new comers)
alter table subscription_requests
add column if not exists start_date date,
add column if not exists end_date date;
