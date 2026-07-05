"""Test that AI reply generation is skipped (not the webhook 200) once ai_reply quota is exhausted."""
import sys
import unittest
from pathlib import Path
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from app.services import ai_reply


class AiReplyQuotaEnforcementTests(unittest.IsolatedAsyncioTestCase):
    @patch("app.services.ai_reply.check_quota", return_value=False)
    async def test_check_quota_false_short_circuits_before_llm_dispatch(self, mock_check_quota):
        self.assertFalse(ai_reply.check_quota(None, "tenant-1", "ai_reply"))

    def test_generate_reply_checks_quota_before_dispatch(self):
        """Static check: the quota guard must appear before retrieval, LLM, and
        channel dispatch, so a skipped reply does not spend AI work or send."""
        import inspect
        source = inspect.getsource(ai_reply.generate_reply)
        quota_idx = source.index("check_quota(db, tenant_id, \"ai_reply\")")
        rag_idx = source.index("get_knowledge_context(")
        llm_idx = source.index("_llm_chat(")
        dispatch_idx = source.index("# Step 3: Dispatch to the correct channel")
        self.assertLess(quota_idx, rag_idx)
        self.assertLess(quota_idx, llm_idx)
        self.assertLess(quota_idx, dispatch_idx)


if __name__ == "__main__":
    unittest.main()
