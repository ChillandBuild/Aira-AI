import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from app.services.meta_ads_payloads import (
    build_campaign_payload, build_adset_payload, build_targeting,
    build_creative_payload, build_ad_payload, WA_LINK,
)


def test_campaign_payload_cbo_daily_budget_in_paise():
    p = build_campaign_payload("Diwali", daily_budget_inr=500)
    assert p["objective"] == "OUTCOME_ENGAGEMENT"
    assert p["special_ad_categories"] == []
    assert p["daily_budget"] == 50000          # 500 * 100
    assert p["bid_strategy"] == "LOWEST_COST_WITHOUT_CAP"
    assert "lifetime_budget" not in p


def test_campaign_payload_lifetime_and_special_category():
    p = build_campaign_payload("Jobs", lifetime_budget_inr=1500, special_ad_category="EMPLOYMENT")
    assert p["lifetime_budget"] == 150000
    assert p["special_ad_categories"] == ["EMPLOYMENT"]
    assert "daily_budget" not in p


def test_targeting_maps_gender_and_geo():
    t = build_targeting(["IN"], 18, 65, "female")
    assert t["geo_locations"] == {"countries": ["IN"]}
    assert t["age_min"] == 18 and t["age_max"] == 65
    assert t["genders"] == [2]
    all_t = build_targeting(["IN"], 18, 65, "all")
    assert "genders" not in all_t


def test_adset_payload_is_whatsapp_conversations_no_budget():
    t = build_targeting(["IN"], 18, 65, "all")
    p = build_adset_payload("Set 1", "c123", "page99", t)
    assert p["destination_type"] == "WHATSAPP"
    assert p["optimization_goal"] == "CONVERSATIONS"
    assert p["billing_event"] == "IMPRESSIONS"
    assert p["promoted_object"] == {"page_id": "page99"}
    assert p["campaign_id"] == "c123"
    assert "daily_budget" not in p and "lifetime_budget" not in p


def test_creative_payload_ctwa_shape():
    p = build_creative_payload("Cr1", "page99", "Come visit!", "Diwali Sale", "HASH1", "Hi, interested!")
    link = p["object_story_spec"]["link_data"]
    assert p["object_story_spec"]["page_id"] == "page99"
    assert link["link"] == WA_LINK
    assert link["message"] == "Come visit!"
    assert link["name"] == "Diwali Sale"
    assert link["image_hash"] == "HASH1"
    assert link["call_to_action"]["type"] == "WHATSAPP_MESSAGE"
    assert link["call_to_action"]["value"]["app_destination"] == "WHATSAPP"
    autofill = link["page_welcome_message"]["text_format"]["message"]["autofill_message"]["content"]
    assert autofill == "Hi, interested!"


def test_ad_payload_links_creative():
    p = build_ad_payload("Ad1", "as123", "cr456")
    assert p["adset_id"] == "as123"
    assert p["creative"] == {"creative_id": "cr456"}
