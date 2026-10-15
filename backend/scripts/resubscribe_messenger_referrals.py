"""One-off: add `messaging_referrals` to every connected Facebook Page's webhook fields.

Messenger sends "this existing chat came back through an ad" as a separate
`messaging_referrals` event, which a Page only delivers when subscribed to it.
New connections get it from app_settings.py; Pages connected before 2026-10-16
need this once. Also re-registers the app-level `page` object (same field list).

    cd backend && python -m scripts.resubscribe_messenger_referrals          # dry run
    cd backend && python -m scripts.resubscribe_messenger_referrals --apply  # do it

Safe to re-run: Meta's subscribed_apps call replaces the field list idempotently.
"""
import argparse
import asyncio

import httpx

from app.db.supabase import get_supabase
from app.services.meta_app_webhooks import WEBHOOK_OBJECTS, ensure_app_webhook_subscription

GRAPH = "https://graph.facebook.com/v21.0"
FIELDS = WEBHOOK_OBJECTS["facebook"][2]


def _connected_pages(db) -> list[tuple[str, str, str]]:
    rows = (
        db.table("app_settings").select("tenant_id,key,value")
        .in_("key", ["facebook_page_id", "facebook_access_token"])
        .execute().data
    ) or []
    by_tenant: dict[str, dict] = {}
    for r in rows:
        if r.get("value"):
            by_tenant.setdefault(r["tenant_id"], {})[r["key"]] = r["value"]
    return [
        (tenant, kv["facebook_page_id"], kv["facebook_access_token"])
        for tenant, kv in sorted(by_tenant.items())
        if kv.get("facebook_page_id") and kv.get("facebook_access_token")
    ]


async def main(apply: bool) -> None:
    assert "messaging_referrals" in FIELDS, FIELDS
    pages = _connected_pages(get_supabase())
    print(f"{len(pages)} connected Page(s); fields = {FIELDS}")
    if not apply:
        for tenant, page_id, _ in pages:
            print(f"  would update tenant={tenant} page={page_id}")
        print("Dry run. Re-run with --apply to change the subscriptions.")
        return

    print("app-level page object:", await ensure_app_webhook_subscription("facebook"))
    async with httpx.AsyncClient(timeout=15.0) as client:
        for tenant, page_id, token in pages:
            r = await client.post(
                f"{GRAPH}/{page_id}/subscribed_apps",
                params={"subscribed_fields": FIELDS, "access_token": token},
            )
            body = r.json()
            status = "ok" if body.get("success") else f"FAILED: {(body.get('error') or {}).get('message')}"
            print(f"  tenant={tenant} page={page_id}: {status}")


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--apply", action="store_true")
    asyncio.run(main(parser.parse_args().apply))
