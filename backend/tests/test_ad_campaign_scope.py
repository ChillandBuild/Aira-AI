"""Meta Ads / Segments scoping: campaigns of the connected ad account only, placeholder
rows folded into their real campaign, and each ad's last day of delivery."""
from app.services import ad_performance
from tests.fake_supabase import FakeSupabase

CURRENT = "act_905982549234446"
OLD = "act_4306295769588787"


def _db():
    db = FakeSupabase()
    db.add("app_settings", tenant_id="t1", key="meta_ads_account_id", value=CURRENT)
    # Real campaigns from the Meta sync, two of them sharing a name.
    db.add("ad_campaigns", id="c-wb-aug", tenant_id="t1", campaign_name="Astro Whatsapp-WB", platform="whatsapp",
           external_campaign_id="120254794740460747", meta_ad_account_id=CURRENT)
    db.add("ad_campaigns", id="c-wb-sep", tenant_id="t1", campaign_name="Astro Whatsapp-WB", platform="whatsapp",
           external_campaign_id="120254601940740747", meta_ad_account_id=CURRENT)
    db.add("ad_campaigns", id="c-old", tenant_id="t1", campaign_name="Astro insta and Fb-WB", platform="whatsapp",
           external_campaign_id="120253294587980066", meta_ad_account_id=OLD)
    # Placeholder the webhook made before the ad synced: named after the ad's headline, keyed by the AD id.
    db.add("ad_campaigns", id="p-chat", tenant_id="t1", campaign_name="Chat with us", platform="whatsapp",
           external_campaign_id="120254794740480747", meta_ad_account_id=None)
    db.add("ad_creatives", id="ad-1", tenant_id="t1", campaign_id="c-wb-aug", meta_ad_id="120254794740480747",
           meta_ad_account_id=CURRENT)
    # Another tenant's row with the same ad id must never be pulled in.
    db.add("ad_campaigns", id="other-tenant", tenant_id="t2", campaign_name="Chat with us",
           external_campaign_id="120254794740480747", meta_ad_account_id=None)
    return db


def test_campaign_list_is_only_the_connected_accounts_real_campaigns():
    ids = [c["id"] for c in ad_performance.current_account_campaigns(_db(), "t1")]
    assert sorted(ids) == ["c-wb-aug", "c-wb-sep"]


def test_campaign_list_is_empty_without_a_connected_account():
    db = _db()
    db.tables["app_settings"] = []
    assert ad_performance.current_account_campaigns(db, "t1") == []


def test_picking_a_campaign_also_covers_its_placeholder_rows():
    assert ad_performance.campaign_ids_with_placeholders(_db(), "t1", "c-wb-aug") == ["c-wb-aug", "p-chat"]


def test_a_campaign_without_placeholders_is_just_itself():
    assert ad_performance.campaign_ids_with_placeholders(_db(), "t1", "c-wb-sep") == ["c-wb-sep"]


def test_segments_campaign_filter_includes_leads_filed_under_its_placeholder():
    from app.routes.leads import LeadFilters, _filtered_leads_query

    db = _db()
    db.add("leads", id="L-real", tenant_id="t1", source="whatsapp", ad_campaign_id="c-wb-aug")
    db.add("leads", id="L-placeholder", tenant_id="t1", source="whatsapp", ad_campaign_id="p-chat")
    db.add("leads", id="L-other", tenant_id="t1", source="whatsapp", ad_campaign_id="c-wb-sep")
    f = LeadFilters(source_filter="meta_ads", ad_campaign_id="c-wb-aug")
    rows = _filtered_leads_query(db, {"tenant_id": "t1"}, f).execute().data
    assert sorted(r["id"] for r in rows) == ["L-placeholder", "L-real"]


def test_campaigns_route_scopes_to_current_account_only_when_asked():
    import asyncio
    from unittest.mock import patch
    from app.routes import inbound_leads

    db = _db()
    with patch.object(inbound_leads, "get_supabase", return_value=db):
        scoped = asyncio.run(inbound_leads.list_campaigns(current_account=True, tenant_id="t1"))["data"]
        everything = asyncio.run(inbound_leads.list_campaigns(current_account=False, tenant_id="t1"))["data"]
    assert sorted(c["id"] for c in scoped) == ["c-wb-aug", "c-wb-sep"]
    assert sorted(c["id"] for c in everything) == ["c-old", "c-wb-aug", "c-wb-sep", "p-chat"]


def test_last_delivery_is_the_latest_day_with_impressions():
    db = _db()
    for day, impressions in [("2026-08-20", 300), ("2026-08-25", 40), ("2026-09-02", 0)]:
        db.add("ad_insights_daily", tenant_id="t1", meta_ad_account_id=CURRENT, ad_creative_id="ad-1",
               insight_date=day, impressions=impressions)
    db.add("ad_insights_daily", tenant_id="t1", meta_ad_account_id=CURRENT, ad_creative_id="ad-2",
           insight_date="2026-10-01", impressions=0)
    got = ad_performance.last_delivery_dates(db, "t1", CURRENT, ["ad-1", "ad-2"])
    assert got == {"ad-1": "2026-08-25"}


def test_campaign_sync_saves_metas_creation_date(monkeypatch):
    from app.services import meta_ads_insights_sync as sync

    db = _db()
    monkeypatch.setattr(sync, "_fetch_campaigns", lambda *a, **k: [
        {"id": "120254794740460747", "name": "Astro Whatsapp-WB", "effective_status": "ACTIVE",
         "created_time": "2026-08-14T10:30:00+0530"},
    ])
    sync.sync_campaign_meta(db, "t1", "token", CURRENT)
    row = next(c for c in db.tables["ad_campaigns"] if c["id"] == "c-wb-aug")
    assert row["meta_created_at"] == "2026-08-14T10:30:00+0530"
    listed = next(c for c in ad_performance.current_account_campaigns(db, "t1") if c["id"] == "c-wb-aug")
    assert listed["meta_created_at"] == "2026-08-14T10:30:00+0530"


def test_meta_ads_rows_carry_the_campaigns_meta_creation_date():
    db = _db()
    db.tables["ad_campaigns"][0]["meta_created_at"] = "2026-08-14T05:00:00+00:00"
    db.tables["ad_creatives"][0].update(is_click_to_whatsapp=True, creative_label="Astro Whatsapp-WB",
                                        ad_effective_status="PAUSED")
    rows = ad_performance.build_creative_performance(db, "t1")
    assert [r["campaign_created_at"] for r in rows] == ["2026-08-14T05:00:00+00:00"]


def test_campaign_sync_saves_the_creation_date_even_for_campaigns_with_no_recent_delivery(monkeypatch):
    # Astro Tamil: no ad shown in the last 30 days, so the sync sees no WhatsApp rows.
    from app.services import meta_ads_insights_sync as sync

    db = _db()
    db.tables["ad_campaigns"][0]["effective_status"] = "PAUSED"
    monkeypatch.setattr(sync, "_fetch_campaigns", lambda *a, **k: [
        {"id": "120254794740460747", "effective_status": "ACTIVE", "objective": "OUTCOME_ENGAGEMENT",
         "created_time": "2026-08-14T10:30:00+0530"},
    ])
    sync.sync_campaign_meta(db, "t1", "token", CURRENT, campaign_ids=set())
    row = next(c for c in db.tables["ad_campaigns"] if c["id"] == "c-wb-aug")
    assert row["meta_created_at"] == "2026-08-14T10:30:00+0530"
    # Everything else stays limited to campaigns with WhatsApp delivery, as before.
    assert row["effective_status"] == "PAUSED"
    assert "objective" not in row
