"""
Static contract checks for the call evaluation v2 wiring in calls.py.
Verifies the source wires KB grounding + outcome into analyze_call and that
the dead evaluate_call/summarize_call imports are gone.
"""
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]


def read(path: str) -> str:
    return (ROOT / path).read_text()


class CallEvaluationV2WiringTests(unittest.TestCase):
    def test_run_summarization_imports_knowledge_context(self):
        source = read("backend/app/routes/calls.py")
        self.assertIn("from app.services.knowledge_service import get_knowledge_context", source)

    def test_run_summarization_fetches_kb_context_from_transcript(self):
        source = read("backend/app/routes/calls.py")
        self.assertIn("get_knowledge_context(tenant_id, query=transcript[:1500])", source)

    def test_analyze_call_receives_outcome_and_kb_context(self):
        source = read("backend/app/routes/calls.py")
        self.assertIn("outcome=outcome", source)
        self.assertIn("kb_context=kb_context", source)

    def test_dead_evaluation_functions_no_longer_imported(self):
        source = read("backend/app/routes/calls.py")
        self.assertNotIn("summarize_call", source)
        self.assertNotIn("evaluate_call", source)


if __name__ == "__main__":
    unittest.main()
