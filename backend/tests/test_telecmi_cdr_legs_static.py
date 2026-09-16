"""Static contract tests for the TeleCMI CHUB two-leg CDR model.

CHUB sends two CDRs per outbound click2call (docs: outgoing-answered,
outgoing-missed) — leg 'a' is the agent leg, leg 'b' the customer leg, both
carrying the same request_id/extra_params. Treating both as the whole call
made the final status arrival-order dependent and metered every call twice,
so these assertions pin the leg-aware contract in place.
"""
import sys
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))


def _read(path: str) -> str:
    return (ROOT / path).read_text(encoding="utf-8")


def test_cdr_distinguishes_legs():
    source = _read("app/routes/calls.py")
    # Leg is read and leg A short-circuits before the authoritative update path.
    assert 'leg = str(cdr.get("leg") or "").strip().lower()' in source
    assert 'if leg == "a":' in source
    # Leg A 'missed' is the real agent-never-answered signal (CHUB has no
    # `user_missed` status), and must not clobber a leg B 'completed'.
    assert 'if status == "missed" and current_status != "completed":' in source
    # The removed non-existent status must not come back.
    assert '== "user_missed"' not in source


def test_cdr_duration_uses_documented_fields_only():
    source = _read("app/routes/calls.py")
    assert 'cdr.get("answeredsec")' in source
    assert 'cdr.get("billedsec")' in source
    # `bilsec` is not a field in any CHUB API — it was a typo'd fallback.
    assert 'cdr.get("bilsec")' not in source


def test_call_minutes_are_not_metered_twice():
    source = _read("app/routes/calls.py")
    # A redelivered CDR (TeleCMI retries) must not double-bill: an already-set
    # duration_seconds means this call was metered on an earlier delivery.
    assert 'already_metered = bool(log_row.data.get("duration_seconds"))' in source
    assert "if not already_metered and updates.get" in source
    # duration_seconds has to be selected for that guard to mean anything.
    assert '.select("id,caller_id,lead_id,tenant_id,status,duration_seconds")' in source


def test_cdr_lead_match_normalizes_phone():
    source = _read("app/routes/calls.py")
    # leads.phone is stored as '+91XXXXXXXXXX'; the raw CDR number is bare
    # digits, so it must be normalized or the lookup never matches and every
    # CDR silently creates a duplicate lead.
    assert "dialed = _normalize_sim_phone(str(raw_dialed)) if raw_dialed else None" in source


def test_recording_uses_documented_chub_endpoint():
    client = _read("app/services/telecmi_client.py")
    calls = _read("app/routes/calls.py")
    # play-record docs: rest.telecmi.com/v2/play with appid/secret/file.
    assert 'TELECMI_RECORDING_BASE_URL = "https://rest.telecmi.com/v2/play"' in client
    assert '"secret": secret' in client
    # The PIOPIY endpoint and its `token` param are the wrong product's API.
    assert "piopiy.telecmi.com" not in calls
    assert "&token=" not in calls
    # CHUB only ever sends `filename` — record_url/recording_url do not exist.
    assert 'cdr.get("record_url")' not in calls
    assert 'cdr.get("recording_url")' not in calls
    assert 'recording_filename = cdr.get("filename")' in calls


def test_recording_download_rejects_non_audio():
    source = _read("app/routes/calls.py")
    # TeleCMI answers a failed playback with HTTP 200 + a JSON error body, so a
    # status check alone would store the error blob as the call's .mp3.
    assert "def _is_audio_payload(" in source
    assert "if not _is_audio_payload(resp, audio_bytes):" in source


def test_live_events_never_write_terminal_status():
    source = _read("app/routes/calls.py")
    # Live events fire per leg too; leg A's 'hangup' arrives while the customer
    # leg may still be up and previously flipped the log to "completed".
    assert 'leg = str(event.get("leg") or "").strip().lower()' in source
    # Documented live statuses only — 'dial'/'initiated'/'in_progress'/'ended'
    # were never real CHUB values.
    assert 'if status in ("started", "ringing"):' in source
    assert 'elif status == "answered":' in source
    assert '"dial"' not in source
    assert '"ended"' not in source
    # Terminal status comes from the CDR, and progress writes are guarded so a
    # late event cannot overwrite it.
    assert '.in_("status", ["initiated", "in_progress"])' in source
