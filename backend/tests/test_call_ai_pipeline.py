"""The durable recording pipeline: claiming, stages, retries, the restart sweep, and the
new v4 flow (per-track transcription -> sorting -> marking -> alerts -> check 10)."""
import sys
import unittest
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock, patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from app.services import call_ai_pipeline as pipe
from app.services.call_lines import Line
from app.services.call_marking import CHECKS, MarkResult
from app.services.call_sorting import SortResult
from app.services.call_transcribe import TrackTranscript


class _Res:
    def __init__(self, data):
        self.data = data


class _Q:
    def __init__(self, db, table):
        self.db, self.table, self.op, self.payload, self.filters = db, table, "select", None, []

    def select(self, *a, **k):
        return self

    def update(self, payload):
        self.op, self.payload = "update", payload
        return self

    def insert(self, payload):
        self.op, self.payload = "insert", payload
        return self

    def eq(self, col, val):
        self.filters.append(lambda r: r.get(col) == val)
        return self

    def in_(self, col, vals):
        self.filters.append(lambda r: r.get(col) in vals)
        return self

    def lt(self, col, val):
        self.filters.append(lambda r: (r.get(col) or "") < val)
        return self

    def order(self, *a, **k):
        return self

    def limit(self, *a):
        return self

    def maybe_single(self):
        self.single = True
        return self

    def execute(self):
        rows = [r for r in self.db.rows.get(self.table, []) if all(f(r) for f in self.filters)]
        if self.op == "update":
            for r in rows:
                r.update(self.payload)
            self.db.updates.append((self.table, dict(self.payload)))
            return _Res([dict(r) for r in rows])
        if self.op == "insert":
            self.db.inserts.append((self.table, self.payload))
            return _Res([self.payload])
        if getattr(self, "single", False):
            return _Res(dict(rows[0]) if rows else None)
        return _Res([dict(r) for r in rows])


class FakeDB:
    def __init__(self, **rows):
        self.rows = rows
        self.updates, self.inserts = [], []
        self.storage = MagicMock()
        self.storage.from_.return_value.get_public_url.return_value = "https://storage.test/c1.mp3"

    def table(self, name):
        return _Q(self, name)

    def row(self):
        return self.rows["call_logs"][0]


def _call(**over):
    row = {"id": "c1", "tenant_id": "t1", "caller_id": "k1", "lead_id": "l1", "duration_seconds": 240,
           "recording_url": "https://storage.test/c1.mp3", "recording_filename": "rec.mp3",
           "ai_status": "pending", "ai_attempts": 0, "ai_updated_at": "2026-09-24T00:00:00+00:00"}
    row.update(over)
    return row


class ClaimTests(unittest.IsolatedAsyncioTestCase):
    async def test_finished_or_exhausted_calls_are_not_claimed(self):
        for row in (_call(ai_status="done"), _call(ai_status="failed"), _call(ai_attempts=2)):
            db = FakeDB(call_logs=[row])
            self.assertIsNone(pipe._claim(db, "c1"))

    async def test_claim_is_lost_when_another_worker_gets_there_first(self):
        """The webhook task and the sweep can't both process one call."""
        db = FakeDB(call_logs=[_call()])
        real_table = db.table

        def table(name):
            query = real_table(name)
            real_update = query.update

            def update(payload):
                db.row()["ai_attempts"] = 1  # the other worker claimed between our read and write
                return real_update(payload)

            query.update = update
            return query

        db.table = table
        self.assertIsNone(pipe._claim(db, "c1"))

    async def test_claim_bumps_the_attempt_and_moves_to_transcribing(self):
        db = FakeDB(call_logs=[_call(ai_attempts=1, ai_status="transcribing")])
        self.assertEqual(pipe._claim(db, "c1")["ai_attempts"], 2)
        self.assertEqual(db.row()["ai_status"], "transcribing")


def _tracks():
    return TrackTranscript([Line(1, "telecaller", "Hello"), Line(3, "customer", "I need a demo")], [(1.0, 2.0)], [(3.0, 5.0)], True)


def _sort(group):
    early = None if group == "real_conversation" else {"polite": True, "rude_quote": None, "enquiry_confirmed_early": False, "expected_crm": "other", "crm_matches": None}
    return SortResult(group, [], {"next_action": "Call back"}, early, False, None, None)


class NewFlowTests(unittest.IsolatedAsyncioTestCase):
    async def _process(self, db, row, group):
        marking = MarkResult(checks=[{"key": c["key"], "full": c["full"], "level": "good" if c["key"] != "crm_update" else None} for c in CHECKS])
        with patch.object(pipe, "_load_audio", AsyncMock(return_value=(b"wav", "audio/wav"))), \
             patch.object(pipe, "transcribe_tracks", AsyncMock(return_value=_tracks())), \
             patch.object(pipe, "sort_call", AsyncMock(return_value=_sort(group))), \
             patch.object(pipe, "mark_call", AsyncMock(return_value=marking)) as mark, \
             patch.object(pipe, "raise_alert") as alert, \
             patch("app.services.knowledge_service.get_knowledge_context", AsyncMock(return_value="")):
            await pipe._process(db, row, None)
        return mark, alert

    async def test_very_short_call_is_never_transcribed(self):
        db = MagicMock()
        with patch.object(pipe, "transcribe_tracks", AsyncMock()) as tr:
            await pipe._process(db, {"id": "c", "tenant_id": "t", "duration_seconds": 20}, None)
        tr.assert_not_called()

    async def test_early_exit_skips_marking(self):
        mark, _ = await self._process(MagicMock(), {"id": "c", "tenant_id": "t", "duration_seconds": 90, "lead_id": None}, "early_exit")
        mark.assert_not_called()

    async def test_real_conversation_is_marked(self):
        mark, _ = await self._process(MagicMock(), {"id": "c", "tenant_id": "t", "duration_seconds": 90, "lead_id": None}, "real_conversation")
        mark.assert_called_once()


class RunCallAiTests(unittest.IsolatedAsyncioTestCase):
    async def test_success_path_finalizes_score_and_checks_crm(self):
        db = FakeDB(call_logs=[_call()])
        with patch.object(pipe, "get_supabase", return_value=db), \
             patch.object(pipe, "_process", AsyncMock()), \
             patch.object(pipe, "finalize_call_score") as finalize, \
             patch.object(pipe, "mark_crm_update", AsyncMock()) as crm:
            await pipe.run_call_ai("c1")
        finalize.assert_called_once_with(db, "c1")
        crm.assert_awaited_once_with(db, "c1")

    async def test_non_final_failure_goes_back_to_pending_without_an_alert(self):
        db = FakeDB(call_logs=[_call()])
        with patch.object(pipe, "get_supabase", return_value=db), \
             patch.object(pipe, "_process", AsyncMock(side_effect=RuntimeError("gemini 503"))), \
             patch.object(pipe, "raise_alert") as alert, \
             patch.object(pipe, "finalize_call_score"), \
             patch.object(pipe, "mark_crm_update", AsyncMock()):
            await pipe.run_call_ai("c1")
        self.assertEqual(db.row()["ai_status"], "pending")
        self.assertIn("gemini 503", db.row()["ai_error"])
        alert.assert_not_called()

    async def test_final_failure_is_marked_failed_and_raises_a_transcript_failed_alert(self):
        db = FakeDB(call_logs=[_call(ai_attempts=1)])  # bumped to MAX_ATTEMPTS(2) on claim
        with patch.object(pipe, "get_supabase", return_value=db), \
             patch.object(pipe, "_process", AsyncMock(side_effect=RuntimeError("still down"))), \
             patch.object(pipe, "raise_alert") as alert, \
             patch.object(pipe, "finalize_call_score"), \
             patch.object(pipe, "mark_crm_update", AsyncMock()):
            await pipe.run_call_ai("c1")
        self.assertEqual(db.row()["ai_status"], "failed")
        alert.assert_called_once()
        self.assertEqual(alert.call_args.kwargs["type"], "transcript_failed")

    async def test_a_broken_alert_insert_does_not_stop_scoring_or_the_crm_check(self):
        """A non-duplicate error from raise_alert on the final-failure path must not
        abort finalize_call_score / mark_crm_update."""
        db = FakeDB(call_logs=[_call(ai_attempts=1)])  # bumped to MAX_ATTEMPTS(2) on claim
        with patch.object(pipe, "get_supabase", return_value=db), \
             patch.object(pipe, "_process", AsyncMock(side_effect=RuntimeError("still down"))), \
             patch.object(pipe, "raise_alert", side_effect=RuntimeError("insert failed")), \
             patch.object(pipe, "finalize_call_score") as finalize, \
             patch.object(pipe, "mark_crm_update", AsyncMock()) as crm:
            await pipe.run_call_ai("c1")
        self.assertEqual(db.row()["ai_status"], "failed")
        finalize.assert_called_once_with(db, "c1")
        crm.assert_awaited_once_with(db, "c1")


class LoadAudioTests(unittest.IsolatedAsyncioTestCase):
    async def test_first_run_downloads_from_telecmi_and_stores_the_recording(self):
        db = FakeDB(call_logs=[_call(recording_url=None)])
        with patch.object(pipe, "_download_from_telecmi", AsyncMock(return_value=b"ID3" + bytes(4000))):
            audio, mime = await pipe._load_audio(db, db.row(), "2222223")
        self.assertEqual(db.row()["recording_url"], "https://storage.test/c1.mp3")
        self.assertEqual(mime, "audio/mp3")
        db.storage.from_.assert_called_with("call-recordings")

    async def test_telecmi_download_url_follows_the_play_record_docs(self):
        settings = {"telecmi_app_id": "33337312", "telecmi_secret": "app-secret-xyz", "telecmi_recording_base_url": None}
        response = MagicMock(status_code=200, content=b"ID3" + bytes(4000), headers={"content-type": "audio/mpeg"})
        client = MagicMock()
        client.__aenter__ = AsyncMock(return_value=client)
        client.__aexit__ = AsyncMock(return_value=False)
        client.get = AsyncMock(return_value=response)
        with patch.object(pipe, "get_setting", side_effect=lambda k, **kw: settings.get(k)), \
             patch.object(pipe.httpx, "AsyncClient", return_value=client), \
             patch.object(pipe.asyncio, "sleep", AsyncMock()):
            audio = await pipe._download_from_telecmi(_call(recording_url=None), "2222223")
        url = client.get.call_args.args[0]
        self.assertIn("rest.telecmi.com/v2/play", url)
        self.assertIn("appid=2222223", url)
        self.assertIn("file=rec.mp3", url)
        self.assertTrue(audio.startswith(b"ID3"))

    async def test_missing_telecmi_credentials_fail_loudly(self):
        with patch.object(pipe, "get_setting", return_value=None):
            with self.assertRaises(RuntimeError):
                await pipe._download_from_telecmi(_call(recording_url=None), None)


class QueueAndSweepTests(unittest.IsolatedAsyncioTestCase):
    def test_queue_resets_progress(self):
        db = FakeDB(call_logs=[_call(ai_status="failed", ai_attempts=3, ai_error="x")])
        pipe.queue_call_ai(db, "c1", "new.mp3")
        row = db.row()
        self.assertEqual((row["ai_status"], row["ai_attempts"], row["ai_error"], row["recording_filename"]), ("pending", 0, None, "new.mp3"))

    def test_retry_only_touches_failed_calls_in_the_tenant(self):
        db = FakeDB(call_logs=[_call(ai_status="failed", ai_attempts=3)])
        self.assertFalse(pipe.retry_call_ai(db, "c1", "other-tenant"))
        self.assertTrue(pipe.retry_call_ai(db, "c1", "t1"))
        self.assertEqual(db.row()["ai_status"], "pending")
        self.assertFalse(pipe.retry_call_ai(db, "c1", "t1"), "a pending call has nothing to retry")

    async def test_sweep_resumes_stale_calls_and_fails_exhausted_ones(self):
        db = FakeDB(call_logs=[
            _call(id="stale"),
            _call(id="stuck", ai_status="transcribing"),
            _call(id="exhausted", ai_attempts=2),
            _call(id="fresh", ai_updated_at="9999-01-01T00:00:00+00:00"),
        ])
        runs = []
        with patch.object(pipe, "get_supabase", return_value=db), \
             patch.object(pipe, "run_call_ai", AsyncMock(side_effect=lambda cid: runs.append(cid))), \
             patch.object(pipe, "finalize_call_score") as finalize, \
             patch.object(pipe, "raise_alert") as alert:
            count = await pipe.sweep_call_ai()
        self.assertEqual(sorted(runs), ["stale", "stuck"])
        self.assertEqual(count, 2)
        exhausted = next(r for r in db.rows["call_logs"] if r["id"] == "exhausted")
        self.assertEqual(exhausted["ai_status"], "failed")
        finalize.assert_called_once_with(db, "exhausted")
        alert.assert_called_once()
        self.assertEqual(alert.call_args.kwargs["type"], "transcript_failed")

    async def test_a_broken_alert_insert_does_not_abort_the_rest_of_the_sweep(self):
        db = FakeDB(call_logs=[
            _call(id="exhausted-first", ai_attempts=2),
            _call(id="exhausted-second", ai_attempts=2),
            _call(id="stale"),
        ])
        runs = []
        with patch.object(pipe, "get_supabase", return_value=db), \
             patch.object(pipe, "run_call_ai", AsyncMock(side_effect=lambda cid: runs.append(cid))), \
             patch.object(pipe, "finalize_call_score") as finalize, \
             patch.object(pipe, "raise_alert", side_effect=RuntimeError("insert failed")):
            count = await pipe.sweep_call_ai()
        self.assertEqual(count, 1)
        self.assertEqual(runs, ["stale"])
        self.assertEqual(finalize.call_count, 2)
        for cid in ("exhausted-first", "exhausted-second"):
            row = next(r for r in db.rows["call_logs"] if r["id"] == cid)
            self.assertEqual(row["ai_status"], "failed")


class SweepCrmCutoffTests(unittest.IsolatedAsyncioTestCase):
    async def test_only_provisional_real_conversations_past_cutoff_are_rechecked(self):
        db = MagicMock()
        select = db.table.return_value.select.return_value
        eq1 = select.eq.return_value
        eq2 = eq1.eq.return_value
        eq3 = eq2.eq.return_value
        in_ = eq3.in_.return_value
        lt = in_.lt.return_value
        lt.limit.return_value.execute.return_value = MagicMock(data=[{"id": "c1"}, {"id": "c2"}])
        with patch.object(pipe, "get_supabase", return_value=db), \
             patch.object(pipe, "mark_crm_update", AsyncMock(side_effect=[True, False])) as crm:
            changed = await pipe.sweep_crm_cutoff()
        self.assertEqual(changed, 1)
        self.assertEqual(crm.await_count, 2)
        db.table.assert_called_with("call_logs")
        select.eq.assert_called_once_with("provider", "telecmi")
        eq1.eq.assert_called_once_with("ai_status", "done")
        eq2.eq.assert_called_once_with("score_final", False)
        eq3.in_.assert_called_once_with("call_group", ["real_conversation", "early_exit"])
        lt_args = in_.lt.call_args.args
        self.assertEqual(lt_args[0], "created_at")
        self.assertIsInstance(lt_args[1], str)


if __name__ == "__main__":
    unittest.main()
