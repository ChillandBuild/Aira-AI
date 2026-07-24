"""Pure Meta Marketing API payload builders for Click-to-WhatsApp ad creation.
No I/O — every function returns a dict ready to POST. Money arrives in INR
rupees and is converted to Meta's minor units (paise) here."""

WA_LINK = "https://api.whatsapp.com/send"
_GENDER_MAP = {"male": [1], "female": [2]}  # "all" → omit the key entirely


def build_campaign_payload(name, *, daily_budget_inr=None, lifetime_budget_inr=None,
                           special_ad_category=None) -> dict:
    """Campaign-level CBO: budget + bid strategy live here, not on the ad set."""
    p = {
        "name": name,
        "objective": "OUTCOME_ENGAGEMENT",
        "special_ad_categories": [special_ad_category] if special_ad_category else [],
        "bid_strategy": "LOWEST_COST_WITHOUT_CAP",
        "status": "ACTIVE",
    }
    if daily_budget_inr:
        p["daily_budget"] = int(round(daily_budget_inr * 100))
    if lifetime_budget_inr:
        p["lifetime_budget"] = int(round(lifetime_budget_inr * 100))
    return p


def build_targeting(location_countries, age_min, age_max, gender) -> dict:
    t = {
        "geo_locations": {"countries": list(location_countries)},
        "age_min": int(age_min),
        "age_max": int(age_max),
    }
    g = _GENDER_MAP.get((gender or "all").lower())
    if g:
        t["genders"] = g
    return t


def build_adset_payload(name, campaign_id, page_id, targeting) -> dict:
    return {
        "name": name,
        "campaign_id": campaign_id,
        "destination_type": "WHATSAPP",
        "billing_event": "IMPRESSIONS",
        "optimization_goal": "CONVERSATIONS",
        "promoted_object": {"page_id": page_id},
        "targeting": targeting,
        "status": "ACTIVE",
    }


def build_creative_payload(name, page_id, message, headline, image_hash, greeting) -> dict:
    return {
        "name": name,
        "object_story_spec": {
            "page_id": page_id,
            "link_data": {
                "name": headline,
                "message": message,
                "image_hash": image_hash,
                "link": WA_LINK,
                "call_to_action": {
                    "type": "WHATSAPP_MESSAGE",
                    "value": {"app_destination": "WHATSAPP"},
                },
                "page_welcome_message": {
                    "type": "VISUAL_EDITOR",
                    "version": 2,
                    "landing_screen_type": "welcome_message",
                    "media_type": "text",
                    "text_format": {
                        "customer_action_type": "autofill_message",
                        "message": {
                            "text": greeting,
                            "autofill_message": {"content": greeting},
                        },
                    },
                },
            },
        },
    }


def build_ad_payload(name, adset_id, creative_id) -> dict:
    return {
        "name": name,
        "adset_id": adset_id,
        "creative": {"creative_id": creative_id},
        "status": "ACTIVE",
    }
