import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from app.routes import meta_ads


def test_write_routes_registered():
    flat = {r.path for r in meta_ads.router.routes if hasattr(r, "methods")}
    assert "/pages" in flat
    assert "/media" in flat
    assert "/campaigns" in flat
    assert "/{campaign_id}/status" in flat
    assert "/{campaign_id}/budget" in flat
