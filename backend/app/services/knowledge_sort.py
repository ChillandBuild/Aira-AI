"""Knowledge Auto-Sort -- spec: docs/superpowers/specs/2026-09-18-knowledge-auto-sort-design.md

An uploaded document is cut into sections and each section is labelled RULE, FACT,
MIXED or JUNK by the tenant's own AI model. Rules are merged into a proposed
Description, facts are kept WORD FOR WORD for RAG, junk is left out. The result is
parked as a pending knowledge_reviews row; nothing reaches replies until the client
approves it through apply_review().

Why full_text must become facts-only: when retrieval matches nothing,
knowledge_service._full_text_context injects every indexed document's full_text. A raw
rulebook left there would come back into the prompt, labelled as facts, on every miss."""
import json
import logging
import re
from dataclasses import dataclass, field
from datetime import datetime, timezone

from app.db.supabase import get_supabase
from app.services import knowledge_versions as versions
from app.services.description_diff import (
    apply_hunks,
    client_lines,
    closest_line,
    diff_hunks,
    insert_under_heading,
    lines_of,
    normalize,
    normalize_text,
    remove_lines,
    replace_exact_line,
)
from app.services.knowledge_sections import Section, critical_tokens, split_sections, unverified_tokens, verify_fact

logger = logging.getLogger(__name__)

SOFT_WORD_LIMIT = 1_200
_PURPOSE = "knowledge_sort"
_LABEL_BATCH_CHARS = 12_000
_COMPILE_BATCH_CHARS = 16_000
_OTHER_FACTS_BUDGET_CHARS = 20_000
_PREVIEW_CHARS = 600
_LABELS = {"RULE", "FACT", "MIXED", "JUNK"}

NO_MODEL_MESSAGE = "Aira couldn't sort this file because no AI model is set up for your account."


# ─── Errors (routes map .status to the HTTP status; str(e) is the plain-language detail) ──

class KnowledgeError(Exception):
    status = 400
    message = "Something went wrong."

    def __init__(self, message: str | None = None):
        super().__init__(message or self.message)


class SortError(KnowledgeError):
    message = "Aira couldn't sort this file. Try Re-sort."


class NotFoundError(KnowledgeError):
    status = 404
    message = "Not found."


class StaleError(KnowledgeError):
    status = 409
    message = "Your Description changed since this was prepared. Re-sort to see the latest."


class EmptyDescriptionError(KnowledgeError):
    status = 422
    message = (
        "This would leave your Description empty, so Aira still wouldn't know who it is. "
        "Write a short Description first, or upload a file that describes your business."
    )


class OwnerRequiredError(KnowledgeError):
    status = 403
    message = "Only an account owner can change the Description."


# ─── Model calls ──────────────────────────────────────────────────────────────

def _parse_json(raw: str | None) -> dict:
    text = (raw or "").strip()
    text = re.sub(r"^```(?:json)?\s*|\s*```$", "", text, flags=re.IGNORECASE)
    start, end = text.find("{"), text.rfind("}")
    if start == -1 or end <= start:
        raise ValueError("no JSON object in model output")
    data = json.loads(text[start:end + 1])
    if not isinstance(data, dict):
        raise ValueError("model output is not a JSON object")
    return data


async def _llm_json(system: str, user: str, *, tenant_id: str, max_tokens: int) -> dict:
    """Call the tenant's own reply model and parse a JSON object, retrying once on a
    parse failure. Every provider is reached through _llm_chat so its per-provider
    quirks (Gemini thinking level, GPT-5 reasoning params) are already handled."""
    from app.services.ai_reply import _llm_chat

    messages = [{"role": "system", "content": system}, {"role": "user", "content": user}]
    for attempt in range(2):
        try:
            raw = await _llm_chat(
                messages, max_tokens=max_tokens, tenant_id=tenant_id, purpose=_PURPOSE, temperature=0.1
            )
        except RuntimeError as e:
            if "not configured" in str(e):
                raise SortError(NO_MODEL_MESSAGE) from e
            raise
        try:
            return _parse_json(raw)
        except (ValueError, json.JSONDecodeError) as e:
            logger.warning(f"knowledge_sort: unparseable model output (attempt {attempt + 1}) for tenant {tenant_id}: {e}")
            messages = messages + [
                {"role": "assistant", "content": raw or ""},
                {"role": "user", "content": "That was not valid JSON. Reply again with only the JSON object."},
            ]
    raise SortError("Aira couldn't read the sorting result. Try Re-sort.")


_LABEL_SYSTEM = """You sort a business's uploaded document for its WhatsApp sales assistant.

Each section is marked <<s1>>, <<s2>>, ... Label every section with exactly one of:
- RULE: tells the assistant how to behave -- tone, language, spelling, greetings, closings, what never to say, conversation flows, when to recommend something, reply length, example replies.
- FACT: something a customer could ask about -- prices, packages, features, policies, FAQs, addresses, timings, links.
- MIXED: contains both rules and facts.
- JUNK: not meant for the assistant -- a pasted chat with an AI ("I agree", "I'd replace this section with"), editor notes, placeholders like "attach the link", or a repeat of an earlier section.

For a MIXED section, "facts" lists the fact sentences COPIED EXACTLY from the section. Never reword, translate, summarise or combine them. Never change a number, price or link. For every other label, "facts" is [].

Reply with only JSON:
{"sections": [{"id": "s1", "label": "RULE", "facts": [], "note": "one short reason"}]}"""


_COMPILE_SYSTEM = """You maintain the always-on instructions ("Description") for a business's WhatsApp sales assistant. The assistant re-reads the whole Description before every reply, so it must be short, clear and free of contradictions.

You get the CURRENT DESCRIPTION and NEW RULES taken from an uploaded document. Produce the updated Description.

How to write it:
- Keep every line of the current Description word for word, unless a new rule contradicts it.
- Merge the new rules in as short plain lines under UPPERCASE headings, in this order, using only the ones you need: ABOUT US, WHAT WE OFFER, WHO WE TALK TO, YOUR JOB IN EVERY CONVERSATION, LANGUAGE, HOW TO SOUND, GREETINGS AND CLOSINGS, WHAT YOU MUST NEVER DO, HAND OVER TO A PERSON WHEN. Headings already in the current Description stay as they are.
- When one new rule says it overrides or replaces another, keep only the winning one.
- Write each rule once. Drop example conversations unless one exact phrase must be used word for word.
- Do not copy prices, packages, FAQs or policies into the Description -- they are looked up separately -- unless they are already in the current Description.
- No markdown: no #, no **, no >, no tables. Plain lines; "- " bullets are fine.
- At most 1,200 words.

Conflicts: when the new rules disagree with the current Description, or with each other, and you cannot tell which is right, put NEITHER version in the Description and list it in "conflicts".

Reply with only JSON:
{"description": "the full updated Description", "conflicts": [{"topic": "short", "heading": "HEADING IT BELONGS UNDER", "option_a": "one line", "source_a": "current Description or this file", "option_b": "one line", "source_b": "this file"}]}"""


_DISAGREE_SYSTEM = """You check whether newly uploaded facts disagree with what a business's assistant already knows -- for example a different price, a different number of free questions, a different link.

You get NEW FACTS, the CURRENT DESCRIPTION, and OTHER FILES (each marked <<file name>>). Report only real disagreements about the same thing. Do not report things that are merely missing.

For a disagreement with the Description, copy the Description's exact line into "existing_line" and write "proposed_line": that same line with only the disagreeing value changed to the new one.

Reply with only JSON:
{"disagreements": [{"where": "description or file", "document_name": "file name, or null for the description", "topic": "short", "new_value": "as written in the new facts", "existing_value": "as written in the existing text", "existing_line": "description only", "proposed_line": "description only"}]}"""


# ─── Labelling and bucketing ──────────────────────────────────────────────────

@dataclass
class Label:
    label: str
    facts: list[str]
    note: str


@dataclass
class Buckets:
    facts: list[str] = field(default_factory=list)
    rules: list[str] = field(default_factory=list)
    unverified: list[str] = field(default_factory=list)
    left_out: list[dict] = field(default_factory=list)


def _batches(texts: list, limit: int, size=len):
    batch, used = [], 0
    for item in texts:
        n = size(item)
        if batch and used + n > limit:
            yield batch
            batch, used = [], 0
        batch.append(item)
        used += n
    if batch:
        yield batch


async def label_sections(tenant_id: str, sections: list[Section]) -> dict[str, Label]:
    labels: dict[str, Label] = {}
    for batch in _batches(sections, _LABEL_BATCH_CHARS, size=lambda s: len(s.text)):
        user = "\n\n".join(f"<<{s.id}>>\n{s.text}" for s in batch)
        data = await _llm_json(_LABEL_SYSTEM, user, tenant_id=tenant_id, max_tokens=2_500)
        ids = {s.id for s in batch}
        for item in data.get("sections") or []:
            if not isinstance(item, dict):
                continue
            sid = str(item.get("id") or "").strip()
            label = str(item.get("label") or "").strip().upper()
            if sid not in ids or label not in _LABELS:
                continue
            facts = [str(f).strip() for f in (item.get("facts") or []) if str(f).strip()] if label == "MIXED" else []
            labels[sid] = Label(label=label, facts=facts, note=str(item.get("note") or "")[:200])
    return labels


def bucket_sections(sections: list[Section], labels: dict[str, Label]) -> Buckets:
    """FACT sections go to RAG verbatim. MIXED sections feed the rules, and their copied
    facts go to RAG only if every number/link in them is in the section (spec §4.3).
    A section the model skipped is left out rather than guessed -- guessing FACT would
    put rules back into retrieval."""
    b = Buckets()
    for s in sections:
        lab = labels.get(s.id)
        if lab is None:
            b.left_out.append({"text": s.text[:_PREVIEW_CHARS], "note": "Aira couldn't tell what this part is, so it was left out."})
        elif lab.label == "FACT":
            b.facts.append(s.text)
        elif lab.label == "RULE":
            b.rules.append(s.text)
        elif lab.label == "MIXED":
            b.rules.append(s.text)
            for fact in lab.facts:
                (b.facts if verify_fact(fact, s.text) else b.unverified).append(fact)
        else:
            b.left_out.append({"text": s.text[:_PREVIEW_CHARS], "note": lab.note or "Not meant for Aira."})
    return b


# ─── Compiling the Description ────────────────────────────────────────────────

def _clean_conflicts(items, start: int) -> list[dict]:
    out: list[dict] = []
    for item in items or []:
        if not isinstance(item, dict):
            continue
        a = str(item.get("option_a") or "").strip()
        b = str(item.get("option_b") or "").strip()
        if not a or not b or normalize(a) == normalize(b):
            continue
        out.append({
            "id": f"c{start + len(out) + 1}",
            "topic": str(item.get("topic") or "").strip()[:120],
            "heading": normalize(str(item.get("heading") or "")).upper()[:60],
            "option_a": a[:500],
            "source_a": str(item.get("source_a") or "").strip()[:80],
            "option_b": b[:500],
            "source_b": str(item.get("source_b") or "").strip()[:80],
        })
    return out


async def compile_description(tenant_id: str, current: str, rules: list[str]) -> tuple[str, list[dict]]:
    """Fold the rules into the Description batch by batch, so a very long rulebook never
    has to fit one request. Each round's output is the next round's CURRENT."""
    description = current
    conflicts: list[dict] = []
    for batch in _batches(rules, _COMPILE_BATCH_CHARS):
        user = (
            f"CURRENT DESCRIPTION:\n{description.strip() or '(empty)'}\n\n"
            "NEW RULES:\n" + "\n\n---\n\n".join(batch)
        )
        data = await _llm_json(_COMPILE_SYSTEM, user, tenant_id=tenant_id, max_tokens=3_000)
        proposed = str(data.get("description") or "").strip()
        if proposed:
            description = proposed
        conflicts += _clean_conflicts(data.get("conflicts"), start=len(conflicts))
    return description, conflicts


# ─── Price and fact disagreements (spec §6.5) ─────────────────────────────────

def validate_disagreements(
    items,
    *,
    new_facts: str,
    description: str,
    other_docs: dict[str, str],
    client_line_set: set[str],
) -> list[dict]:
    """Keep only disagreements whose quoted values really are in the texts they claim
    to come from -- a made-up conflict must never reach the client."""
    desc_lines = {normalize(line): line for line in lines_of(description) if normalize(line)}
    out: list[dict] = []
    for item in items or []:
        if not isinstance(item, dict):
            continue
        new_value = str(item.get("new_value") or "").strip()
        existing_value = str(item.get("existing_value") or "").strip()
        new_tokens, old_tokens = critical_tokens(new_value), critical_tokens(existing_value)
        if not new_tokens or new_tokens == old_tokens or unverified_tokens(new_value, new_facts):
            continue
        base = {
            "id": f"d{len(out) + 1}",
            "topic": str(item.get("topic") or "").strip()[:120],
            "new_value": new_value[:200],
            "existing_value": existing_value[:200],
        }
        where = str(item.get("where") or "").strip().lower()
        if where == "description":
            existing_line = desc_lines.get(normalize(str(item.get("existing_line") or "")))
            proposed_line = str(item.get("proposed_line") or "").strip()
            if not existing_line or not proposed_line or normalize(proposed_line) == normalize(existing_line):
                continue
            if unverified_tokens(existing_value, existing_line) or unverified_tokens(proposed_line, existing_line, new_facts):
                continue
            out.append({
                **base,
                "where": "description",
                "document_name": None,
                "existing_line": existing_line,
                "proposed_line": proposed_line,
                "client_line": normalize(existing_line) in client_line_set,
            })
        elif where == "file":
            name = str(item.get("document_name") or "").strip()
            source = other_docs.get(name)
            if source is None or unverified_tokens(existing_value, source):
                continue
            out.append({**base, "where": "file", "document_name": name, "existing_line": None, "proposed_line": None, "client_line": False})
    return out


def _disagree_user(new_facts: str, description: str, others: dict[str, str]) -> str:
    parts = [f"NEW FACTS:\n{new_facts}", f"CURRENT DESCRIPTION:\n{description.strip() or '(empty)'}"]
    if others:
        parts.append("OTHER FILES:\n" + "\n\n".join(f"<<{name}>>\n{text}" for name, text in others.items()))
    return "\n\n".join(parts)


# ─── Database helpers ─────────────────────────────────────────────────────────

def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _get_doc(db, tenant_id: str, document_id: str, columns: str = "*") -> dict | None:
    res = (
        db.table("knowledge_documents")
        .select(columns)
        .eq("id", str(document_id))
        .eq("tenant_id", tenant_id)
        .limit(1)
        .execute()
    )
    return (res.data or [None])[0]


def machine_lines(db, tenant_id: str, exclude: frozenset | set = frozenset()) -> set[str]:
    """Every Description line a sorted document claims (spec §6.1)."""
    rows = db.table("knowledge_documents").select("id,rule_lines").eq("tenant_id", tenant_id).execute().data or []
    out: set[str] = set()
    for row in rows:
        if row["id"] in exclude:
            continue
        out |= {normalize(line) for line in (row.get("rule_lines") or []) if normalize(line)}
    return out


def _doc_rule_lines(db, tenant_id: str, document_id: str | None) -> list[str]:
    if not document_id:
        return []
    doc = _get_doc(db, tenant_id, document_id, "id,rule_lines")
    return [normalize(line) for line in ((doc or {}).get("rule_lines") or []) if normalize(line)]


def _other_docs_facts(db, tenant_id: str, campaign_tag_id: str | None, exclude: set) -> dict[str, str]:
    """Facts of other SORTED documents a customer in this scope could also be served.
    Legacy documents are skipped: their full_text is the raw file, up to 50,000 chars."""
    rows = (
        db.table("knowledge_documents")
        .select("id,name,full_text,campaign_tag_id,sorted_at,status")
        .eq("tenant_id", tenant_id)
        .eq("status", "indexed")
        .execute()
        .data
        or []
    )
    out: dict[str, str] = {}
    budget = _OTHER_FACTS_BUDGET_CHARS
    for row in rows:
        text = (row.get("full_text") or "").strip()
        if row["id"] in exclude or not row.get("sorted_at") or not text:
            continue
        if campaign_tag_id and row.get("campaign_tag_id") not in (None, campaign_tag_id):
            continue
        if len(text) > budget:
            continue
        out[row["name"]] = text
        budget -= len(text)
    return out


def _pending_review(db, tenant_id: str, document_id: str) -> dict | None:
    res = (
        db.table("knowledge_reviews")
        .select("*")
        .eq("tenant_id", tenant_id)
        .eq("document_id", str(document_id))
        .eq("status", "pending")
        .order("created_at", desc=True)
        .limit(1)
        .execute()
    )
    return (res.data or [None])[0]


def _latest_review(db, tenant_id: str, document_id: str) -> dict | None:
    res = (
        db.table("knowledge_reviews")
        .select("*")
        .eq("tenant_id", tenant_id)
        .eq("document_id", str(document_id))
        .order("created_at", desc=True)
        .limit(1)
        .execute()
    )
    return (res.data or [None])[0]


# ─── Sorting ──────────────────────────────────────────────────────────────────

async def run_sort(
    db,
    *,
    tenant_id: str,
    document_id: str,
    source_text: str,
    truncated: bool,
    campaign_tag_id: str | None,
    replaces_document_id: str | None,
    origin: str,
    user_id: str | None,
) -> dict:
    """Sort one document and park the result as the document's pending review."""
    sections = split_sections(source_text)
    labels = await label_sections(tenant_id, sections)
    b = bucket_sections(sections, labels)

    # Campaign-scoped rules are left out: the Description applies to every campaign
    # (spec §4.5, decided 2026-09-18).
    rules, left_out_rules = b.rules, []
    if campaign_tag_id and b.rules:
        rules, left_out_rules = [], [r[:_PREVIEW_CHARS] for r in b.rules]

    base = versions.current_description_version(db, tenant_id)
    current = base.get("content") or ""
    compile_base = current
    if replaces_document_id:
        # Lines only the replaced file claimed are dropped before compiling; if the new
        # version still says them, the compile puts them back and the diff nets out.
        shared = machine_lines(db, tenant_id, exclude={replaces_document_id, document_id})
        compile_base = remove_lines(current, set(_doc_rule_lines(db, tenant_id, replaces_document_id)) - shared)

    if rules:
        proposed, conflicts = await compile_description(tenant_id, compile_base, rules)
    else:
        proposed, conflicts = compile_base, []

    facts_text = "\n\n".join(b.facts).strip()
    disagreements: list[dict] = []
    if facts_text:
        others = _other_docs_facts(db, tenant_id, campaign_tag_id, exclude={document_id, replaces_document_id})
        if current.strip() or others:
            data = await _llm_json(
                _DISAGREE_SYSTEM, _disagree_user(facts_text, current, others), tenant_id=tenant_id, max_tokens=1_500
            )
            disagreements = validate_disagreements(
                data.get("disagreements"),
                new_facts=facts_text,
                description=current,
                other_docs=others,
                client_line_set=client_lines(current, machine_lines(db, tenant_id)),
            )

    current_norm = {normalize(line) for line in lines_of(current)}
    proposed_rule_lines = list(dict.fromkeys(
        normalize(line) for line in lines_of(proposed) if normalize(line) and normalize(line) not in current_norm
    ))

    (
        db.table("knowledge_reviews")
        .update({"status": "discarded"})
        .eq("tenant_id", tenant_id)
        .eq("document_id", str(document_id))
        .eq("status", "pending")
        .execute()
    )
    return db.table("knowledge_reviews").insert({
        "tenant_id": tenant_id,
        "document_id": str(document_id),
        "base_version_id": base["id"],
        "proposed_description": proposed,
        "proposed_facts": facts_text,
        "proposed_rule_lines": proposed_rule_lines,
        "conflicts": conflicts,
        "fact_disagreements": disagreements,
        "unverified": b.unverified,
        "left_out": b.left_out,
        "left_out_rules": left_out_rules,
        "truncated": truncated,
        "replaces_document_id": replaces_document_id,
        "origin": origin,
        "status": "pending",
        "created_by": user_id,
    }).execute().data[0]


async def sort_document(*, tenant_id: str, document_id: str, user_id: str | None, replaces_document_id: str | None = None) -> None:
    """Background entry point for uploads and re-sorts. Never raises: a failure is
    written to the document as a plain-language message the client can act on.

    A document that is already live (status 'indexed', e.g. a legacy file being sorted
    for the first time) keeps serving replies throughout -- only sort_state changes."""
    from app.services.knowledge_service import _MAX_TEXT_CHARS

    db = get_supabase()
    doc = _get_doc(db, tenant_id, document_id, "id,status,source_text,campaign_tag_id")
    if not doc:
        return
    was_indexed = doc.get("status") == "indexed"
    if replaces_document_id is None and not was_indexed:
        # A re-sort of a not-yet-applied upload keeps the file it was replacing.
        replaces_document_id = (_latest_review(db, tenant_id, document_id) or {}).get("replaces_document_id")
    source = doc.get("source_text") or ""
    try:
        await run_sort(
            db,
            tenant_id=tenant_id,
            document_id=document_id,
            source_text=source,
            truncated=len(source) >= _MAX_TEXT_CHARS,
            campaign_tag_id=doc.get("campaign_tag_id"),
            replaces_document_id=replaces_document_id,
            origin="resort" if was_indexed else "upload",
            user_id=user_id,
        )
        updates = {"sort_state": "review", "error_message": None}
        if not was_indexed:
            updates["status"] = "review_pending"
    except Exception as e:
        if isinstance(e, SortError):
            message = str(e)
        else:
            logger.exception(f"knowledge_sort: sorting failed for document {document_id}")
            message = SortError.message
        updates = {"sort_state": "failed", "error_message": message}
        if not was_indexed:
            updates["status"] = "failed"
    db.table("knowledge_documents").update(updates).eq("id", document_id).eq("tenant_id", tenant_id).execute()


def prepare_resort(db, tenant_id: str, document_id: str) -> None:
    """Validate a re-sort request and mark the document as sorting. For a legacy
    document the raw text still lives in full_text, so it's copied to source_text."""
    doc = _get_doc(db, tenant_id, document_id, "id,status,sort_state,sorted_at,source_text,full_text")
    if not doc:
        raise NotFoundError("Document not found.")
    if doc.get("status") == "processing" or doc.get("sort_state") == "sorting":
        raise SortError("This file is already being sorted.")
    source = doc.get("source_text") or ("" if doc.get("sorted_at") else (doc.get("full_text") or ""))
    if not source.strip():
        raise SortError("There's no text to sort in this file. Upload it again.")
    updates = {"sort_state": "sorting", "error_message": None}
    if not doc.get("source_text"):
        updates["source_text"] = source
    if doc.get("status") != "indexed":
        updates["status"] = "processing"
    db.table("knowledge_documents").update(updates).eq("id", document_id).eq("tenant_id", tenant_id).execute()


# ─── Review ───────────────────────────────────────────────────────────────────

@dataclass
class ApplyChoices:
    base_version_id: str
    accepted_hunk_ids: list[str] = field(default_factory=list)
    conflict_choices: dict[str, str] = field(default_factory=dict)  # conflict id -> "a" | "b" | "none"
    accepted_update_ids: list[str] = field(default_factory=list)  # description disagreements to apply


def build_review_payload(db, tenant_id: str, document_id: str) -> dict:
    review = _pending_review(db, tenant_id, document_id)
    if not review:
        raise NotFoundError("There's no review waiting for this file.")
    doc = _get_doc(db, tenant_id, document_id, "id,name") or {}
    latest = versions.current_description_version(db, tenant_id)
    base = versions.get_version(db, tenant_id, review["base_version_id"]) if review.get("base_version_id") else None
    base_text = (base or {}).get("content") or ""
    proposed = review.get("proposed_description") or ""
    hunks = diff_hunks(base_text, proposed, machine_lines(db, tenant_id))
    replaces = None
    if review.get("replaces_document_id"):
        old = _get_doc(db, tenant_id, review["replaces_document_id"], "id,name")
        replaces = {"id": old["id"], "name": old["name"]} if old else None
    return {
        "review_id": review["id"],
        "document_id": str(document_id),
        "document_name": doc.get("name") or "",
        "origin": review.get("origin") or "upload",
        "stale": base is None or latest["id"] != review.get("base_version_id"),
        "base_version_id": review.get("base_version_id"),
        "base_description": base_text,
        "proposed_description": proposed,
        "hunks": [h.to_dict() for h in hunks],
        "conflicts": review.get("conflicts") or [],
        "fact_disagreements": review.get("fact_disagreements") or [],
        "facts": review.get("proposed_facts") or "",
        "unverified": review.get("unverified") or [],
        "left_out": review.get("left_out") or [],
        "left_out_rules": review.get("left_out_rules") or [],
        "truncated": bool(review.get("truncated")),
        "replaces_document": replaces,
        "word_count": len(proposed.split()),
        "soft_word_limit": SOFT_WORD_LIMIT,
    }


def compute_final_description(review: dict, base_text: str, machine: set[str], choices: ApplyChoices) -> tuple[str, list[str]]:
    """The Description the client approved, plus the normalised lines this document
    contributed to it. Pure -- the frontend mirrors it for its live preview."""
    hunks = diff_hunks(base_text, review.get("proposed_description") or "", machine)
    accepted = set(choices.accepted_hunk_ids)
    final = apply_hunks(base_text, hunks, accepted)
    new_lines = [normalize(line) for h in hunks if h.id in accepted for line in h.new_lines if normalize(line)]

    for conflict in review.get("conflicts") or []:
        pick = choices.conflict_choices.get(conflict.get("id"), "none")
        if pick in ("a", "b"):
            line = conflict["option_a" if pick == "a" else "option_b"]
            final = insert_under_heading(final, conflict.get("heading") or "", line)
            new_lines.append(normalize(line))

    accepted_updates = set(choices.accepted_update_ids)
    for d in review.get("fact_disagreements") or []:
        if d.get("where") == "description" and d.get("id") in accepted_updates:
            replaced = replace_exact_line(final, d.get("existing_line") or "", d.get("proposed_line") or "")
            if replaced is not None:  # the line was changed by an accepted hunk: skip
                final = replaced
                new_lines.append(normalize(d["proposed_line"]))

    return final.strip(), list(dict.fromkeys(new_lines))


def apply_review(db, tenant_id: str, document_id: str, choices: ApplyChoices, *, user_id: str | None, is_owner: bool) -> dict:
    """Commit an approved review. Database writes only -- the caller schedules
    index_facts() so chunking/embedding never holds up the response; until the chunks
    exist the full-text fallback serves the new facts."""
    review = _pending_review(db, tenant_id, document_id)
    if not review:
        raise NotFoundError("There's no review waiting for this file.")
    latest = versions.current_description_version(db, tenant_id)
    if latest["id"] != review.get("base_version_id") or choices.base_version_id != review.get("base_version_id"):
        raise StaleError()

    base_text = latest.get("content") or ""
    final, new_lines = compute_final_description(review, base_text, machine_lines(db, tenant_id), choices)
    if not final:
        raise EmptyDescriptionError()
    changed = normalize_text(final) != normalize_text(base_text)
    if changed and not is_owner:
        raise OwnerRequiredError(
            "Only an account owner can apply changes to the Description. Ask an owner to review this file."
        )

    replaces = review.get("replaces_document_id")
    if replaces:
        final_norm = {normalize(line) for line in lines_of(final)}
        new_lines += [line for line in _doc_rule_lines(db, tenant_id, replaces) if line in final_norm]
    rule_lines = list(dict.fromkeys(new_lines))

    reason = "resort" if review.get("origin") == "resort" else "upload"
    if changed:
        versions.save_description(db, tenant_id, final, reason, user_id)

    facts = review.get("proposed_facts") or ""
    doc = _get_doc(db, tenant_id, document_id, "id,campaign_tag_id") or {}
    (
        db.table("knowledge_documents")
        .update({
            "full_text": facts,
            "rule_lines": rule_lines,
            "sorted_at": _now(),
            "status": "indexed",
            "sort_state": None,
            "error_message": None,
        })
        .eq("id", str(document_id))
        .eq("tenant_id", tenant_id)
        .execute()
    )
    versions.save_facts_version(db, tenant_id, str(document_id), facts, reason, user_id)
    # A legacy document's old chunks are the raw rulebook -- they must stop serving now.
    db.table("knowledge_chunks").delete().eq("document_id", str(document_id)).eq("tenant_id", tenant_id).execute()
    db.table("knowledge_reviews").update({"status": "applied"}).eq("id", review["id"]).execute()
    if replaces:
        delete_document_row(db, tenant_id, replaces)

    return {
        "description_changed": changed,
        "base_was_empty": not base_text.strip(),
        "final_description": final,
        "facts": facts,
        "campaign_tag_id": doc.get("campaign_tag_id"),
    }


def discard_review(db, tenant_id: str, document_id: str) -> None:
    """A new upload that was never applied is deleted outright; a live document just
    drops the proposal and keeps working as before."""
    review = _pending_review(db, tenant_id, document_id)
    if not review:
        raise NotFoundError("There's no review waiting for this file.")
    db.table("knowledge_reviews").update({"status": "discarded"}).eq("id", review["id"]).execute()
    doc = _get_doc(db, tenant_id, document_id, "id,status")
    if not doc:
        return
    if doc.get("status") != "indexed":
        delete_document_row(db, tenant_id, document_id)
    else:
        db.table("knowledge_documents").update({"sort_state": None}).eq("id", str(document_id)).eq("tenant_id", tenant_id).execute()


async def index_facts(tenant_id: str, document_id: str, facts: str, campaign_tag_id: str | None) -> None:
    """Chunk and embed a document's facts. Best-effort: on failure the full-text
    fallback still serves full_text, exactly as process_document always behaved."""
    from app.services.knowledge_service import _index_chunks

    if not (facts or "").strip():
        return
    try:
        await _index_chunks(document_id, tenant_id, facts, get_supabase(), campaign_tag_id=campaign_tag_id)
    except Exception as e:
        logger.error(f"knowledge_sort: embedding failed for {document_id}: {e}. Full-text fallback active.")


def delete_document_row(db, tenant_id: str, document_id: str) -> None:
    """Delete a document and its stored original. Chunks, reviews and facts versions go
    with it via ON DELETE CASCADE."""
    from app.services.knowledge_service import DOCS_BUCKET

    row = _get_doc(db, tenant_id, document_id, "id,storage_path")
    if not row:
        raise NotFoundError("Document not found.")
    if row.get("storage_path"):
        try:
            db.storage.from_(DOCS_BUCKET).remove([row["storage_path"]])
        except Exception as e:
            logger.warning(f"Knowledge document storage delete failed for {row['storage_path']}: {e}")
    db.table("knowledge_documents").delete().eq("id", str(document_id)).eq("tenant_id", tenant_id).execute()
