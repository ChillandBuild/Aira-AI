import sys
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))


def _read(path: str) -> str:
    return (ROOT / path).read_text(encoding="utf-8")


def test_sim_recording_endpoint_exists():
    source = _read("app/routes/calls.py")
    assert '@public_router.post("/sim-recording")' in source
    assert "_resolve_sim_caller(request)" in source
    assert 'phone_number: str | None = Form(default=None)' in source
    assert 'file_timestamp: int = Form(...)' in source
    assert "file: UploadFile = File(...)" in source


def test_sim_recording_never_creates_call_logs_row():
    source = _read("app/routes/calls.py")
    start = source.index('@public_router.post("/sim-recording")')
    end = source.index("# ── TeleCMI Live Events Webhook ─")
    block = source[start:end]
    assert '.insert(' not in block, "Recording path must not insert new call_logs rows"
    assert 'No matching call log found' in block


def test_sim_recording_only_updates_recording_url():
    source = _read("app/routes/calls.py")
    start = source.index('@public_router.post("/sim-recording")')
    end = source.index("# ── TeleCMI Live Events Webhook ─")
    block = source[start:end]
    update_line = next(line for line in block.splitlines() if '"recording_url": public_url' in line)
    assert update_line.strip().startswith('db.table("call_logs").update({"recording_url": public_url})')


def test_sim_recording_reuses_run_summarization():
    source = _read("app/routes/calls.py")
    start = source.index('@public_router.post("/sim-recording")')
    end = source.index("# ── TeleCMI Live Events Webhook ─")
    block = source[start:end]
    assert "background_tasks.add_task(_run_summarization, call_log_id, public_url)" in block


def test_sim_recording_fallback_match_picks_closest_timestamp():
    source = _read("app/routes/calls.py")
    start = source.index('@public_router.post("/sim-recording")')
    end = source.index("# ── TeleCMI Live Events Webhook ─")
    block = source[start:end]
    fallback_start = block.index("if not call_log_id:")
    fallback_block = block[fallback_start:block.index("if not call_log_id:", fallback_start + 1)]
    assert "for r in (row.data or []):\n            if r.get(\"lead_id\"):\n                call_log_id = r[\"id\"]\n                break" not in fallback_block
    assert "min(" in fallback_block
    assert "candidates" in fallback_block
    assert "call_dt" in fallback_block