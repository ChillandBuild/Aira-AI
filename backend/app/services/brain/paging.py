"""Bounded, ordered paging for the brain's row reads. PostgREST silently caps a response
at 1000 rows, so anything that could exceed that is paged with .range()."""
import logging
from collections.abc import Callable
from typing import Any

logger = logging.getLogger(__name__)

PAGE_SIZE = 1000
MAX_PAGES = 50  # 50,000 rows: a hard ceiling so one busy tenant cannot make a poll unbounded


def fetch_bounded(build_query: Callable[[], Any], label: str) -> list[dict]:
    """Page through build_query() (which must already be tenant-scoped and ordered by a unique
    key, e.g. .order("created_at").order("id"): rows with equal timestamps may otherwise repeat
    or vanish across page boundaries)."""
    rows: list[dict] = []
    for page_number in range(MAX_PAGES):
        offset = page_number * PAGE_SIZE
        page = build_query().range(offset, offset + PAGE_SIZE - 1).execute().data or []
        rows.extend(page)
        if len(page) < PAGE_SIZE:
            return rows
    logger.warning("brain: %s hit the %d-row ceiling; counts may be understated", label, PAGE_SIZE * MAX_PAGES)
    return rows
