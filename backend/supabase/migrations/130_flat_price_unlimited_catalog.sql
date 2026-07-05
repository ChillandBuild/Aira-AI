-- Migration 130: flat-price modules + unlimited quota phase
--
-- Channel/telecalling modules are monthly flat-price entitlements, not usage
-- caps. Quantity/AI counters remain useful for usage visibility, but no
-- catalog row should imply a hard cap while pricing is still being finalized.

update feature_catalog
set
    usage_metric = null,
    unit_price = null,
    included_qty = null,
    is_metered = false
where feature_key in (
    'inbound_messaging',
    'outbound_messaging',
    'telecalling_telecmi',
    'telecalling_sim',
    'ai_tier.basic',
    'ai_tier.standard',
    'ai_tier.premium'
);

update feature_catalog
set
    included_qty = null,
    is_metered = false
where feature_key in ('telecaller_seats', 'numbers_pool');

update tenant_usage_counters
set hard_cap = null
where metric in (
    'message_sent',
    'ai_reply',
    'call_minute',
    'team_seat_active',
    'phone_number'
);
