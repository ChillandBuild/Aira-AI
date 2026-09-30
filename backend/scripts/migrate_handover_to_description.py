"""One-off data step for blueprint step 0 (Description grows to 8 sections).

Copies each tenant's old handover_line setting into the 8th Description section
("WHAT AIRA SAYS WHEN IT BRINGS IN YOUR TEAM"), then blanks the old setting.

Why blank it: business_profile.get_handover_line falls back to the old setting only when
the Description has no 8th heading at all. Once the setting is gone, an owner who later
clears the section gets Aira's default wording, not the old line back.

Rules (all covered by tests/test_migrate_handover_to_description.py):
- Dry run by default. Nothing is written unless --apply is passed.
- Idempotent. A Description that already has the 8th heading is skipped.
- The write goes through knowledge_versions.save_description, so a version row exists
  and the change can be undone from version history.
- A tenant with a handover line and no Description gets a Description holding only the
  8th section.
- If adding the section would push the Description over the 700-word cap, the tenant is
  reported and left alone. Client text is never trimmed.
- The old setting is blanked only after the new Description has been re-read and the
  8th section is confirmed to hold the line.

Run from backend/:
    python -m scripts.migrate_handover_to_description                 # dry run
    python -m scripts.migrate_handover_to_description --apply
    python -m scripts.migrate_handover_to_description --tenant <id>   # one tenant only
"""
import argparse
import logging
import os
import sys
from dataclasses import dataclass
from typing import Callable

sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

from app.services import business_profile as bp  # noqa: E402
from app.services import knowledge_versions as kv  # noqa: E402

logger = logging.getLogger(__name__)

LEGACY_KEY = "handover_line"
DESCRIPTION_KEY = kv.DESCRIPTION_KEY
SAVE_REASON = "edit"  # knowledge_versions_reason_check allows only its fixed reasons

MIGRATE, SKIP, STOP, FAILED = "migrate", "skip", "stop", "failed"


@dataclass(frozen=True)
class Plan:
    tenant_id: str
    action: str  # MIGRATE | SKIP | STOP | FAILED
    reason: str
    handover_line: str = ""
    new_description: str = ""


def _handover_heading() -> str:
    return bp._SECTION_BY_KEY[bp.HANDOVER_KEY].heading


def append_handover_section(description: str, line: str) -> str:
    """The Description with the 8th section added at the end. Existing text is not
    reordered or reformatted: parse() and render() are not used to write it."""
    section = f"{_handover_heading()}\n{line.strip()}"
    existing = (description or "").strip()
    return f"{existing}\n\n{section}" if existing else section


def plan_tenant(tenant_id: str, description: str, handover_line: str) -> Plan:
    """Decide what to do for one tenant. Pure: no reads, no writes."""
    line = (handover_line or "").strip()
    if not line:
        return Plan(tenant_id, SKIP, "no handover line to move")
    if bp.HANDOVER_KEY in bp.heading_keys(description):
        return Plan(
            tenant_id, SKIP,
            "Description already has the 8th heading; the old setting is ignored by the reader and left as is",
            handover_line=line,
        )
    proposed = append_handover_section(description, line)
    parsed = bp.parse(proposed)
    errors = bp.validate(parsed.sections, parsed.other)
    if errors:
        return Plan(tenant_id, STOP, "; ".join(errors) + " Decide by hand; nothing was changed.", handover_line=line)
    return Plan(tenant_id, MIGRATE, "copy into the 8th section, then blank the old setting",
                handover_line=line, new_description=proposed)


def _read_setting(db, tenant_id: str, key: str) -> str:
    """Read straight from the database, and let a failed read raise. get_setting turns
    a failed read into "" and a write built on that would replace a real Description."""
    rows = (
        db.table("app_settings").select("value").eq("tenant_id", tenant_id).eq("key", key).limit(1).execute()
    ).data or []
    return (rows[0].get("value") or "") if rows else ""


def find_tenants_with_handover(db, only_tenant: str | None = None) -> list[tuple[str, str]]:
    query = db.table("app_settings").select("tenant_id,value").eq("key", LEGACY_KEY)
    if only_tenant:
        query = query.eq("tenant_id", only_tenant)
    rows = query.execute().data or []
    return sorted((r["tenant_id"], r.get("value") or "") for r in rows if (r.get("value") or "").strip())


def apply_plan(db, plan: Plan) -> None:
    """Write the new Description (with a version row), confirm it, then blank the old
    setting. Raises when the confirmation fails, leaving the old setting in place."""
    kv.save_description(db, plan.tenant_id, plan.new_description, SAVE_REASON, None)
    saved = bp.parse(_read_setting(db, plan.tenant_id, DESCRIPTION_KEY)).sections.get(bp.HANDOVER_KEY, "").strip()
    if saved != plan.handover_line:
        raise RuntimeError("the 8th section did not read back as the handover line; old setting kept")
    db.table("app_settings").delete().eq("tenant_id", plan.tenant_id).eq("key", LEGACY_KEY).execute()
    kv.invalidate_cache(LEGACY_KEY)


def run(db, *, apply: bool, only_tenant: str | None = None, out: Callable[[str], None] = print) -> list[Plan]:
    mode = "APPLY" if apply else "DRY RUN (nothing is written; pass --apply to write)"
    out(f"Handover line -> Description section 8. Mode: {mode}")
    results: list[Plan] = []
    for tenant_id, line in find_tenants_with_handover(db, only_tenant):
        plan = plan_tenant(tenant_id, _read_setting(db, tenant_id, DESCRIPTION_KEY), line)
        if apply and plan.action == MIGRATE:
            try:
                apply_plan(db, plan)
            except Exception as e:  # report and go on: one tenant must not block the rest
                logger.exception("handover migration failed for tenant %s", tenant_id)
                plan = Plan(tenant_id, FAILED, str(e), handover_line=plan.handover_line)
            else:
                out(f"  [{tenant_id}] migrated")
                results.append(plan)
                continue
        label = "WOULD MIGRATE" if plan.action == MIGRATE else plan.action.upper()
        out(f"  [{tenant_id}] {label}: {plan.reason}")
        results.append(plan)
    counts = {a: sum(1 for p in results if p.action == a) for a in (MIGRATE, SKIP, STOP, FAILED)}
    out(f"Done. {len(results)} tenant(s) with a handover line: {counts}")
    return results


def main() -> int:
    parser = argparse.ArgumentParser(description="Move each handover_line setting into Description section 8.")
    parser.add_argument("--apply", action="store_true", help="Write the changes. Without it, only report.")
    parser.add_argument("--tenant", help="Only this tenant id.")
    args = parser.parse_args()

    from app.db.supabase import get_supabase

    results = run(get_supabase(), apply=args.apply, only_tenant=args.tenant)
    return 1 if any(p.action in (STOP, FAILED) for p in results) else 0


if __name__ == "__main__":
    sys.exit(main())
