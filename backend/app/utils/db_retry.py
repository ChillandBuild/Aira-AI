"""Shared retry helper for transient Supabase/Postgrest connection drops.

httpx.RemoteProtocolError ("Server disconnected") and similar HTTP/2 hiccups
happen intermittently against Supabase and are worth a single retry rather
than a 500. See dependencies/auth.py's _verify_remote for the auth-critical
variant (retries then raises 503) and chat_handovers.py's handover_count for
the catch-and-fallback variant used by non-critical polling endpoints.
"""


def is_transient_db_error(e: Exception) -> bool:
    """True for transient Supabase/Postgrest connection drops worth retrying once."""
    blob = f"{type(e).__name__}: {e}".lower()
    return any(
        s in blob
        for s in ("server disconnected", "connectionterminated", "connection reset", "goaway")
    )


def execute_with_retry(query):
    """Execute a Supabase query, retrying once on a transient connection drop."""
    try:
        return query.execute()
    except Exception as e:
        if is_transient_db_error(e):
            return query.execute()
        raise
