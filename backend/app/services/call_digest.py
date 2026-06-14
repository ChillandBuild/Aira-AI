"""Daily coaching digest — one consolidated LLM call per telecaller per day.

Instead of generating a coaching_tip per call (50× LLM calls/day per caller),
this runs once at end of day, picks the 3 most representative transcripts,
and produces one actionable coaching report.
"""
import logging
from datetime import date, datetime, timezone

from groq import AsyncGroq

from app.config import settings
from app.db.supabase import get_supabase
from app.services.call_summarizer import _SCORE_KEYS

logger = logging.getLogger(__name__)

_client = AsyncGroq(api_key=settings.groq_api_key) if settings.groq_api_key else None
_MODEL = "llama-3.3-70b-versatile"

_DIGEST_PROMPT = (
    "You are a sales coach reviewing a telecaller's full day of calls.\n\n"
    "Today's stats:\n{stats_text}\n\n"
    "Sample transcripts (most representative calls from today):\n{transcripts_text}\n\n"
    "Write a coaching report (max 150 words) with exactly three sections:\n"
    "1. What they did well (cite a specific moment from the transcripts)\n"
    "2. Their main weakness (one repeating pattern, not generic advice)\n"
    "3. One exact phrase they should use tomorrow\n\n"
    "Be direct. No preamble. No markdown headers."
)

# Truncate each transcript to this many characters before sending to LLM.
# Keeps per-call contribution small while preserving key moments.
_TRANSCRIPT_CHARS = 600


def _build_stats_text(stats: dict) -> str:
    text = (
        f"Total calls: {stats['total_calls']} | "
        f"Conversions: {stats['converted']} | "
        f"Callbacks: {stats['callbacks']} | "
        f"Not interested: {stats['not_interested']} | "
        f"No answer: {stats['no_answer']} | "
        f"Avg duration: {stats['avg_duration_seconds']}s | "
        f"Avg score: {stats.get('avg_score', 'N/A')}"
    )
    weakest = stats.get("weakest_criterion")
    if weakest:
        avg = stats["criteria_avg"][weakest]
        text += f" | Weakest area today: {weakest} (avg {avg}/10)"
    return text


def _aggregate_evaluations(rows: list[dict]) -> dict:
    """Aggregate per-criterion scores and outcome-accuracy flags across a day's calls."""
    criteria_sums: dict[str, float] = {k: 0.0 for k in _SCORE_KEYS}
    criteria_counts: dict[str, int] = {k: 0 for k in _SCORE_KEYS}
    outcome_mismatches = 0

    for row in rows:
        evaluation = row.get("evaluation") or {}
        if not isinstance(evaluation, dict):
            continue
        for key in _SCORE_KEYS:
            value = evaluation.get(key)
            if value is not None:
                criteria_sums[key] += float(value)
                criteria_counts[key] += 1
        if evaluation.get("outcome_match") is False:
            outcome_mismatches += 1

    criteria_avg = {
        k: round(criteria_sums[k] / criteria_counts[k], 1)
        for k in _SCORE_KEYS
        if criteria_counts[k] > 0
    }
    weakest_criterion = min(criteria_avg, key=criteria_avg.get) if criteria_avg else None

    return {
        "criteria_avg": criteria_avg,
        "weakest_criterion": weakest_criterion,
        "outcome_mismatches": outcome_mismatches,
    }


def _pick_representative(rows: list[dict]) -> list[dict]:
    """Pick up to 3 distinct calls with transcripts that give the best coaching signal."""
    with_tx = [r for r in rows if r.get("transcript")]
    if not with_tx:
        return []

    best = (
        next((r for r in with_tx if r.get("outcome") == "converted"), None)
        or next((r for r in with_tx if r.get("outcome") == "callback"), None)
    )
    worst_pool = sorted(
        [r for r in with_tx if r.get("outcome") == "not_interested"],
        key=lambda r: r.get("duration_seconds") or 0,
    )
    worst = worst_pool[0] if worst_pool else None
    longest = max(with_tx, key=lambda r: r.get("duration_seconds") or 0)

    seen: set[str] = set()
    selected = []
    for r in [best, worst, longest]:
        if r and r["id"] not in seen:
            seen.add(r["id"])
            selected.append(r)
    return selected


async def generate_daily_digest(caller_id: str, tenant_id: str, for_date: date) -> None:
    """Compute stats + AI coaching report for one caller on for_date, upsert to caller_digests."""
    db = get_supabase()
    date_str = for_date.isoformat()
    day_start = f"{date_str}T00:00:00+00:00"
    day_end = f"{date_str}T23:59:59+00:00"

    rows_res = (
        db.table("call_logs")
        .select("id,outcome,duration_seconds,score,transcript,evaluation")
        .eq("caller_id", caller_id)
        .eq("tenant_id", tenant_id)
        .gte("created_at", day_start)
        .lte("created_at", day_end)
        .execute()
    )
    rows = rows_res.data or []
    if not rows:
        return

    # ── Aggregate stats ───────────────────────────────────────────────
    total = len(rows)
    converted = sum(1 for r in rows if r.get("outcome") == "converted")
    callbacks = sum(1 for r in rows if r.get("outcome") == "callback")
    not_interested = sum(1 for r in rows if r.get("outcome") == "not_interested")
    no_answer = sum(1 for r in rows if r.get("outcome") == "no_answer")
    durations = [r["duration_seconds"] for r in rows if r.get("duration_seconds")]
    avg_duration = sum(durations) // len(durations) if durations else 0
    scores = [float(r["score"]) for r in rows if r.get("score") is not None]
    avg_score = round(sum(scores) / len(scores), 1) if scores else None

    stats = {
        "total_calls": total,
        "converted": converted,
        "callbacks": callbacks,
        "not_interested": not_interested,
        "no_answer": no_answer,
        "avg_duration_seconds": avg_duration,
        "avg_score": avg_score,
    }
    stats.update(_aggregate_evaluations(rows))

    # ── Pick representative transcripts ───────────────────────────────
    selected = _pick_representative(rows)

    coaching_report: str | None = None
    if selected and _client:
        parts = []
        for i, r in enumerate(selected, 1):
            snippet = (r["transcript"] or "")[:_TRANSCRIPT_CHARS]
            parts.append(
                f"[Call {i} — outcome: {r.get('outcome', '?')}, "
                f"duration: {r.get('duration_seconds', 0)}s]\n{snippet}"
            )
        try:
            response = await _client.chat.completions.create(
                model=_MODEL,
                messages=[{
                    "role": "user",
                    "content": _DIGEST_PROMPT.format(
                        stats_text=_build_stats_text(stats),
                        transcripts_text="\n\n".join(parts),
                    ),
                }],
                temperature=0.4,
                max_tokens=250,
            )
            coaching_report = response.choices[0].message.content.strip()
            logger.info(f"Digest generated for caller {caller_id} on {date_str}")
        except Exception as e:
            logger.error(f"Digest LLM call failed for caller {caller_id}: {e}")

    # ── Upsert (safe to re-run) ───────────────────────────────────────
    db.table("caller_digests").upsert(
        {
            "caller_id": caller_id,
            "tenant_id": tenant_id,
            "digest_date": date_str,
            "call_count": total,
            "stats": stats,
            "coaching_report": coaching_report,
        },
        on_conflict="caller_id,digest_date",
    ).execute()


async def generate_digests_for_tenant(tenant_id: str, for_date: date) -> int:
    """Run daily digest for every active caller in a tenant. Returns count processed."""
    db = get_supabase()
    callers = (
        db.table("callers")
        .select("id")
        .eq("tenant_id", tenant_id)
        .eq("active", True)
        .execute()
    )
    count = 0
    for row in (callers.data or []):
        try:
            await generate_daily_digest(row["id"], tenant_id, for_date)
            count += 1
        except Exception as e:
            logger.error(f"Digest failed for caller {row['id']}: {e}")
    return count


async def generate_all_digests(for_date: date) -> None:
    """APScheduler entry point — runs digests for all tenants."""
    db = get_supabase()
    tenants = db.table("app_settings").select("tenant_id").execute()
    seen: set[str] = set()
    for row in (tenants.data or []):
        tid = row.get("tenant_id")
        if tid and tid not in seen:
            seen.add(tid)
            try:
                n = await generate_digests_for_tenant(tid, for_date)
                logger.info(f"Digest job: tenant {tid} — {n} caller(s) processed for {for_date}")
            except Exception as e:
                logger.error(f"Digest job failed for tenant {tid}: {e}")
