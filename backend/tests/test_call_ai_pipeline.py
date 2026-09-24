"""The durable recording pipeline: claiming, stages, retries and the restart sweep."""
import sys
import unittest
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock, patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from app.services import call_ai_pipeline as pipe


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


EVALUATION = {"evaluation_version": 3, "ai_average": 8.0}


class RunTests(unittest.IsolatedAsyncioTestCase):
    def _patches(self, db, transcript="Telecaller: Hello\nCustomer: Hi", analyze=None):
        return [
            patch.object(pipe, "get_supabase", return_value=db),
            patch.object(pipe, "_load_audio", AsyncMock(return_value=(b"audio", "audio/mpeg"))),
            patch.object(pipe, "transcribe_call", AsyncMock(return_value=(transcript, []))),
            patch.object(pipe, "analyze_call", analyze or AsyncMock(return_value=({"next_action": "Call back"}, dict(EVALUATION)))),
            patch.object(pipe, "_selected_criteria", return_value=["greeting_quality"]),
            patch("app.services.knowledge_service.get_knowledge_context", AsyncMock(return_value="")),
            patch.object(pipe, "finalize_call_score"),
        ]

    async def _run(self, db, **kw):
        patches = self._patches(db, **kw)
        for p in patches:
            p.start()
        try:
            await pipe.run_call_ai("c1")
        finally:
            for p in patches:
                p.stop()

    async def test_full_run_stores_transcript_summary_and_evaluation(self):
        db = FakeDB(call_logs=[_call()], leads=[{"id": "l1", "name": "Ravi"}])
        await self._run(db)
        row = db.row()
        self.assertEqual(row["ai_status"], "done")
        self.assertEqual(row["ai_attempts"], 1)
        self.assertEqual(row["transcript"], "Telecaller: Hello\nCustomer: Hi")
        self.assertEqual(row["evaluation"], EVALUATION)
        stages = [u[1]["ai_status"] for u in db.updates if "ai_status" in u[1]]
        self.assertEqual(stages, ["transcribing", "scoring", "done"])
        self.assertEqual(db.inserts[0][0], "lead_notes")

    async def test_short_call_is_transcribed_but_never_evaluated(self):
        db = FakeDB(call_logs=[_call(duration_seconds=20)], leads=[])
        analyze = AsyncMock()
        await self._run(db, analyze=analyze)
        self.assertEqual(db.row()["ai_status"], "done")
        self.assertIn("transcript", db.row())
        analyze.assert_not_called()

    async def test_failure_goes_back_to_pending_for_the_sweep(self):
        db = FakeDB(call_logs=[_call()], leads=[])
        await self._run(db, analyze=AsyncMock(side_effect=RuntimeError("gemini 503")))
        self.assertEqual(db.row()["ai_status"], "pending")
        self.assertIn("gemini 503", db.row()["ai_error"])

    async def test_third_failure_is_final(self):
        db = FakeDB(call_logs=[_call(ai_attempts=2)], leads=[])
        await self._run(db, analyze=AsyncMock(side_effect=RuntimeError("still down")))
        self.assertEqual(db.row()["ai_status"], "failed")

    async def test_empty_transcript_is_a_failure_not_a_score(self):
        db = FakeDB(call_logs=[_call()], leads=[])
        await self._run(db, transcript="  ")
        self.assertEqual(db.row()["ai_status"], "pending")
        self.assertNotIn("evaluation", db.row())

    async def test_finished_or_exhausted_calls_are_not_claimed(self):
        for row in (_call(ai_status="done"), _call(ai_status="failed"), _call(ai_attempts=3)):
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
            _call(id="exhausted", ai_attempts=3),
            _call(id="fresh", ai_updated_at="9999-01-01T00:00:00+00:00"),
        ])
        runs = []
        with patch.object(pipe, "get_supabase", return_value=db), \
             patch.object(pipe, "run_call_ai", AsyncMock(side_effect=lambda cid: runs.append(cid))), \
             patch.object(pipe, "finalize_call_score") as finalize:
            count = await pipe.sweep_call_ai()
        self.assertEqual(sorted(runs), ["stale", "stuck"])
        self.assertEqual(count, 2)
        exhausted = next(r for r in db.rows["call_logs"] if r["id"] == "exhausted")
        self.assertEqual(exhausted["ai_status"], "failed")
        finalize.assert_called_once_with(db, "exhausted")


if __name__ == "__main__":
    unittest.main()
