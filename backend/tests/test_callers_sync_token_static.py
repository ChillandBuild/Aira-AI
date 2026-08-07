import sys
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))


def _read(path: str) -> str:
    return (ROOT / path).read_text(encoding="utf-8")


def test_get_sync_token_endpoint_exists():
    source = _read("app/routes/callers.py")
    assert '@router.get("/{caller_id}/sync-token")' in source
    assert "async def get_sync_token(caller_id: UUID, tenant_id: str = Depends(get_owner_tenant_id))" in source
    # Read-only: must select, never update, the sync_token column in this function
    get_fn_start = source.index("async def get_sync_token")
    post_fn_start = source.index("async def generate_sync_token")
    get_fn_body = source[get_fn_start:post_fn_start]
    assert '.select("sync_token")' in get_fn_body
    assert '.update({"sync_token"' not in get_fn_body


def test_generate_sync_token_endpoint_still_exists():
    # Regression guard: the existing mint endpoint must be untouched by this change
    source = _read("app/routes/callers.py")
    assert '@router.post("/{caller_id}/sync-token")' in source
    assert "async def generate_sync_token(caller_id: UUID, tenant_id: str = Depends(get_owner_tenant_id))" in source
