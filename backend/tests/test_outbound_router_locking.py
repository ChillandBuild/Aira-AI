"""get_best_number() must never select a number that's over the tenant's
numbers_pool quota, even if it's status=active/unpaused/warmed-up -- this is
what makes a subscription downgrade take effect immediately, without waiting
for a manual re-sync or any write to the number's own row."""
import sys
from pathlib import Path
from unittest.mock import MagicMock, patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import pytest

from app.services.outbound_router import get_best_number


def _candidate(id_, **overrides):
    row = {
        "id": id_, "quality_rating": "green", "messaging_tier": 1000,
        "daily_send_count": 0, "warm_up_day": 14, "status": "active",
    }
    row.update(overrides)
    return row


@pytest.mark.asyncio
async def test_excludes_locked_candidate_even_if_otherwise_eligible():
    db = MagicMock()
    rows = [_candidate("locked-1"), _candidate("unlocked-1")]
    db.table.return_value.select.return_value.eq.return_value.eq.return_value.neq.return_value.gte.return_value.eq.return_value.execute.return_value = MagicMock(data=rows)

    with patch("app.services.outbound_router.get_supabase", return_value=db), \
         patch("app.services.outbound_router.get_unlocked_number_ids", return_value={"unlocked-1"}):
        best = await get_best_number("tenant-1")

    assert best is not None
    assert best["id"] == "unlocked-1"


@pytest.mark.asyncio
async def test_returns_none_when_every_candidate_is_locked():
    db = MagicMock()
    rows = [_candidate("locked-1")]
    db.table.return_value.select.return_value.eq.return_value.eq.return_value.neq.return_value.gte.return_value.eq.return_value.execute.return_value = MagicMock(data=rows)

    with patch("app.services.outbound_router.get_supabase", return_value=db), \
         patch("app.services.outbound_router.get_unlocked_number_ids", return_value=set()):
        best = await get_best_number("tenant-1")

    assert best is None
