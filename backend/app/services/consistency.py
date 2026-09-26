"""One story for Aira: find where the Description, knowledge files, products and handover
line disagree with the Services page (packages, prices, details to collect), and propose a
fix for each.

Why: Aira reads every source before each reply. When the Description says "starts from
₹29, buy in the app, never ask for date of birth" while the Services page sells ₹49 and ₹99
in chat and needs the date of birth, the model has to pick a side on every message. The reply
path already settles it (deal_engine's SOURCE OF TRUTH rule and the price guard), but the
client should see and fix the contradiction, not rely on the tie-break.

Two layers:
- deterministic checks that cannot be argued with: a rupee figure the business does not
  charge, "never ask for X" when X is a required detail, a handover line that sends people
  elsewhere;
- one model pass for the rest (e.g. "everything happens in the app"), kept only when the
  quoted text really is in the source it names and the proposed fix adds no new number or link.

The Services page is always the side that wins; a fix edits the other source. Nothing is
changed until the client accepts a fix (apply_fix).
"""
import hashlib
import json
import logging
import re
from datetime import datetime, timezone

from app.config_dynamic import get_setting, invalidate_cache, save_setting
from app.services import deal_engine
from app.services.description_diff import lines_of, normalize
from app.services.knowledge_sections import unverified_tokens

logger = logging.getLogger(__name__)

REPORT_KEY = "consistency_report"
TRUTH = "Services page"
_PURPOSE = "consistency_check"
_DOC_TEXT_BUDGET = 24_000
_LINE_MAX = 1_000
_SENTENCE_SPLIT_RE = re.compile(r"(?<=[.!?])\s+")

_NEVER_ASK_RE = re.compile(
    r"\b(never|don'?t|do not|must not|should not|no need to)\b[^.\n]{0,40}\b(ask|request|collect|take|get)\b",
    re.IGNORECASE,
)
# What a customer is told to do instead of talking to the team in this chat.
_ELSEWHERE_RE = re.compile(
    r"\b(app|support option|support team|helpdesk|help desk|website|email|e-mail|call us|call)\b|\d{7,}",
    re.IGNORECASE,
)
_FIELD_SYNONYMS = (
    ("date of birth", "dob", "birth date", "birthday"),
    ("time of birth", "tob", "birth time"),
    ("place of birth", "pob", "birth place", "birthplace"),
)


# ─── Sources ──────────────────────────────────────────────────────────────────

def gather(db, tenant_id: str) -> dict:
    """Everything Aira reads about what this business sells."""
    from app.services import intake

    config = intake.get_intake_config(tenant_id, db=db)
    catalog = (
        db.table("catalog_items").select("name,price_paise").eq("tenant_id", tenant_id).eq("status", "ready").execute()
    ).data or []
    return {
        "description": (get_setting("business_description", tenant_id=tenant_id) or "").strip(),
        "handover_line": (get_setting("handover_line", tenant_id=tenant_id) or "").strip(),
        "config": config,
        "selling": deal_engine.is_enabled(config),
        "catalog": catalog,
        "documents": _documents(db, tenant_id),
    }


def _documents(db, tenant_id: str) -> list[dict]:
    """name, id, text Aira looks up, and whether it is sorted (only sorted facts are editable)."""
    rows = (
        db.table("knowledge_documents").select("id,name,full_text,sorted_at,status")
        .eq("tenant_id", tenant_id).eq("status", "indexed").execute()
    ).data or []
    docs, budget = [], _DOC_TEXT_BUDGET
    for row in rows:
        text = (row.get("full_text") or "").strip() if row.get("sorted_at") else _chunk_text(db, tenant_id, row["id"])
        if not text or len(text) > budget:
            continue
        budget -= len(text)
        docs.append({"id": row["id"], "name": row["name"], "text": text, "editable": bool(row.get("sorted_at"))})
    return docs


def _chunk_text(db, tenant_id: str, document_id: str) -> str:
    """A file uploaded before auto-sort is served from its chunks, not full_text."""
    rows = (
        db.table("knowledge_chunks").select("content,chunk_index")
        .eq("tenant_id", tenant_id).eq("document_id", document_id).order("chunk_index").execute()
    ).data or []
    return "\n".join((r.get("content") or "").strip() for r in rows).strip()


def fingerprint(src: dict) -> str:
    payload = json.dumps(
        [src["description"], src["handover_line"], src["config"], src["catalog"],
         [(d["id"], d["text"]) for d in src["documents"]]],
        sort_keys=True, default=str, ensure_ascii=False,
    )
    return hashlib.sha256(payload.encode()).hexdigest()


def _truth_prices(src: dict) -> set[float]:
    prices = deal_engine.allowed_prices(src["config"]) if src["selling"] else set()
    return prices | {(c.get("price_paise") or 0) / 100 for c in src["catalog"] if c.get("price_paise")}


def _rupees(value: float) -> str:
    return f"₹{int(value)}" if value == int(value) else f"₹{value:.2f}"


def services_summary(src: dict) -> str:
    """The Services page in words, for the model and for the client-facing 'truth' text."""
    lines = []
    if src["selling"]:
        from app.services import intake
        for leaf in deal_engine._leaves(intake.normalize_packages(src["config"])):
            lines.append(f"- {leaf['name']}: {_rupees(leaf['amount_paise'] / 100)}, sold and paid for in this chat")
        fields = src["config"].get("fields") or []
        if fields:
            lines.append("- Details collected before payment: " + ", ".join(f["label"] for f in fields))
    for item in src["catalog"]:
        if item.get("price_paise"):
            lines.append(f"- Product {item['name']}: {_rupees(item['price_paise'] / 100)}")
    return "\n".join(lines)


# ─── Deterministic checks ─────────────────────────────────────────────────────

def _sources(src: dict):
    """(where, document id, document name, editable, text) for every text Aira reads."""
    yield "description", None, None, True, src["description"]
    for doc in src["documents"]:
        yield "knowledge", doc["id"], doc["name"], doc["editable"], doc["text"]


def _sentences(text: str):
    """Each sentence of each line: a Description line can be a whole paragraph, and a fix
    should change the one sentence that is wrong, not rewrite the paragraph."""
    for line in lines_of(text):
        for sentence in _SENTENCE_SPLIT_RE.split(line.strip()):
            if sentence.strip():
                yield sentence.strip()


def _issue(kind: str, where: str, doc_id, doc_name, editable: bool, line: str, topic: str, truth: str) -> dict:
    return {
        "kind": kind, "where": where, "document_id": doc_id, "document_name": doc_name,
        "editable": editable, "quote": line.strip()[:_LINE_MAX], "topic": topic, "truth": truth,
        "proposed": None,
    }


def price_issues(src: dict) -> list[dict]:
    allowed = _truth_prices(src)
    if not allowed:
        return []
    out = []
    for where, doc_id, name, editable, text in _sources(src):
        for line in _sentences(text):
            found = {deal_engine._to_float(a) for a in deal_engine._AMOUNT_BEFORE_RE.findall(line)}
            found |= {deal_engine._to_float(a) for a in deal_engine._AMOUNT_AFTER_RE.findall(line)}
            unknown = sorted(found - allowed)
            if unknown:
                figures = ", ".join(_rupees(v) for v in unknown)
                out.append(_issue(
                    "price", where, doc_id, name, editable, line, f"Price {figures} is not on your {TRUTH}",
                    "Prices on your Services page: " + ", ".join(_rupees(v) for v in sorted(allowed)[:8]),
                ))
    return out


def _field_terms(field: dict) -> tuple[str, ...]:
    """The words a description would use for this detail: its label, its key, and the
    common short forms when it is a birth detail ("DOB" for "Date of birth")."""
    label = (field.get("label") or "").strip().lower()
    terms = {label, (field.get("key") or "").replace("_", " ").strip().lower()}
    for group in _FIELD_SYNONYMS:
        if any(word in label for word in group):
            terms |= set(group)
    return tuple(t for t in terms if len(t) >= 3)


def never_ask_issues(src: dict) -> list[dict]:
    fields = (src["config"].get("fields") or []) if src["selling"] else []
    out = []
    for field in fields:
        terms = _field_terms(field)
        pattern = re.compile(r"\b(" + "|".join(re.escape(t) for t in terms) + r")\b", re.IGNORECASE)
        for where, doc_id, name, editable, text in _sources(src):
            for line in _sentences(text):
                if _NEVER_ASK_RE.search(line) and pattern.search(line):
                    out.append(_issue(
                        "required_detail", where, doc_id, name, editable, line,
                        f"Says not to ask for {field['label']}, but your {TRUTH} needs it before payment",
                        f"{field['label']} is collected before the payment link is sent",
                    ))
    return out


def handover_issues(src: dict) -> list[dict]:
    line = src["handover_line"]
    if not line or not _ELSEWHERE_RE.search(line):
        return []
    issue = _issue(
        "handover", "handover_line", None, None, True, line,
        "Your handover line sends customers elsewhere, but Aira alerts your team to reply in this chat",
        "When Aira brings a person in, your team is alerted in the inbox and replies here",
    )
    return [issue]


def deterministic_issues(src: dict) -> list[dict]:
    return price_issues(src) + never_ask_issues(src) + handover_issues(src)


# ─── Model pass ───────────────────────────────────────────────────────────────

_SYSTEM = """You check a business's WhatsApp assistant setup for contradictions with its SERVICES PAGE.

The SERVICES PAGE is the truth: what is sold and paid for right in this chat, the prices, the details collected before payment, and that a person on the team replies in this chat when the assistant brings one in.

Find lines in the DESCRIPTION, the KNOWLEDGE files and the HANDOVER LINE that contradict it, for example: a different price, telling customers to buy or pay somewhere else for something sold in this chat, saying not to ask for a detail the Services page collects, sending customers elsewhere to reach a person. Report only real contradictions, not missing information. Also report every FLAGGED line you are given.

For each, copy the contradicting line EXACTLY as written into "quote", and write "proposed": that same line rewritten to agree with the Services page, keeping its language, tone and everything else it says; "" when the whole line should simply be removed. Never add a price, number or link that is not on the Services page or in the line itself.

Reply with only JSON:
{"issues": [{"where": "description" | "knowledge" | "handover_line", "document_name": "file name or null", "quote": "exact line", "topic": "short, plain words", "proposed": "rewritten line or \\"\\""}]}"""


def _user_prompt(src: dict, flagged: list[dict]) -> str:
    parts = [f"SERVICES PAGE:\n{services_summary(src) or '(nothing configured)'}"]
    parts.append(f"DESCRIPTION:\n{src['description'] or '(empty)'}")
    for doc in src["documents"]:
        parts.append(f"KNOWLEDGE <<{doc['name']}>>:\n{doc['text']}")
    parts.append(f"HANDOVER LINE:\n{src['handover_line'] or '(none)'}")
    if flagged:
        parts.append("FLAGGED (must be in your answer, with a proposed fix):\n" + "\n".join(
            f"- [{i['where']}{' ' + i['document_name'] if i['document_name'] else ''}] {i['quote']}" for i in flagged
        ))
    return "\n\n".join(parts)


def _source_text(src: dict, where: str, document_name: str | None) -> tuple[str | None, dict | None]:
    if where == "description":
        return src["description"], None
    if where == "handover_line":
        return src["handover_line"], None
    for doc in src["documents"]:
        if doc["name"] == document_name:
            return doc["text"], doc
    return None, None


def _line_in(text: str, quote: str) -> str | None:
    """The quote as it stands in the source: the sentence or line it copies, whitespace aside."""
    target = normalize(quote)
    if not target:
        return None
    for sentence in _sentences(text):
        if normalize(sentence) == target:
            return sentence
    for line in lines_of(text):
        if normalize(line) == target or target in normalize(line):
            return quote.strip() if quote.strip() in line else line.strip()
    return None


def validate_model_issues(items, src: dict) -> list[dict]:
    """Keep only issues whose quote really is in the named source, and drop a proposed fix
    that brings in a number or link found in neither the line nor the Services page."""
    truth = services_summary(src)
    out = []
    for item in items or []:
        if not isinstance(item, dict):
            continue
        where = str(item.get("where") or "").strip().lower()
        if where not in ("description", "knowledge", "handover_line"):
            continue
        name = item.get("document_name") if where == "knowledge" else None
        text, doc = _source_text(src, where, name)
        line = _line_in(text or "", str(item.get("quote") or ""))
        if not line:
            continue
        proposed: str | None = str(item.get("proposed") or "").strip()
        if normalize(proposed) == normalize(line) or unverified_tokens(proposed, line, truth):
            proposed = None  # no real change, or it brings in a figure from nowhere
        issue = _issue(
            "other", where, doc["id"] if doc else None, name, doc["editable"] if doc else True,
            line, str(item.get("topic") or "Disagrees with your Services page").strip()[:160],
            "What your Services page says wins",
        )
        issue["proposed"] = proposed
        out.append(issue)
    return out


async def _model_issues(src: dict, flagged: list[dict], tenant_id: str) -> list[dict]:
    from app.services.knowledge_sort import KnowledgeError, _llm_json

    if not (src["selling"] or src["catalog"]):
        return []
    try:
        data = await _llm_json(_SYSTEM, _user_prompt(src, flagged), tenant_id=tenant_id, max_tokens=2_500)
    except KnowledgeError as e:
        logger.warning("consistency: model pass skipped for tenant %s: %s", tenant_id, e)
        return []
    except Exception:
        logger.exception("consistency: model pass failed for tenant %s", tenant_id)
        return []
    return validate_model_issues(data.get("issues"), src)


# ─── Report ───────────────────────────────────────────────────────────────────

def issue_key(issue: dict) -> str:
    raw = f"{issue['where']}|{issue.get('document_id') or ''}|{normalize(issue['quote'])}"
    return hashlib.sha1(raw.encode()).hexdigest()[:16]


def merge(deterministic: list[dict], model: list[dict]) -> list[dict]:
    """One issue per source line. A deterministic finding keeps its precise topic and takes
    the model's proposed rewrite of the same line."""
    by_key: dict[str, dict] = {}
    for issue in deterministic:
        by_key.setdefault(issue_key(issue), dict(issue))
    for issue in model:
        key = issue_key(issue)
        if key in by_key:
            if by_key[key].get("proposed") is None and issue.get("proposed") is not None:
                by_key[key]["proposed"] = issue["proposed"]
        else:
            by_key[key] = dict(issue)
    return [{**issue, "id": key} for key, issue in by_key.items()]


def load_report(tenant_id: str) -> dict:
    raw = get_setting(REPORT_KEY, tenant_id=tenant_id)
    try:
        data = json.loads(raw) if raw else {}
    except (ValueError, TypeError):
        data = {}
    return data if isinstance(data, dict) else {}


def _save_report(tenant_id: str, report: dict) -> None:
    save_setting(REPORT_KEY, json.dumps(report, ensure_ascii=False), tenant_id=tenant_id)
    invalidate_cache(REPORT_KEY)


def visible(report: dict) -> dict:
    dismissed = set(report.get("dismissed") or [])
    issues = [i for i in report.get("issues") or [] if i["id"] not in dismissed]
    return {**report, "issues": issues}


async def run_check(db, tenant_id: str) -> dict:
    """Recompute and store the report. Never raises for a model failure: the deterministic
    findings are still reported."""
    src = gather(db, tenant_id)
    found = deterministic_issues(src)
    issues = merge(found, await _model_issues(src, found, tenant_id))
    previous = load_report(tenant_id)
    report = {
        "issues": issues,
        "dismissed": [k for k in previous.get("dismissed") or [] if any(i["id"] == k for i in issues)],
        "fingerprint": fingerprint(src),
        "checked_at": datetime.now(timezone.utc).isoformat(),
    }
    _save_report(tenant_id, report)
    return visible(report)


async def run_check_safely(tenant_id: str) -> None:
    """Background entry point after a save: a failed check must never fail the save."""
    from app.db.supabase import get_supabase

    try:
        await run_check(get_supabase(), tenant_id)
    except Exception:
        logger.exception("consistency: background check failed for tenant %s", tenant_id)


def current_report(db, tenant_id: str) -> dict:
    report = visible(load_report(tenant_id))
    if not report.get("fingerprint"):
        return {"issues": [], "checked_at": None, "stale": True}
    stale = report["fingerprint"] != fingerprint(gather(db, tenant_id))
    return {"issues": report["issues"], "checked_at": report.get("checked_at"), "stale": stale}


def dismiss(tenant_id: str, issue_id: str) -> None:
    report = load_report(tenant_id)
    dismissed = list(dict.fromkeys([*(report.get("dismissed") or []), issue_id]))
    _save_report(tenant_id, {**report, "dismissed": dismissed})


class FixError(Exception):
    def __init__(self, message: str, status: int = 400):
        super().__init__(message)
        self.status = status


def _replace_line(text: str, quote: str, proposed: str) -> str:
    """Replace the quoted sentence (or whole line) where it stands; an empty proposal removes it."""
    quote = quote.strip()
    lines = text.split("\n")
    for i, current in enumerate(lines):
        if quote and quote in current:
            replaced = current.replace(quote, proposed, 1)
            indent = replaced[: len(replaced) - len(replaced.lstrip())]
            body = re.sub(r"[ \t]{2,}", " ", replaced.strip())
            if body:
                lines[i] = indent + body
            else:
                lines.pop(i)
            return re.sub(r"\n{3,}", "\n\n", "\n".join(lines)).strip()
        if normalize(current) == normalize(quote):
            if proposed:
                lines[i] = current.replace(current.strip(), proposed)
            else:
                lines.pop(i)
            return re.sub(r"\n{3,}", "\n\n", "\n".join(lines)).strip()
    raise FixError("That text has changed since Aira checked. Check again to see the latest.", 409)


def apply_fix(db, tenant_id: str, issue_id: str, *, user_id: str | None, is_owner: bool, text: str | None = None) -> dict:
    """Apply the proposed (or the client's own edited) wording for one issue. The Services
    page is never changed here; the other source is."""
    from app.services import knowledge_sort as ks
    from app.services import knowledge_versions as kv

    report = load_report(tenant_id)
    issue = next((i for i in report.get("issues") or [] if i["id"] == issue_id), None)
    if not issue:
        raise FixError("Aira no longer sees this problem. Check again.", 404)
    proposed = (text if text is not None else issue.get("proposed"))
    if proposed is None:
        raise FixError("There is no suggested wording for this one. Type your own, or edit the source.")
    proposed = proposed.strip()
    if proposed and unverified_tokens(proposed, issue["quote"], services_summary(gather(db, tenant_id))):
        raise FixError("The new wording has a price, number or link that isn't on your Services page.")

    if issue["where"] == "description":
        if not is_owner:
            raise FixError("Only an account owner can change the Description.", 403)
        current = kv.current_description(tenant_id)
        new_text = _replace_line(current, issue["quote"], proposed)
        kv.save_description(db, tenant_id, new_text, "consistency_fix", user_id)
        result = {"where": "description", "description": new_text}
    elif issue["where"] == "handover_line":
        save_setting("handover_line", proposed, tenant_id=tenant_id)
        invalidate_cache("handover_line")
        result = {"where": "handover_line"}
    else:
        if not issue.get("editable"):
            raise FixError("This file was uploaded before auto-sort. Re-sort it on the Knowledge page, then fix it there.")
        doc = next((d for d in _documents(db, tenant_id) if d["id"] == issue["document_id"]), None)
        if not doc:
            raise FixError("That file is gone. Check again.", 404)
        facts = ks.update_facts(db, tenant_id, doc["id"], _replace_line(doc["text"], issue["quote"], proposed), user_id)
        result = {"where": "knowledge", "document_id": doc["id"], **facts}
    remaining = [i for i in report.get("issues") or [] if i["id"] != issue_id]
    _save_report(tenant_id, {**report, "issues": remaining})
    return {"applied": issue_id, **result}

