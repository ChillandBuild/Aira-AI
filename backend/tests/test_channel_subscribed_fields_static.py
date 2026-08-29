import sys
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

# Meta rejects the whole subscribed_apps call with (#100) if any single field is
# not in the object's vocabulary. These are Messenger-only.
MESSENGER_ONLY_FIELDS = ("message_deliveries", "message_reads")


def _read(path: str) -> str:
    return (ROOT / path).read_text(encoding="utf-8")


def _activate_channel_body(source: str) -> str:
    start = source.index("async def activate_channel")
    end = source.index("@router.post", start)
    return source[start:end]


def test_activate_channel_sends_instagram_its_own_fields():
    body = _activate_channel_body(_read("app/routes/app_settings.py"))
    assert '"messages,messaging_postbacks,messaging_seen"' in body
    assert 'if channel == "instagram"' in body


def test_instagram_branch_omits_messenger_only_fields():
    body = _activate_channel_body(_read("app/routes/app_settings.py"))
    start = body.index("sub_fields = (")
    instagram_branch = body[start:body.index("else", start)]
    for field in MESSENGER_ONLY_FIELDS:
        assert field not in instagram_branch


def test_facebook_still_gets_the_messenger_field_list():
    body = _activate_channel_body(_read("app/routes/app_settings.py"))
    assert '"messages,messaging_postbacks,message_deliveries,message_reads"' in body
