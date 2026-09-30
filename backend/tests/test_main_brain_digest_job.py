"""The Aira Brain weekly digest job in app.main: it must not block the event loop, and the
startup log lines must describe the jobs actually registered."""
import logging
import re
import threading
from unittest.mock import patch

import pytest

import app.main
from test_scheduler_local_mode import FakeScheduler


@pytest.mark.asyncio
async def test_the_digest_runs_off_the_event_loop_thread(monkeypatch):
    loop_thread = threading.get_ident()
    seen: list[int] = []
    monkeypatch.setattr("app.db.supabase.get_supabase", lambda: object())
    monkeypatch.setattr(
        "app.services.brain_digest.send_weekly_digests",
        lambda db: seen.append(threading.get_ident()),
    )
    await app.main._send_brain_weekly_digest()
    assert len(seen) == 1
    assert seen[0] != loop_thread


async def _startup_logs(caplog, *, enabled: bool) -> tuple[list[str], FakeScheduler]:
    caplog.set_level(logging.INFO, logger="app.main")
    scheduler = FakeScheduler()
    with patch("app.main._scheduler", scheduler), patch("app.main.settings.scheduler_enabled", enabled):
        async with app.main.lifespan(app.main.app):
            pass
    return [r.message for r in caplog.records], scheduler


@pytest.mark.asyncio
async def test_the_paused_log_counts_every_registered_job(caplog):
    messages, scheduler = await _startup_logs(caplog, enabled=False)
    paused = next(m for m in messages if "PAUSED" in m)
    assert f"{len(scheduler.calls['add_job'])} jobs registered" in paused


@pytest.mark.asyncio
async def test_the_started_log_lists_the_digest_job(caplog):
    messages, _ = await _startup_logs(caplog, enabled=True)
    started = next(m for m in messages if m.startswith("Schedulers started"))
    assert re.search(r"brain-weekly-digest\(Mon 09:00 IST\)", started)
