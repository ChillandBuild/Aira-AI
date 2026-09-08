"""Adding a second number through Embedded Signup must not take the primary slot.

The client picked their sending number. Onboarding another one onto the same WABA
days later is an "add", not a "switch" -- so the incumbent keeps sending until the
client promotes the new number from the Numbers page themselves.
"""
from unittest.mock import AsyncMock, MagicMock, patch

import pytest


class _FakeTable:
    def __init__(self, store, name):
        self._store = store
        self._name = name
        self._op = None
        self._fields = None
        self._filters = {}

    # -- query builders -------------------------------------------------
    def select(self, *_a, **_k):
        self._op = "select"
        return self

    def update(self, fields):
        self._op = "update"
        self._fields = fields
        return self

    def upsert(self, fields, **_k):
        self._op = "upsert"
        self._fields = fields
        return self

    def insert(self, fields):
        self._op = "insert"
        self._fields = fields
        return self

    def delete(self):
        self._op = "delete"
        return self

    def eq(self, key, value):
        self._filters[key] = value
        return self

    def neq(self, key, value):
        self._filters["!" + key] = value
        return self

    def in_(self, *_a, **_k):
        return self

    def order(self, *_a, **_k):
        return self

    # -- execution ------------------------------------------------------
    def execute(self):
        rows = self._store.setdefault(self._name, [])
        if self._op == "select":
            return MagicMock(data=[r for r in rows if self._matches(r)])
        if self._op == "update":
            for r in rows:
                if self._matches(r):
                    r.update(self._fields)
            return MagicMock(data=[])
        if self._op in ("upsert", "insert"):
            rows.append(dict(self._fields, id="row-%d" % (len(rows) + 1)))
            return MagicMock(data=[rows[-1]])
        return MagicMock(data=[])

    def _matches(self, row):
        for key, value in self._filters.items():
            if key.startswith("!"):
                if row.get(key[1:]) == value:
                    return False
            elif row.get(key) != value:
                return False
        return True


class _FakeDB:
    def __init__(self, phone_numbers=None):
        self.store = {"phone_numbers": list(phone_numbers or []), "app_settings": []}

    def table(self, name):
        return _FakeTable(self.store, name)

    def settings_written(self):
        return {r["key"]: r["value"] for r in self.store["app_settings"] if "key" in r}


def _call(db, *, number, phone_id, claim_primary):
    from app.routes.app_settings import _upsert_onboarded_phone_number

    return _upsert_onboarded_phone_number(
        db,
        "tenant-1",
        number=number,
        display_name="Bloom Matrix",
        meta_phone_number_id=phone_id,
        claim_primary=claim_primary,
    )


def test_first_number_takes_primary_so_the_pool_is_not_dead():
    # compute_unlocked_ids() unlocks nothing until a primary exists, so a
    # tenant's very first number must still be promoted.
    db = _FakeDB()
    assert _call(db, number="+919999999999", phone_id="phone-1", claim_primary=False) is True
    row = db.store["phone_numbers"][0]
    assert row["role"] == "primary"
    assert row["status"] == "active"


def test_second_number_lands_standby_and_leaves_the_incumbent_alone():
    db = _FakeDB([
        {"id": "old", "number": "+919999999999", "role": "primary",
         "status": "active", "meta_phone_number_id": "phone-1", "tenant_id": "tenant-1"},
    ])
    assert _call(db, number="+918888888888", phone_id="phone-2", claim_primary=False) is False

    old = next(r for r in db.store["phone_numbers"] if r["id"] == "old")
    new = next(r for r in db.store["phone_numbers"] if r.get("meta_phone_number_id") == "phone-2")
    assert old["role"] == "primary", "incumbent must keep the slot"
    assert new["role"] == "standby"
    assert new["status"] == "warming"
    assert new["warm_up_day"] == 0


def test_reconnecting_the_incumbent_does_not_demote_it():
    db = _FakeDB([
        {"id": "old", "number": "+919999999999", "role": "primary",
         "status": "active", "meta_phone_number_id": "phone-1", "tenant_id": "tenant-1"},
    ])
    assert _call(db, number="+919999999999", phone_id="phone-1", claim_primary=False) is True
    assert db.store["phone_numbers"][0]["role"] == "primary"
    assert len(db.store["phone_numbers"]) == 1, "reconnect must update, not duplicate"


def test_a_synced_row_is_matched_on_the_normalized_number_not_duplicated():
    # sync-from-meta stores the number stripped of spacing; signup does not.
    db = _FakeDB([
        {"id": "synced", "number": "+918888888888", "role": "standby",
         "status": "warming", "meta_phone_number_id": None, "tenant_id": "tenant-1"},
        {"id": "old", "number": "+919999999999", "role": "primary",
         "status": "active", "meta_phone_number_id": "phone-1", "tenant_id": "tenant-1"},
    ])
    assert _call(db, number="+91 88888 88888", phone_id="phone-2", claim_primary=False) is False
    assert len(db.store["phone_numbers"]) == 2, "should update the synced row in place"
    assert db.store["phone_numbers"][0]["meta_phone_number_id"] == "phone-2"


def test_hand_pasted_token_still_claims_the_slot():
    # The manual path names one number explicitly and repoints
    # meta_phone_number_id at it, so it does demote the incumbent.
    db = _FakeDB([
        {"id": "old", "number": "+919999999999", "role": "primary",
         "status": "active", "meta_phone_number_id": "phone-1", "tenant_id": "tenant-1"},
    ])
    assert _call(db, number="+918888888888", phone_id="phone-2", claim_primary=True) is True
    old = next(r for r in db.store["phone_numbers"] if r["id"] == "old")
    assert old["role"] == "standby"


@pytest.mark.asyncio
async def test_embedded_signup_keeps_the_sender_on_the_incumbent():
    """The end-to-end guard: adding a number must not repoint the tenant-level
    meta_phone_number_id, or outbound splits between the two numbers."""
    from app.routes.app_settings import EmbeddedSignupRequest, whatsapp_embedded_signup

    db = _FakeDB([
        {"id": "old", "number": "+919999999999", "role": "primary",
         "status": "active", "meta_phone_number_id": "phone-1", "tenant_id": "tenant-1"},
    ])

    class _Resp:
        def __init__(self, payload):
            self._payload = payload

        def json(self):
            return self._payload

    class _Client:
        async def __aenter__(self):
            return self

        async def __aexit__(self, *args):
            return False

        async def post(self, url, **kwargs):
            return _Resp({"success": True})

        async def get(self, url, **kwargs):
            return _Resp({"display_phone_number": "+918888888888", "verified_name": "Second Line"})

    with patch("app.services.meta_cloud.exchange_embedded_signup_code", new=AsyncMock(return_value={"access_token": "token-2"})), \
         patch("app.services.meta_cloud.register_phone_number", new=AsyncMock(return_value={"success": True})), \
         patch("app.routes.app_settings.get_supabase", return_value=db), \
         patch("app.routes.app_settings.httpx.AsyncClient", return_value=_Client()), \
         patch("app.routes.app_settings._save_shared_meta_app_credentials"), \
         patch("app.routes.app_settings.record_audit_event"), \
         patch("app.config_dynamic.invalidate_cache"):
        result = await whatsapp_embedded_signup(
            EmbeddedSignupRequest(code="code", waba_id="waba-1", phone_number_id="phone-2"),
            ctx={"tenant_id": "tenant-1"},
            user={"user_id": "user-1"},
        )

    assert result["success"] is True
    written = db.settings_written()
    assert "meta_phone_number_id" not in written, "sender must stay on the incumbent"
    assert written["meta_access_token"] == "token-2", "the refreshed token still lands"
    assert written["meta_waba_id"] == "waba-1"
    assert "meta_phone_display" not in written, "the Hub label names the sender"
