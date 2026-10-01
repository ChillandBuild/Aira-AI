SET LOCAL lock_timeout = '5s';
ALTER TABLE public.messages ADD COLUMN IF NOT EXISTS interactive_id text;
