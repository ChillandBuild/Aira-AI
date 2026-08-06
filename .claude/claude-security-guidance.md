# Aira AI security rules

- Every new/changed table or route touching leads, calls, or messages must have RLS enabled
  AND be checked against `get_tenant_and_role()` in the app layer — RLS alone is not sufficient,
  isolation is enforced at both layers.
- WhatsApp inbound webhook must verify `X-Hub-Signature-256` before processing. On an invalid
  signature it must still return HTTP 200 and silently drop the payload — do NOT "fix" this to
  return 401/403, Meta retries non-200 responses aggressively.
- New Postgres `SECURITY DEFINER` functions must explicitly `REVOKE EXECUTE ... FROM anon`.
- Never add a platform-level fallback API key for AI reply models, WhatsApp, or Voice providers.
  Every provider key must resolve per-tenant (`ai_reply_model` etc.) — a shared fallback key is
  a tenant-isolation break, not a config convenience.
- Call recordings must upload to Supabase Storage only. Never write recordings to local disk
  (including temp dirs) even transiently.
- The bulk broadcast send endpoint must reject any lead with a null `opt_in_source` before
  sending — this is a compliance gate, not just validation.
- Razorpay payment status must only be confirmed via signature-verified webhook callback.
  Never trust a client-reported or query-param payment status to mark a payment link paid.
