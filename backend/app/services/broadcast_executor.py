"""Execute a scheduled broadcast row from the scheduled_broadcasts table."""
import csv
import io
import json
import logging
import random as _random
import re as _re
from datetime import datetime, timezone

import httpx

from app.db.supabase import get_supabase
from app.services.entitlements import meter
from app.services.meta_cloud import send_template_message
from app.services.outbound_router import get_best_number, increment_send_count
from app.services.segmentation import new_lead_score_and_segment

logger = logging.getLogger(__name__)


def _normalize_phone(raw: str) -> str:
    digits = "".join(c for c in raw if c.isdigit())
    if not digits:
        return ""
    if not digits.startswith("91") and len(digits) == 10:
        digits = "91" + digits
    return "+" + digits


def _clean_text(val: str | None) -> str:
    return (val or "").strip()


def _meta_error_detail(error_msg: str) -> str:
    """Human-readable Meta error for the failed CSV — '(#code) message', else trimmed raw."""
    if not error_msg:
        return ""
    m = _re.search(r'"message"\s*:\s*"((?:[^"\\]|\\.)*)"', error_msg)
    msg = m.group(1).encode().decode("unicode_escape") if m else error_msg.strip()
    msg = _re.sub(r"^\d{3}:\s*", "", msg)
    return msg[:300]


async def execute_broadcast(row: dict) -> dict:
    """Run a single scheduled_broadcasts row and return a result dict."""
    row_id = row["id"]
    tenant_id = row["tenant_id"]
    template_name = row["template_name"]
    variable_mapping: list[str] = row.get("variable_mapping") or []
    opt_in_source = row.get("opt_in_source") or ""
    tag_id: str | None = row.get("tag_id")

    db = get_supabase()

    # Mark running using a Compare-And-Swap (CAS) lock
    res = (
        db.table("scheduled_broadcasts")
        .update({"status": "running"})
        .eq("id", row_id)
        .eq("status", "pending")
        .execute()
    )
    if not res.data:
        logger.info(f"Broadcast {row_id} already acquired by another worker or not pending.")
        return {"sent": 0, "failed": 0}

    try:
        leads_raw: list[dict] = row.get("leads_json") or []
        if not leads_raw:
            _finish(db, row_id, "done", {"sent": 0, "failed": 0, "note": "empty_leads"})
            return {"sent": 0, "failed": 0}

        # Get best number
        number_rows = (
            db.table("phone_numbers")
            .select("*")
            .eq("tenant_id", tenant_id)
            .eq("role", "primary")
            .eq("paused_outbound", False)
            .execute()
            .data
        )
        best_number = number_rows[0] if number_rows else await get_best_number(tenant_id)
        if not best_number:
            raise RuntimeError("No primary number available for scheduled broadcast")

        # Fetch template metadata (including variations for rotation)
        tpl_lang = "en"
        tpl_body = ""
        tpl_variations: list[str] = []
        tpl_row = (
            db.table("message_templates")
            .select("language,body_text,variations")
            .eq("name", template_name)
            .eq("tenant_id", tenant_id)
            .limit(1)
            .execute()
        )
        if tpl_row.data:
            tpl_lang = tpl_row.data[0].get("language") or "en"
            tpl_body = tpl_row.data[0].get("body_text") or ""
            raw_variations = tpl_row.data[0].get("variations") or []
            if isinstance(raw_variations, list):
                tpl_variations = [v for v in raw_variations if isinstance(v, str) and v.strip()]

        # Build pool: primary template + approved sibling variants
        template_pool: list[tuple[str, str, str]] = [(template_name, tpl_lang, tpl_body)]
        for sibling_name in tpl_variations:
            sib_row = (
                db.table("message_templates")
                .select("language,body_text")
                .eq("name", sibling_name)
                .eq("tenant_id", tenant_id)
                .limit(1)
                .execute()
            )
            if sib_row.data:
                sib_lang = sib_row.data[0].get("language") or "en"
                sib_body = sib_row.data[0].get("body_text") or ""
                template_pool.append((sibling_name, sib_lang, sib_body))

        # Opted-out phones
        all_phones = [_normalize_phone(l.get("phone", "")) for l in leads_raw if _normalize_phone(l.get("phone", ""))]
        opted_out_phones: set[str] = set()
        if all_phones:
            rows = db.table("leads").select("phone").in_("phone", all_phones).eq("tenant_id", tenant_id).eq("opted_out", True).execute()
            opted_out_phones = {r["phone"] for r in (rows.data or [])}

        # Suppress leads with 3+ consecutive unreplied outbound messages
        suppressed_phones: set[str] = set()
        if all_phones:
            supp_rows = db.table("leads").select("phone").in_("phone", all_phones).eq("tenant_id", tenant_id).gte("outbound_no_reply_count", 3).execute()
            suppressed_phones = {r["phone"] for r in (supp_rows.data or [])}

        # Suppress leads who previously replied negatively to any broadcast
        negative_reply_phones: set[str] = set()
        if all_phones:
            neg_rows = (
                db.table("leads")
                .select("phone")
                .in_("phone", all_phones)
                .eq("tenant_id", tenant_id)
                .not_.is_("broadcast_negative_reply_at", "null")
                .execute()
            )
            negative_reply_phones = {r["phone"] for r in (neg_rows.data or [])}

        lead_rows = db.table("leads").select("id,phone,name").in_("phone", all_phones).eq("tenant_id", tenant_id).execute()
        phone_to_lead_id = {r["phone"]: r["id"] for r in (lead_rows.data or [])}

        sent = 0
        failed = 0
        broadcast_id = row_id  # reuse scheduled_broadcast id as broadcast_id
        recipient_rows = []

        for lead in leads_raw:
            phone = _normalize_phone(lead.get("phone", ""))
            if not phone or phone in opted_out_phones or phone in suppressed_phones or phone in negative_reply_phones:
                failed += 1
                recipient_rows.append({
                    "tenant_id": tenant_id,
                    "broadcast_id": broadcast_id,
                    "lead_id": None,
                    "phone": phone,
                    "name": _clean_text(lead.get("name")),
                    "send_status": "failed",
                    "tag_id": tag_id,
                })
                continue

            lead_id = phone_to_lead_id.get(phone)
            lead_name = _clean_text(lead.get("name"))
            extra_cols: dict = lead.get("extra_cols") or {}

            # Pick a random template from pool for this lead
            chosen_name, chosen_lang, chosen_body = _random.choice(template_pool)
            has_vars_this = bool(_re.search(r"\{\{\d+\}\}", chosen_body))

            try:
                components: list[dict] = []
                if has_vars_this:
                    params = []
                    for col in (variable_mapping or []):
                        val = extra_cols.get(col, "") or ""
                        params.append({"type": "text", "text": val or "Customer"})
                    if not params:
                        params = [{"type": "text", "text": lead_name or "Customer"}]
                    components = [{"type": "body", "parameters": params}]

                _send_resp = await send_template_message(
                    to_number=phone,
                    template_name=chosen_name,
                    lang_code=chosen_lang,
                    components=components,
                    phone_number_id=best_number.get("meta_phone_number_id"),
                    tenant_id=tenant_id,
                )
                _meta_msg_id: str | None = None
                try:
                    _meta_msg_id = ((_send_resp or {}).get("messages") or [{}])[0].get("id")
                except Exception:
                    pass

                sent += 1
                recipient_rows.append({
                    "tenant_id": tenant_id,
                    "broadcast_id": broadcast_id,
                    "lead_id": lead_id,
                    "phone": phone,
                    "name": lead_name,
                    "send_status": "sent",
                    "meta_message_id": _meta_msg_id,
                    "tag_id": tag_id,
                    "extra_cols": extra_cols or None,
                })
                # Track-only usage metering: one billable send per successfully
                # delivered recipient. Never blocks/caps — best-effort only.
                meter(db, tenant_id, "message_sent")

                if lead_id:
                    try:
                        db.table("messages").insert({
                            "lead_id": lead_id,
                            "tenant_id": tenant_id,
                            "direction": "outbound",
                            "channel": "whatsapp",
                            "content": f"[Template: {chosen_name}]",
                            "is_ai_generated": False,
                            "meta_message_id": _meta_msg_id,
                        }).execute()
                    except Exception:
                        pass
                    try:
                        db.rpc("increment_lead_no_reply_count", {"p_lead_id": lead_id}).execute()
                    except Exception:
                        pass

            except Exception as e:
                logger.error(f"Scheduled broadcast send failed for {phone}: {e}")
                failed += 1
                recipient_rows.append({
                    "tenant_id": tenant_id,
                    "broadcast_id": broadcast_id,
                    "lead_id": lead_id,
                    "phone": phone,
                    "name": lead_name,
                    "send_status": "failed",
                    "tag_id": tag_id,
                    "fail_detail": _meta_error_detail(str(e)),
                })

        # Persist broadcast_recipients
        if recipient_rows:
            for i in range(0, len(recipient_rows), 100):
                batch = recipient_rows[i:i+100]
                try:
                    db.table("broadcast_recipients").insert(batch).execute()
                except Exception as br_err:
                    logger.error(f"broadcast_recipients insert failed: {br_err}")

        # Freeze previous un-finalized broadcast_lead_scores rows (per-lead freeze).
        # Each broadcast starts its own scoring slate at the tenant's Cold floor;
        # this intentionally does not modify the lead's global score or segment.
        sent_at = datetime.now(timezone.utc).isoformat()
        sent_lead_ids_for_bls = [
            r["lead_id"] for r in recipient_rows
            if r.get("send_status") == "sent" and r.get("lead_id")
        ]

        # Freeze previous un-finalized rows for these leads
        if sent_lead_ids_for_bls:
            try:
                for i in range(0, len(sent_lead_ids_for_bls), 100):
                    batch_ids = sent_lead_ids_for_bls[i:i+100]
                    db.table("broadcast_lead_scores").update(
                        {"finalized_at": sent_at}
                    ).in_("lead_id", batch_ids).is_("finalized_at", "null").neq("broadcast_id", str(broadcast_id)).execute()
            except Exception as frz_err:
                logger.warning(f"broadcast_lead_scores freeze failed: {frz_err}")

        initial_score, initial_segment = new_lead_score_and_segment(tenant_id)
        bls_rows = [
            {
                "tenant_id": tenant_id,
                "broadcast_id": broadcast_id,
                "lead_id": r["lead_id"],
                "tag_id": tag_id,
                "score": initial_score,
                "segment": initial_segment,
                "arc_score": initial_score,
                "arc_message_count": 0,
                "broadcast_sent_at": sent_at,
            }
            for r in recipient_rows
            if r.get("send_status") == "sent" and r.get("lead_id")
        ]
        if bls_rows:
            for i in range(0, len(bls_rows), 100):
                try:
                    db.table("broadcast_lead_scores").upsert(
                        bls_rows[i:i+100],
                        on_conflict="broadcast_id,lead_id",
                    ).execute()
                except Exception as bls_err:
                    logger.error(f"broadcast_lead_scores seed failed: {bls_err}")

        # Increment broadcast_count in lead_tag_interest for each successfully sent lead
        if tag_id and bls_rows:
            sent_lead_ids = [r["lead_id"] for r in bls_rows]
            try:
                existing_lti = (
                    db.table("lead_tag_interest")
                    .select("lead_id,broadcast_count")
                    .eq("tenant_id", tenant_id)
                    .eq("tag_id", tag_id)
                    .in_("lead_id", sent_lead_ids)
                    .execute().data or []
                )
                existing_counts = {r["lead_id"]: r.get("broadcast_count") or 0 for r in existing_lti}
                lti_rows = [
                    {
                        "tenant_id": tenant_id,
                        "lead_id": lid,
                        "tag_id": tag_id,
                        "broadcast_count": existing_counts.get(lid, 0) + 1,
                    }
                    for lid in sent_lead_ids
                ]
                for i in range(0, len(lti_rows), 100):
                    db.table("lead_tag_interest").upsert(
                        lti_rows[i:i+100],
                        on_conflict="tenant_id,lead_id,tag_id",
                    ).execute()
            except Exception as lti_err:
                logger.warning(f"lead_tag_interest broadcast_count update failed: {lti_err}")

        if sent > 0:
            await increment_send_count(best_number["id"], delta=sent)

        result = {"sent": sent, "failed": failed, "broadcast_id": broadcast_id}
        _finish(db, row_id, "done", result)
        logger.info(f"Scheduled broadcast {row_id}: sent={sent} failed={failed}")
        return result

    except Exception as exc:
        logger.error(f"Scheduled broadcast {row_id} failed: {exc}")
        _finish(db, row_id, "failed", None, error=str(exc))
        return {"sent": 0, "failed": 0, "error": str(exc)}


def _finish(db, row_id: str, status: str, result: dict | None, error: str | None = None) -> None:
    update: dict = {
        "status": status,
        "executed_at": datetime.now(timezone.utc).isoformat(),
    }
    if result is not None:
        update["result"] = json.dumps(result)
    if error:
        update["error"] = error
    db.table("scheduled_broadcasts").update(update).eq("id", row_id).execute()
