"""Executors for the AI-native deal engine (services/deal_actions.py).

The session store, Razorpay and the handover helper are replaced with in-memory fakes:
the point is to prove the GUARDRAILS (what code refuses no matter what the model asks).
"""
import asyncio
import json
from unittest.mock import patch

import pytest

from app.services import deal_actions, intake

LEAD, TENANT, PHONE = "lead-1", "tenant-1", "+910000000000"

CONFIG = {
    "enabled": True,
    "service_noun": "consultation",
    "fields": [
        {"key": "name", "label": "Full name", "type": "text"},
        {"key": "birth_date", "label": "Date of birth", "type": "date"},
    ],
    "packages": [
        {"key": "one_question", "name": "One Question", "amount_paise": 4900, "button_label": "49 Rs"},
        {"key": "detailed", "name": "Detailed Question", "amount_paise": 9900, "button_label": "99Rs",
         "addons": [{"key": "report", "name": "Written report", "amount_paise": 2000}]},
        {"key": "marriage", "name": "Marriage Compatibility", "amount_paise": 9900, "button_label": "Marriage 99Rs"},
    ],
}
NO_DETAILS_CONFIG = {**CONFIG, "fields": []}


class World:
    """In-memory session store + recorded side effects."""

    def __init__(self):
        self.sessions: dict[str, dict] = {}
        self.links: list[dict] = []
        self.handovers: list[str] = []

    def install(self, stack_patches):
        w = self

        def get_active(lead_id, tenant_id, db):
            rows = [s for s in w.sessions.values() if s["status"] in intake._ACTIVE_STATUSES]
            return rows[-1] if rows else None

        def create(lead_id, tenant_id, db):
            sid = f"s{len(w.sessions) + 1}"
            w.sessions[sid] = {
                "id": sid, "lead_id": lead_id, "tenant_id": tenant_id, "status": "offer_pending",
                "collected_data": {}, "skipped_fields": [], "package_path": [], "selected_addons": None,
            }
            return w.sessions[sid]

        def update(session_id, patch_, db):
            w.sessions[session_id].update(patch_)

        async def link(**kw):
            w.links.append(kw)
            return {"payment_link_url": f"https://rzp.io/l/{len(w.links)}"}

        def handover(lead_id, reason, tenant_id, assigned_to, db):
            w.handovers.append(reason)

        for module, name, fn in [
            (intake, "_get_active_session", get_active),
            (intake, "_create_session", create),
            (intake, "_update_session", update),
            (intake, "create_payment_link", link),
            (intake, "adopt_lead_name", lambda *a, **k: None),
        ]:
            stack_patches.append(patch.object(module, name, fn))
        import app.services.ai_reply as ai_reply
        stack_patches.append(patch.object(ai_reply, "_trigger_chat_escalation", handover))


@pytest.fixture
def world():
    w = World()
    patches: list = []
    w.install(patches)
    for p in patches:
        p.start()
    yield w
    for p in patches:
        p.stop()


def call(name, **args):
    return {"function": {"name": name, "arguments": json.dumps(args)}}


def run(calls, config=CONFIG, last_assistant_text=""):
    ctx = deal_actions.DealContext(config=config, db=object(), lead_id=LEAD, tenant_id=TENANT, phone=PHONE)
    return asyncio.run(deal_actions.apply_tool_calls(calls, ctx, last_assistant_text=last_assistant_text))


class TestSelectOffering:
    def test_unknown_key_is_refused(self, world):
        out = run([call("select_offering", key="nope")])
        assert out.refusals and not world.sessions

    def test_creates_session_with_price_snapshot_and_collecting_status(self, world):
        out = run([call("select_offering", key="one_question")])
        s = next(iter(world.sessions.values()))
        assert not out.refusals
        assert s["package_key"] == "one_question" and s["package_amount_paise"] == 4900
        assert s["total_amount_paise"] == 4900 and s["status"] == "collecting"

    def test_no_required_details_goes_straight_to_ready(self, world):
        run([call("select_offering", key="one_question")], NO_DETAILS_CONFIG)
        assert next(iter(world.sessions.values()))["status"] == "awaiting_confirmation"

    def test_offering_with_addons_refuses_until_addon_keys_given(self, world):
        out = run([call("select_offering", key="detailed")])
        assert out.refusals and not world.sessions

    def test_addon_total_is_computed_by_code(self, world):
        run([call("select_offering", key="detailed", addon_keys=["report"])])
        assert next(iter(world.sessions.values()))["total_amount_paise"] == 11900

    def test_unknown_addon_is_refused(self, world):
        out = run([call("select_offering", key="detailed", addon_keys=["free-gift"])])
        assert out.refusals and not world.sessions

    def test_paid_session_cannot_be_reselected(self, world):
        run([call("select_offering", key="one_question")])
        next(iter(world.sessions.values()))["status"] = "paid"
        out = run([call("select_offering", key="marriage")])
        assert out.refusals
        assert next(iter(world.sessions.values()))["package_key"] == "one_question"

    def test_changing_package_clears_the_old_link(self, world):
        run([call("select_offering", key="one_question")], NO_DETAILS_CONFIG)
        run([call("create_payment_link")], NO_DETAILS_CONFIG)
        run([call("select_offering", key="marriage")], NO_DETAILS_CONFIG)
        s = next(iter(world.sessions.values()))
        assert s["package_key"] == "marriage" and s.get("payment_link") is None
        assert s["status"] == "awaiting_confirmation"


class TestSaveDetails:
    def test_needs_a_selected_offering_first(self, world):
        out = run([call("save_details", fields={"name": "Ravi"})])
        assert out.refusals

    def test_saves_known_keys_and_ignores_unknown(self, world):
        run([call("select_offering", key="one_question")])
        out = run([call("save_details", fields={"name": " Ravi ", "shoe_size": "9"})])
        s = next(iter(world.sessions.values()))
        assert s["collected_data"] == {"name": "Ravi"} and not out.refusals

    def test_only_unknown_keys_is_refused(self, world):
        run([call("select_offering", key="one_question")])
        assert run([call("save_details", fields={"shoe_size": "9"})]).refusals

    def test_status_flips_to_ready_when_last_detail_arrives(self, world):
        run([call("select_offering", key="one_question")])
        run([call("save_details", fields={"name": "Ravi"})])
        s = next(iter(world.sessions.values()))
        assert s["status"] == "collecting"
        run([call("save_details", fields={"birth_date": "12-03-1994"})])
        assert s["status"] == "awaiting_confirmation"

    def test_choice_field_rejects_value_not_in_options(self, world):
        config = {**CONFIG, "fields": [{"key": "plan", "label": "Plan", "type": "choice", "options": ["Gold", "Silver"]}]}
        run([call("select_offering", key="one_question")], config)
        assert run([call("save_details", fields={"plan": "Bronze"})], config).refusals
        assert not run([call("save_details", fields={"plan": "gold"})], config).refusals


class TestImpossibleDates:
    def test_date_that_cannot_exist_is_refused(self, world):
        run([call("select_offering", key="one_question")])
        out = run([call("save_details", fields={"name": "Ravi", "birth_date": "31-02-1995"})])
        s = next(iter(world.sessions.values()))
        assert s["collected_data"] == {"name": "Ravi"} and "birth_date" in out.refusals[0]

    def test_month_name_impossible_date_is_refused(self, world):
        run([call("select_offering", key="one_question")])
        assert run([call("save_details", fields={"birth_date": "30 February 1990"})]).refusals

    def test_real_dates_in_many_shapes_are_accepted(self, world):
        run([call("select_offering", key="one_question")])
        for value in ("12-03-1994", "12/3/94", "29-02-2000", "12 March 1994", "4 june 1996", "around 1995"):
            assert not run([call("save_details", fields={"birth_date": value})]).refusals, value

    def test_leap_day_in_a_non_leap_year_is_refused(self, world):
        run([call("select_offering", key="one_question")])
        assert run([call("save_details", fields={"birth_date": "29-02-2001"})]).refusals


class TestSkipDetail:
    def test_skipped_detail_counts_as_done(self, world):
        run([call("select_offering", key="one_question")])
        run([call("save_details", fields={"name": "Ravi"})])
        run([call("skip_detail", key="birth_date", reason="does not know")])
        s = next(iter(world.sessions.values()))
        assert s["skipped_fields"] == ["birth_date"] and s["status"] == "awaiting_confirmation"

    def test_unknown_field_is_refused(self, world):
        run([call("select_offering", key="one_question")])
        assert run([call("skip_detail", key="shoe_size")]).refusals


class TestCreatePaymentLink:
    def test_refused_without_a_selection(self, world):
        out = run([call("create_payment_link")])
        assert out.refusals and not world.links and out.payment_link is None

    def test_refused_while_details_are_missing(self, world):
        run([call("select_offering", key="one_question")])
        run([call("save_details", fields={"name": "Ravi"})])
        out = run([call("create_payment_link")])
        assert out.refusals and "birth_date" in out.refusals[0] and not world.links

    def test_link_created_from_session_amount_never_from_model(self, world):
        run([call("select_offering", key="one_question")])
        run([call("save_details", fields={"name": "Ravi", "birth_date": "12-03-1994"})])
        out = run([call("create_payment_link", amount=1)])
        assert out.payment_link == "https://rzp.io/l/1" and not out.refusals
        assert world.links[0]["amount_paise"] == 4900
        s = next(iter(world.sessions.values()))
        assert s["status"] == "awaiting_payment" and s["payment_link"] == out.payment_link
        assert s["amount_paise"] == 4900

    def test_select_save_and_link_in_one_turn(self, world):
        out = run([
            call("select_offering", key="one_question"),
            call("save_details", fields={"name": "Ravi", "birth_date": "12-03-1994"}),
            call("create_payment_link"),
        ])
        assert out.payment_link and not out.refusals

    def test_existing_link_is_reused_not_recreated(self, world):
        run([call("select_offering", key="one_question")], NO_DETAILS_CONFIG)
        first = run([call("create_payment_link")], NO_DETAILS_CONFIG)
        second = run([call("create_payment_link")], NO_DETAILS_CONFIG)
        assert first.payment_link == second.payment_link and len(world.links) == 1

    def test_paid_session_gets_no_new_link(self, world):
        run([call("select_offering", key="one_question")], NO_DETAILS_CONFIG)
        next(iter(world.sessions.values()))["status"] = "paid"
        out = run([call("create_payment_link")], NO_DETAILS_CONFIG)
        assert out.refusals and not world.links

    def test_razorpay_failure_brings_in_a_person(self, world, monkeypatch):
        async def broken(**kw):
            raise RuntimeError("Razorpay payment link creation failed: 401")

        monkeypatch.setattr(intake, "create_payment_link", broken)
        run([call("select_offering", key="one_question")], NO_DETAILS_CONFIG)
        out = run([call("create_payment_link")], NO_DETAILS_CONFIG)
        assert out.handover and world.handovers and "payment link" in world.handovers[0].lower()
        assert out.payment_link is None and out.refusals

    def test_a_failed_link_is_not_retried_in_the_same_turn(self, world, monkeypatch):
        attempts = []

        async def broken(**kw):
            attempts.append(kw)
            raise RuntimeError("401")

        monkeypatch.setattr(intake, "create_payment_link", broken)
        run([call("select_offering", key="one_question")], NO_DETAILS_CONFIG)
        run([call("create_payment_link"), call("create_payment_link")], NO_DETAILS_CONFIG)
        assert len(attempts) == 1

    def test_customer_name_falls_back_to_phone(self, world):
        run([call("select_offering", key="one_question")], NO_DETAILS_CONFIG)
        run([call("create_payment_link")], NO_DETAILS_CONFIG)
        assert world.links[0]["customer_name"] == PHONE


class TestShowOptions:
    def test_top_level_packages_become_buttons(self, world):
        out = run([call("show_options", of="packages")])
        assert out.menu["kind"] == "buttons"
        assert out.menu["options"] == ["49 Rs", "99Rs", "Marriage 99Rs"]

    def test_only_one_menu_per_turn(self, world):
        out = run([call("show_options", of="packages"), call("show_options", of="packages")])
        assert out.menu and len(out.refusals) == 1

    def test_same_menu_as_the_previous_message_is_refused(self, world):
        previous = "Pick one\n\n[49 Rs]  [99Rs]  [Marriage 99Rs]"
        out = run([call("show_options", of="packages")], last_assistant_text=previous)
        assert out.menu is None and out.refusals and "just shown" in out.refusals[0]

    def test_a_different_menu_is_allowed_after_a_menu(self, world):
        previous = "Pick one\n\n[Gold]  [Silver]"
        assert run([call("show_options", of="packages")], last_assistant_text=previous).menu

    def test_single_option_is_refused(self, world):
        config = {**CONFIG, "packages": CONFIG["packages"][:1]}
        assert run([call("show_options", of="packages")], config).refusals

    def test_addons_menu_includes_no_thanks(self, world):
        run([call("select_offering", key="detailed", addon_keys=["report"])])
        out = run([call("show_options", of="addons", under="detailed")])
        assert out.menu and "No thanks" in out.menu["options"]

    def test_addons_menu_refused_when_offering_has_none(self, world):
        assert run([call("show_options", of="addons", under="one_question")]).refusals


class TestHandover:
    def test_opens_a_handover_and_flags_the_outcome(self, world):
        out = run([call("hand_to_human", reason="lead says they paid")])
        assert out.handover and world.handovers == ["lead says they paid"]


class TestRobustness:
    def test_unknown_tool_is_ignored(self, world):
        out = run([call("send_quick_reply_block", block_name="x")])
        assert not out.refusals and not out.menu and not out.handover

    def test_malformed_arguments_are_refused_not_raised(self, world):
        out = run([{"function": {"name": "select_offering", "arguments": "{not json"}}])
        assert out.refusals


# ---------------------------------------------------------------- products

CATALOG = {
    "sku-runner": {"id": "sku-runner", "name": "Runner X", "item_type": "product", "price_paise": 249900, "stock_quantity": 5},
    "sku-sandal": {"id": "sku-sandal", "name": "Comfort Sandal", "item_type": "product", "price_paise": 99900, "stock_quantity": 0},
    "svc-fit": {"id": "svc-fit", "name": "Fitting session", "item_type": "service", "price_paise": None, "stock_quantity": None},
}


class Shop:
    def __init__(self, monkeypatch, held=None, existing=None):
        from app.services import deals
        self.created: list[dict] = []
        self.quoted: list[dict] = []
        self.existing = existing or []

        async def create_deal(tenant_id, lead_id, lines, source, stage="quoted", **kw):
            self.created.append({"lines": lines, "stage": stage, **kw})
            total = sum(CATALOG[line["catalog_item_id"]]["price_paise"] * line["qty"] for line in lines)
            items = [{"name": line["name"], "qty": line["qty"],
                      "line_total_paise": CATALOG[line["catalog_item_id"]]["price_paise"] * line["qty"]} for line in lines]
            return {"deal": {"id": f"d{len(self.created)}", "total_paise": total}, "items": items,
                    "payment_link": f"https://rzp.io/l/deal{len(self.created)}"}

        monkeypatch.setattr(deals, "create_deal", create_deal)
        monkeypatch.setattr(deals, "held_quantities", lambda tenant_id, ids, db=None: dict(held or {}))
        monkeypatch.setattr(deals, "upsert_quoted_deal", lambda tenant_id, lead_id, line, db=None: self.quoted.append(line))
        monkeypatch.setattr(deal_actions, "_open_awaiting_deals", lambda ctx: list(self.existing))


def run_shop(calls, max_images=3):
    ctx = deal_actions.DealContext(config={}, db=object(), lead_id=LEAD, tenant_id=TENANT, phone=PHONE,
                                   catalog=CATALOG, max_images=max_images)
    return asyncio.run(deal_actions.apply_tool_calls(calls, ctx))


class TestRecommendItem:
    def test_known_item_is_queued_for_its_photo_and_quoted(self, monkeypatch):
        shop = Shop(monkeypatch)
        out = run_shop([call("recommend_catalog_item", item_id="sku-runner")])
        assert out.image_item_ids == ("sku-runner",) and not out.refusals
        assert shop.quoted and shop.quoted[0]["catalog_item_id"] == "sku-runner"

    def test_out_of_stock_is_refused(self, monkeypatch):
        Shop(monkeypatch)
        out = run_shop([call("recommend_catalog_item", item_id="sku-sandal")])
        assert out.image_item_ids == () and "out of stock" in out.refusals[0].lower()

    def test_unknown_item_is_refused(self, monkeypatch):
        Shop(monkeypatch)
        assert run_shop([call("recommend_catalog_item", item_id="nope")]).refusals

    def test_unpriced_item_gets_a_photo_but_no_quoted_deal(self, monkeypatch):
        shop = Shop(monkeypatch)
        out = run_shop([call("recommend_catalog_item", item_id="svc-fit")])
        assert out.image_item_ids == ("svc-fit",) and not shop.quoted

    def test_same_item_twice_is_one_photo(self, monkeypatch):
        Shop(monkeypatch)
        out = run_shop([call("recommend_catalog_item", item_id="sku-runner")] * 2)
        assert out.image_item_ids == ("sku-runner",)


class TestSendQuote:
    def test_quote_uses_catalog_prices_and_returns_summary_with_link(self, monkeypatch):
        shop = Shop(monkeypatch)
        out = run_shop([call("send_quote", item_ids=["sku-runner"], quantities=[2])])
        assert shop.created[0]["stage"] == "awaiting_payment" and shop.created[0]["send_link"] is False
        assert "Runner X" in out.quote_text and "https://rzp.io/l/deal1" in out.quote_text
        assert "4,998" in out.quote_text or "4998" in out.quote_text

    def test_not_enough_stock_is_refused(self, monkeypatch):
        shop = Shop(monkeypatch, held={"sku-runner": 4})
        out = run_shop([call("send_quote", item_ids=["sku-runner"], quantities=[2])])
        assert out.refusals and not shop.created and out.quote_text is None

    def test_unpriced_or_unknown_items_are_refused(self, monkeypatch):
        shop = Shop(monkeypatch)
        out = run_shop([call("send_quote", item_ids=["svc-fit", "nope"])])
        assert out.refusals and not shop.created

    def test_zero_or_negative_quantity_is_refused(self, monkeypatch):
        shop = Shop(monkeypatch)
        out = run_shop([call("send_quote", item_ids=["sku-runner"], quantities=[0])])
        assert out.refusals and not shop.created

    def test_same_open_quote_reuses_the_existing_link(self, monkeypatch):
        existing = [{"id": "d9", "payment_link": "https://rzp.io/l/old", "total_paise": 499800,
                     "items": [{"catalog_item_id": "sku-runner", "qty": 2, "name": "Runner X", "line_total_paise": 499800}]}]
        shop = Shop(monkeypatch, existing=existing)
        out = run_shop([call("send_quote", item_ids=["sku-runner"], quantities=[2])])
        assert not shop.created and "https://rzp.io/l/old" in out.quote_text

    def test_quote_failure_brings_in_a_person(self, monkeypatch):
        from app.services import deals
        Shop(monkeypatch)
        opened = []

        async def broken(*a, **k):
            raise RuntimeError("401")

        monkeypatch.setattr(deals, "create_deal", broken)
        monkeypatch.setattr(deal_actions, "open_handover", lambda ctx, reason: opened.append(reason))
        out = run_shop([call("send_quote", item_ids=["sku-runner"])])
        assert out.handover and opened and out.quote_text is None

    def test_only_one_quote_per_turn(self, monkeypatch):
        shop = Shop(monkeypatch)
        out = run_shop([call("send_quote", item_ids=["sku-runner"])] * 2)
        assert len(shop.created) == 1 and len(out.refusals) == 1


class TestPaymentConcernBlocksLinks:
    def test_no_package_link_while_they_say_they_paid(self, world):
        run([call("select_offering", key="one_question")], NO_DETAILS_CONFIG)
        ctx = deal_actions.DealContext(config=NO_DETAILS_CONFIG, db=object(), lead_id=LEAD, tenant_id=TENANT,
                                       phone=PHONE, payment_concern=True)
        out = asyncio.run(deal_actions.apply_tool_calls([call("create_payment_link")], ctx))
        assert out.payment_link is None and out.refusals and not world.links

    def test_no_product_quote_while_they_say_they_paid(self, monkeypatch):
        shop = Shop(monkeypatch)
        ctx = deal_actions.DealContext(config={}, db=object(), lead_id=LEAD, tenant_id=TENANT, phone=PHONE,
                                       catalog=CATALOG, payment_concern=True)
        out = asyncio.run(deal_actions.apply_tool_calls([call("send_quote", item_ids=["sku-runner"])], ctx))
        assert out.quote_text is None and out.refusals and not shop.created


class TestAutoLinkWhenReady:
    def _run(self, calls, config, auto=True):
        ctx = deal_actions.DealContext(config=config, db=object(), lead_id=LEAD, tenant_id=TENANT, phone=PHONE)
        return asyncio.run(deal_actions.apply_tool_calls(calls, ctx, auto_link=auto))

    def test_choice_with_nothing_to_collect_gets_its_link_without_being_asked(self, world):
        out = self._run([call("select_offering", key="one_question")], NO_DETAILS_CONFIG)
        assert out.payment_link and world.links[0]["amount_paise"] == 4900

    def test_switching_package_gets_the_new_amounts_link(self, world):
        self._run([call("select_offering", key="one_question")], NO_DETAILS_CONFIG)
        out = self._run([call("select_offering", key="marriage")], NO_DETAILS_CONFIG)
        assert out.payment_link and world.links[-1]["amount_paise"] == 9900

    def test_last_detail_saved_gets_the_link(self, world):
        self._run([call("select_offering", key="one_question")], CONFIG)
        out = self._run([call("save_details", fields={"name": "Ravi", "birth_date": "12-03-1994"})], CONFIG)
        assert out.payment_link

    def test_nothing_when_details_are_still_missing(self, world):
        out = self._run([call("select_offering", key="one_question"), call("save_details", fields={"name": "R"})], CONFIG)
        assert out.payment_link is None and not world.links

    def test_not_during_detail_capture(self, world):
        out = self._run([call("select_offering", key="one_question")], NO_DETAILS_CONFIG, auto=False)
        assert out.payment_link is None and not world.links

    def test_one_link_when_the_model_also_asked(self, world):
        out = self._run([call("select_offering", key="one_question"), call("create_payment_link")], NO_DETAILS_CONFIG)
        assert out.payment_link and len(world.links) == 1

    def test_no_auto_link_on_a_payment_concern(self, world):
        ctx = deal_actions.DealContext(config=NO_DETAILS_CONFIG, db=object(), lead_id=LEAD, tenant_id=TENANT,
                                       phone=PHONE, payment_concern=True)
        out = asyncio.run(deal_actions.apply_tool_calls([call("select_offering", key="one_question")], ctx, auto_link=True))
        assert out.payment_link is None and not world.links
