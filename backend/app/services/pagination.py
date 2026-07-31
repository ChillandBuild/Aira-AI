"""Generic Supabase/PostgREST pagination helper.

PostgREST caps result sets at 1000 rows and returns no error or truncation
flag -- silently dropping data past the cap. Any fetch that could return
more than 1000 rows must page through with .range() instead of a single
.execute() call. See migration 157 for the same problem solved via SQL
aggregation instead; use this helper only where the raw rows are genuinely
needed in Python (the aggregation logic already exists and is correct, and
rewriting it into SQL would be the riskier change).
"""
import asyncio
from typing import Any, Callable


async def fetch_all_rows(
    build_query: Callable[[], Any], page_size: int = 1000
) -> list[dict]:
    rows: list[dict] = []
    offset = 0
    while True:
        page = (
            await asyncio.to_thread(
                lambda: build_query().range(offset, offset + page_size - 1).execute()
            )
        ).data or []
        rows.extend(page)
        if len(page) < page_size:
            break
        offset += page_size
    return rows
