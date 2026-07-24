import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from app.routes import meta_ads


def test_router_exposes_expected_paths():
    paths = {r.path for r in meta_ads.router.routes}
    assert "/performance" in paths
    assert "/analytics" in paths
    assert "/filters" in paths
