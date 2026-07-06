from app.routes.calls import _call_queue_sort_key, _is_message_priority_lead


def test_message_priority_detects_channel_and_replied_upload_leads():
    assert _is_message_priority_lead({"id": "wa", "source": "whatsapp"}) is True
    assert _is_message_priority_lead({"id": "upload", "source": "upload"}, {"upload": "2026-07-05T10:00:00Z"}) is True
    assert _is_message_priority_lead({"id": "upload", "source": "upload"}, {}) is False


def test_call_queue_sort_puts_message_leads_before_upload_leads():
    leads = [
        {"id": "upload-hot", "source": "upload", "segment": "A", "score": 10, "created_at": "2026-07-05T08:00:00Z"},
        {"id": "message-warm", "source": "instagram", "segment": "B", "score": 6, "created_at": "2026-07-05T08:00:00Z"},
        {"id": "reply-hot", "source": "upload", "segment": "A", "score": 9, "created_at": "2026-07-05T08:00:00Z"},
        {"id": "upload-cold", "source": "upload", "segment": "C", "score": 5, "created_at": "2026-07-05T08:00:00Z"},
    ]
    last_inbound = {"reply-hot": "2026-07-05T10:00:00Z"}

    sorted_leads = sorted(leads, key=lambda lead: _call_queue_sort_key(lead, {}, last_inbound))

    assert [lead["id"] for lead in sorted_leads] == ["reply-hot", "message-warm", "upload-hot", "upload-cold"]
