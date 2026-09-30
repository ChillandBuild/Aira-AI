"""Simulated world for running the PRODUCTION reply engine offline (deal_turn.converse_once with
the production prompt builder, catalog prompt, tools and guards).

Real: every LLM call (tenant's keys), knowledge retrieval, prompt building, tool validation.
Simulated: sessions, deals, Razorpay links, handovers, catalog rows (from the scenario config).

Patches are installed ONCE and dispatch to the scenario running in the current asyncio task
(a ContextVar), so scenarios can run concurrently without seeing each other's state.
"""
import contextvars
import re
from contextlib import ExitStack
from datetime import datetime, timedelta, timezone
from types import SimpleNamespace
from unittest.mock import patch

import app.services.ai_reply as ai_reply
import app.services.business_details as business_details
import app.services.choices as choices
import app.services.deal_actions as deal_actions
import app.services.deal_engine as deal_engine
import app.services.deal_turn as deal_turn
import app.services.deals as deals
import app.services.intake as intake

LEAD_ID = "eval-lead"
PHONE = "+910000000000"
CURRENT: contextvars.ContextVar["World"] = contextvars.ContextVar("world")


class StubDB:
    """Every DB read the engine does outside the patched functions comes back empty."""

    def table(self, _name):
        return self

    def __getattr__(self, _name):
        return lambda *a, **k: self

    def execute(self):
        return SimpleNamespace(data=[], count=0)


class World:
    def __init__(self, tenant_id: str, config: dict):
        self.tenant_id = tenant_id
        self.config = config
        self.intake_config = {
            "enabled": bool(config.get("packages")),
            "fields": config.get("required_details", []),
            "packages": config.get("packages", []),
            "service_noun": config.get("service_noun", "consultation"),
            "gst_percent": config.get("gst_percent") or 0,
        }
        self.required_keys = [f["key"] for f in config.get("required_details", [])]
        self.catalog = {
            item["id"]: {
                "id": item["id"], "name": item["name"], "item_type": item.get("item_type", "product"),
                "description": item.get("description", ""), "price_paise": item.get("price_paise"),
                "price_note": None, "stock_quantity": item.get("stock"),
            }
            for item in config.get("catalog") or []
        }
        self.sessions: dict[str, dict] = {}
        self.orders: list[dict] = []
        self.links = 0
        self.events: list[dict] = []
        self.settings: dict = {}
        self.tamil_locked = False
        self.last_activity: datetime | None = None  # the open deal's idle clock (last_activity_at)

    # sessions -----------------------------------------------------------------
    def active_session(self):
        rows = [s for s in self.sessions.values() if s["status"] in intake._ACTIVE_STATUSES]
        return rows[-1] if rows else None

    def new_session(self, status: str, extra: dict | None = None) -> dict:
        sid = f"sess-{len(self.sessions) + 1}"
        self.sessions[sid] = {
            "id": sid, "lead_id": LEAD_ID, "tenant_id": self.tenant_id, "status": status,
            "collected_data": {}, "skipped_fields": [], "package_path": [], "selected_addons": None,
        } | (extra or {})
        return self.sessions[sid]

    def note_lead_message(self, away: timedelta | None = None) -> str | None:
        """Mirror of intake.note_lead_message: the idle clock BEFORE this message (None with no
        open deal), then restart it. `away` pretends the lead was silent that long first."""
        now = datetime.now(timezone.utc)
        if away is not None:
            self.last_activity = now - away
        session = self.active_session()
        previous = self.last_activity if session and session["status"] in intake._UNFINISHED_STATUSES else None
        self.last_activity = now
        return previous.isoformat() if previous else None

    def previous_booking(self) -> dict | None:
        """Mirror of intake.previous_booking: the newest finished session that holds details."""
        done = [s for s in self.sessions.values()
                if s["status"] in ("cancelled", "paid", "resolved") and any((s.get("collected_data") or {}).values())]
        return done[-1] if done else None

    def _seed_link(self, session: dict, link) -> None:
        """state.link: {"expires_in_hours": 20} = a live link, or "expired" = the link ran out
        (link cleared, the deal stays open in awaiting_payment)."""
        if not link:
            return
        session["status"] = "awaiting_payment"
        session["razorpay_payment_link_id"] = "plink_seed"
        if link == "expired":
            return
        session["payment_link"] = self.next_link()
        # the price the link was made for; state.stale_amount_paise = the price changed while they were away
        session["amount_paise"] = link.get("amount_paise", session.get("total_amount_paise"))
        session["payment_link_expires_at"] = (
            datetime.now(timezone.utc) + timedelta(hours=link.get("expires_in_hours", 20))
        ).isoformat()

    def missing(self, session: dict) -> list[str]:
        return deal_engine.missing_details(
            self.config.get("required_details", []), session.get("collected_data") or {},
            session.get("skipped_fields") or [],
        )

    def next_link(self) -> str:
        self.links += 1
        return f"https://rzp.io/l/eval{self.links}"

    # seeding ------------------------------------------------------------------
    def seed(self, state: dict) -> None:
        earlier = next((p for p in self.config.get("packages", []) if p["key"] == (state.get("previous") or {}).get("selected")), None)
        if earlier:  # a finished booking of this lead: {"previous": {"selected": key, "collected": {...}, "status": "cancelled"}}
            self.new_session(state["previous"].get("status", "cancelled"), {
                "collected_data": dict(state["previous"].get("collected") or {}),
                "package_key": earlier["key"], "package_name": earlier["name"],
            })
        package = next((p for p in self.config.get("packages", []) if p["key"] == state.get("selected")), None)
        if package:
            saved = {k: "seeded" for k in state.get("details_saved", [])} | dict(state.get("collected") or {})
            # state.stale_amount_paise: the price the deal (and its link) was made at, before it changed while they were away
            was = state.get("stale_amount_paise", package["amount_paise"])
            session = self.new_session("collecting", {
                "collected_data": saved, "package_key": package["key"], "package_name": package["name"],
                "package_amount_paise": was, "total_amount_paise": was,
            })
            if isinstance(state.get("link"), dict) and "stale_amount_paise" in state:
                state = {**state, "link": {**state["link"], "amount_paise": was}}
            if state.get("paid"):
                session["status"] = deal_engine.PAID_STATUS
            elif not self.missing(session):
                session["status"] = deal_engine.CONFIRM_STATUS
            self._seed_link(session, state.get("link"))
        self.last_activity = datetime.now(timezone.utc) - _away(state)
        for order in state.get("orders") or []:
            item = self.catalog[order["item_id"]]
            qty = order.get("qty", 1)
            self.orders.append({
                "id": f"d{len(self.orders) + 1}", "deal_number": 100 + len(self.orders),
                "stage": order.get("stage", "awaiting_payment"), "total_paise": item["price_paise"] * qty,
                "payment_link": self.next_link() if order.get("stage", "awaiting_payment") != "quoted" else None,
                "items": [{"catalog_item_id": item["id"], "name": item["name"], "qty": qty,
                           "line_total_paise": item["price_paise"] * qty}],
            })


def _away(spec: dict) -> timedelta:
    """How long the lead has been silent: {"away_days": 4} and/or {"away_hours": 2}."""
    return timedelta(days=spec.get("away_days", 0), hours=spec.get("away_hours", 0))


def _w() -> World:
    return CURRENT.get()


async def _payment_link(**kwargs):
    world = _w()
    url = world.next_link()
    session = world.sessions.get((kwargs.get("notes") or {}).get("booking_id"), {})
    expires = (datetime.now(timezone.utc) + timedelta(hours=24)).isoformat()
    world.events.append({"type": "payment_link", "url": url, "missing_required": world.missing(session),
                         "amount_paise": kwargs.get("amount_paise"), "expires_at": expires})
    return {
        "payment_link_url": url, "razorpay_payment_link_id": f"plink_eval{world.links}",
        "payment_link_expires_at": expires,
    }


async def _create_deal(tenant_id, lead_id, lines, source, stage="quoted", **kw):
    world = _w()
    items = [{"catalog_item_id": ln["catalog_item_id"], "name": ln["name"], "qty": ln["qty"],
              "line_total_paise": world.catalog[ln["catalog_item_id"]]["price_paise"] * ln["qty"]} for ln in lines]
    total = sum(i["line_total_paise"] for i in items)
    url = world.next_link()
    deal = {"id": f"d{len(world.orders) + 1}", "deal_number": 100 + len(world.orders), "stage": "awaiting_payment",
            "total_paise": total, "payment_link": url, "items": items}
    world.orders.append(deal)
    world.events.append({"type": "payment_link", "url": url, "missing_required": [],
                         "amount_paise": total, "expires_at": (datetime.now(timezone.utc) + timedelta(hours=24)).isoformat()})
    return {"deal": deal, "items": items, "payment_link": url}


def _handover(lead_id, reason, tenant_id, assigned_to, db):
    world = _w()
    if not any(e["type"] == "handover" for e in world.events):
        world.events.append({"type": "handover", "reason": reason})


def _known_prices(db, tenant_id, lead_id):
    world = _w()
    prices = deal_engine.price_multiples(i["price_paise"] for i in world.catalog.values())
    prices |= {o["total_paise"] / 100 for o in world.orders}
    return frozenset(p for p in prices if p)


def _update(session_id, patch_, db, unless_status=None):
    """Mirror of intake._update_session: skips the write when the session is already in unless_status."""
    world = _w()
    if unless_status and world.sessions[session_id].get("status") == unless_status:
        return False
    world.sessions[session_id].update(patch_)
    if intake._is_progress(patch_):  # real progress restarts the idle clock, as in production
        world.last_activity = datetime.now(timezone.utc)
    return True


def _create(lead_id, tenant_id, db):
    world = _w()
    world.last_activity = datetime.now(timezone.utc)
    return world.new_session("offer_pending")


def _live_link(session: dict) -> bool:
    expires = deal_engine.parse_time(session.get("payment_link_expires_at"))
    return bool(session.get("payment_link") and session.get("razorpay_payment_link_id")
                and (expires is None or expires > datetime.now(timezone.utc)))


async def _cancel_session_link(db, session, *, keep_plink_id=None):
    """Razorpay is never called: only recorded, so a scenario can check the old link was cancelled."""
    if not _live_link(session) or session.get("razorpay_payment_link_id") == keep_plink_id:
        return False
    _w().events.append({"type": "plink_cancelled", "plink_id": session["razorpay_payment_link_id"]})
    return True


async def _cancel_open_session(db, session, *, idle_before=None, reason=None):
    """Mirror of intake.cancel_open_session (conditional on the status still being what the
    caller saw, tenant-scoped); records deal_closed, then plink_cancelled when a link was live."""
    world = _w()
    row = world.sessions.get(session["id"])
    if not row or row["tenant_id"] != session.get("tenant_id") or row["status"] != session["status"]:
        return False
    before = dict(row)
    row["status"] = "cancelled"
    world.events.append({"type": "deal_closed", "session_id": row["id"], "package_key": row.get("package_key")})
    await _cancel_session_link(db, before)
    return True


def install(stack: ExitStack) -> None:
    targets = {
        (intake, "get_intake_config"): lambda tenant_id, db=None: _w().intake_config,
        (intake, "_get_active_session"): lambda lead_id, tenant_id, db: _w().active_session(),
        (intake, "_create_session"): _create,
        (intake, "_update_session"): _update,
        (intake, "cancel_session_link"): _cancel_session_link,
        (intake, "cancel_open_session"): _cancel_open_session,
        (intake, "previous_booking"): lambda db, tenant_id, lead_id: _w().previous_booking(),
        (intake, "create_payment_link"): _payment_link,
        (intake, "adopt_lead_name"): lambda *a, **k: None,
        (ai_reply, "_trigger_chat_escalation"): _handover,
        (deals, "create_deal"): _create_deal,
        (deals, "held_quantities"): lambda tenant_id, ids, db=None: {},
        (deals, "upsert_quoted_deal"): lambda *a, **k: None,
        (deal_actions, "lead_orders"): lambda db, tenant_id, lead_id: list(_w().orders),
        (deal_actions, "_open_awaiting_deals"): lambda ctx: [o for o in _w().orders if o["stage"] == "awaiting_payment"],
        (deal_turn, "_known_prices"): _known_prices,
        (business_details, "get_business_details"): lambda tenant_id, db=None: dict(_w().config.get("business_details") or {}),
    }
    for (module, name), replacement in targets.items():
        stack.enter_context(patch.object(module, name, replacement))


# ---------------------------------------------------------------- settings overrides

import app.config_dynamic as config_dynamic  # noqa: E402

_real_get_setting = config_dynamic.get_setting
_UNSET = object()


def _get_setting(key, fallback=None, tenant_id=None):
    world = CURRENT.get(None)
    value = (world.settings if world else {}).get(key, _UNSET)
    if value is _UNSET:
        return _real_get_setting(key, fallback=fallback, tenant_id=tenant_id)
    return value if value is not None else fallback


def install_settings(stack: ExitStack) -> None:
    stack.enter_context(patch.object(config_dynamic, "get_setting", _get_setting))
    stack.enter_context(patch.object(ai_reply, "get_setting", _get_setting))


# ---------------------------------------------------------------- one turn

CATALOG_RULES = {"can_recommend": True, "can_send_images": True, "max_images_per_reply": 3}


def logged_text(reply: dict) -> str:
    """How production stores an outbound message in the thread the model later reads."""
    if reply["kind"] in ("buttons", "list"):
        return deal_turn.menu_log_text(reply["text"], reply)
    if reply["kind"] == "image":
        return f"[Catalog image: {reply['text']}]"
    return reply["text"]


async def _knowledge(world: World, message: str) -> str:
    facts = world.config.get("facts")
    if facts is not None:
        return "\n\n".join(f"=== excerpt {i + 1} ===\n{f}" for i, f in enumerate(facts))
    from app.services.knowledge_service import get_knowledge_context
    return await get_knowledge_context(world.tenant_id, query=message) or ""


async def run_turn(world: World, history: list[dict], body: str, tap: str | None, away: timedelta | None = None) -> dict:
    """One inbound message through the production path. Returns the transcript turn.
    `away` pretends the lead was silent that long before this message."""
    world.events = []
    # Read first, exactly as generate_reply does: capture_details below restarts the idle clock.
    last_seen_at = world.note_lead_message(away)
    db = StubDB()
    catalog_text, catalog_tools, items_by_id, max_images = ai_reply.catalog_prompt(
        list(world.catalog.values()), "", CATALOG_RULES,
    )
    ctx = deal_turn.build_context(
        db, world.tenant_id, LEAD_ID, PHONE, channel="whatsapp", catalog=items_by_id, max_images=max_images,
    )
    guard_fired = deal_turn.pre_turn_guards(ctx, body)
    earlier = [m["content"] for m in history if m["role"] == "user"]
    await deal_turn.capture_details(ctx, body, earlier=earlier)
    knowledge = await _knowledge(world, body)
    if ai_reply._should_lock_tamil(body):  # the webhook's record_tamil_lock_request, persisted per lead
        world.tamil_locked = True
    lead = {"name": "", "segment": "C", "tenant_id": world.tenant_id, "needs_human_attention": False,
            "tamil_locked": world.tamil_locked}
    system_prompt, _mode, _active = ai_reply.build_reply_system_prompt(
        db, LEAD_ID, world.tenant_id, lead, body, "whatsapp",
        context_text=knowledge, catalog_context=catalog_text,
        tapped_option_key=None if choices.is_choice_tap(tap) else tap, last_seen_at=last_seen_at,
    )
    messages = [{"role": "system", "content": system_prompt}, *history, {"role": "user", "content": body}]
    text, calls, outcome = await deal_turn.converse_once(
        messages, catalog_tools, ctx, tenant_id=world.tenant_id, append_link=False,
        handover_opened=guard_fired, handover_line=ai_reply._handover_line(world.tenant_id),
    )
    sent_urls = {e.get("url") for e in world.events if e["type"] == "payment_link"}
    reused = [outcome.payment_link] if outcome.payment_link else []
    reused += re.findall(r"https?://\S+", outcome.quote_text or "")
    for url in reused:
        if url not in sent_urls:  # a still-valid link resent by code counts as sent this turn
            session = world.active_session() or {}
            world.events.append({"type": "payment_link", "url": url, "missing_required": world.missing(session),
                                 "amount_paise": session.get("amount_paise"),
                                 "expires_at": session.get("payment_link_expires_at")})
    if outcome.payment_link:
        text = f"{text}\n{outcome.payment_link}".strip()
    if outcome.quote_text:
        text = f"{text}\n\n{outcome.quote_text}".strip()
    menu = outcome.menu
    replies = [{"text": text, "kind": menu["kind"] if menu else "text", "options": menu["options"] if menu else []}]
    replies += [{"text": world.catalog[i]["name"], "kind": "image", "options": []} for i in outcome.image_item_ids]
    if ai_reply._HUMAN_REQUEST_RE.search(body):
        _handover(LEAD_ID, "User requested a human agent", world.tenant_id, None, db)  # trigger C
    return {
        "lead": body, "replies": replies, "events": list(world.events),
        "debug": {"away_seen": last_seen_at,
                  "tool_calls": [f"{(c.get('function') or {}).get('name')} {(c.get('function') or {}).get('arguments')}" for c in calls],
                  "refusals": list(outcome.refusals), "deal": _deal_summary(world)},
    }


def _deal_summary(world: World) -> dict | None:
    """The open deal at the end of the turn and what a link for it should charge TODAY."""
    session = world.active_session()
    if not session or not session.get("package_key"):
        return None
    return {"package_key": session["package_key"], "status": session["status"],
            "current_charge_paise": deal_engine.current_charge(world.intake_config, session)}


EXTRA_SETTINGS: dict = {}  # run-wide overrides, e.g. {"ai_reply_model": "google/gemini-3.5-flash"}


def settings_for(config: dict) -> dict:
    """Synthetic businesses bring their own description/handover line; Astro configs use the real tenant's."""
    keys = {"description": "business_description", "handover_line": "handover_line",
            "language_mode": "reply_language_mode", "app_link": "app_download_link"}
    # A synthetic business with no handover line or app link has none: it must not borrow the
    # key tenant's real ones (the salon once told customers to use "support in the app").
    defaults = {"handover_line": "", "app_download_link": ""} if "description" in config else {}
    return defaults | {setting: config[key] for key, setting in keys.items() if key in config} | EXTRA_SETTINGS


async def run_scenario(scenario: dict, config: dict, tenant_id: str) -> list[dict]:
    world = World(tenant_id, config)
    world.settings = settings_for(config)
    CURRENT.set(world)
    world.seed(scenario.get("state") or {})
    history: list[dict] = []
    for raw in scenario.get("prior") or []:
        history.append({"role": "user" if raw[0] == "lead" else "assistant", "content": raw[1]})
    transcript = []
    import time
    for turn in scenario["lead_turns"]:
        body, tap = (turn["text"], turn.get("tap")) if isinstance(turn, dict) else (turn, None)
        away = _away(turn) if isinstance(turn, dict) and ("away_days" in turn or "away_hours" in turn) else None
        started = time.monotonic()
        result = await run_turn(world, history, body, tap, away)
        result["seconds"] = round(time.monotonic() - started, 1)
        history.append({"role": "user", "content": body})
        history.extend({"role": "assistant", "content": logged_text(r)} for r in result["replies"])
        transcript.append(result)
    return transcript
