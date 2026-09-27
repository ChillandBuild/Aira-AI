"""Language barrier wrap-up -> one Needs-attention row that names the language, even if the AI raised one first."""
import sys
import unittest
from pathlib import Path
from unittest.mock import MagicMock, patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from app.services import call_alerts as ca


class ReassignAlertTests(unittest.TestCase):
    def test_new_alert_names_the_language(self):
        db = MagicMock()
        with patch.object(ca, "raise_alert", return_value=True) as raise_alert:
            ca.raise_reassign_alert(db, tenant_id="t1", call_log_id="call-1", caller_id="c1", language="tamil")
        raise_alert.assert_called_once_with(
            db, tenant_id="t1", type="language_barrier", call_log_id="call-1", caller_id="c1",
            quote="Reassign to a Tamil speaker", detail={"preferred_language": "tamil", "source": "wrapup"},
        )
        db.table.assert_not_called()

    def test_existing_ai_alert_is_rewritten_and_shown_again(self):
        db = MagicMock()
        with patch.object(ca, "raise_alert", return_value=False):
            ca.raise_reassign_alert(db, tenant_id="t1", call_log_id="call-1", caller_id="c1", language="hindi")
        db.table.assert_called_with("call_alerts")
        self.assertEqual(db.table.return_value.update.call_args.args[0], {
            "quote": "Reassign to a Hindi speaker",
            "detail": {"preferred_language": "hindi", "source": "wrapup"},
            "seen_at": None, "seen_by": None,
        })

    def test_other_language_wording(self):
        db = MagicMock()
        with patch.object(ca, "raise_alert", return_value=True) as raise_alert:
            ca.raise_reassign_alert(db, tenant_id="t1", call_log_id="call-1", caller_id=None, language="other")
        self.assertEqual(raise_alert.call_args.kwargs["quote"], "Reassign to someone who speaks the customer's language")


if __name__ == "__main__":
    unittest.main()
