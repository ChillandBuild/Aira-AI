"""Regenerates sdk/spec/vectors/*.json FROM THE REAL BACKEND.

The expected outputs are never hand-written: they are produced by running
backend/app/services/auto_messages.py (build_components, normalize_event,
parse_payload) and backend/app/routes/upload.py (_normalize_phone). Edit the
INPUTS below, run this, and commit the JSON diff. The backend test
backend/tests/test_private_send_vectors.py fails if the backend later drifts
from the committed vectors; the Python and Node plug-ins must pass them too.

Run:  cd backend && .venv/bin/python ../sdk/spec/generate_vectors.py
"""
import json
import os
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
BACKEND = os.path.abspath(os.path.join(HERE, "..", "..", "backend"))
sys.path.insert(0, BACKEND)

from app.routes.upload import _normalize_phone  # noqa: E402
from app.services.auto_messages import build_components, normalize_event, parse_payload  # noqa: E402

OUT = os.path.join(HERE, "vectors")


def tpl(**kw):
    base = {
        "name": "t", "language": "en", "body_text": "", "header_text": None,
        "header_media_type": None, "header_media_url": None, "buttons": [],
    }
    return {**base, **kw}


def rule(variables=None, button_param=None):
    return {"variables": variables, "button_param": button_param}


def ctx(first_name="Asha", full_name=None, page_url="", phone="+919876543210", extra=None):
    full = full_name if full_name is not None else (f"{first_name} Rao" if first_name else "")
    return {"first_name": first_name, "full_name": full, "page_url": page_url, "phone": phone, "extra": extra or {}}


URL_BTN = {"type": "URL", "text": "Track", "url": "https://shop.example.com/track/{{1}}"}

COMPONENT_CASES = [
    ("body_two_vars_defaults", rule(), tpl(body_text="Hi {{1}}, your order {{2}} is confirmed."), ctx()),
    ("body_one_var_default_first_name", rule(), tpl(body_text="Hi {{1}}, welcome!"), ctx()),
    ("body_explicit_variables_with_fallback", rule([
        {"source": "first_name", "fallback": "there"},
        {"source": "text", "value": "Order #42", "fallback": "-"},
        {"source": "extra", "key": " Plan ", "fallback": "basic"},
    ]), tpl(body_text="Hi {{1}}, {{2}} on {{3}}"), ctx(extra={"plan": "Gold"})),
    ("explicit_extra_missing_uses_fallback", rule([
        {"source": "first_name", "fallback": "there"},
        {"source": "extra", "key": "city", "fallback": "your city"},
    ]), tpl(body_text="{{1}} from {{2}}"), ctx()),
    ("explicit_full_name_phone_page_url", rule([
        {"source": "full_name", "fallback": "friend"},
        {"source": "phone", "fallback": "-"},
        {"source": "page_url", "fallback": "-"},
    ]), tpl(body_text="{{1}} {{2}} {{3}}"), ctx(page_url="https://shop.example.com/p/9")),
    ("missing_name_uses_fallback", rule([{"source": "first_name", "fallback": "there"}]),
     tpl(body_text="Hi {{1}}"), ctx(first_name="")),
    ("missing_name_no_fallback_uses_dash", rule(), tpl(body_text="Hi {{1}}"), ctx(first_name="")),
    ("null_variable_entry_uses_default", rule([None, {"source": "text", "value": "X"}]),
     tpl(body_text="{{1}} {{2}}"), ctx()),
    ("spec_without_source_uses_default", rule([{"fallback": "pal"}, {"value": "ignored"}]),
     tpl(body_text="{{1}} {{2}}"), ctx(first_name="")),
    ("fewer_specs_than_vars", rule([{"source": "full_name", "fallback": "x"}]),
     tpl(body_text="{{1}} {{2}} {{3}}"), ctx()),
    ("repeated_var_counts_once", rule(), tpl(body_text="{{1}} and again {{1}}"), ctx()),
    ("non_contiguous_vars_count_distinct", rule(), tpl(body_text="{{1}} and {{3}}"), ctx()),
    ("spaced_braces", rule(), tpl(body_text="Hi {{ 1 }}"), ctx()),
    ("no_variables", rule(), tpl(body_text="Thanks for contacting us."), ctx()),
    ("header_text_var", rule(), tpl(header_text="Hello {{1}}", body_text="Plain body"), ctx()),
    ("header_text_var_missing_name_there", rule(), tpl(header_text="Hello {{1}}", body_text="Plain body"), ctx(first_name="")),
    ("header_text_no_var_ignored", rule(), tpl(header_text="Static header", body_text="Plain body"), ctx()),
    ("header_image", rule(), tpl(header_media_type="IMAGE", header_media_url="https://cdn.example.com/a.jpg", body_text="Hi {{1}}"), ctx()),
    ("header_video", rule(), tpl(header_media_type="VIDEO", header_media_url="https://cdn.example.com/a.mp4", body_text="Hi"), ctx()),
    ("header_document", rule(), tpl(header_media_type="DOCUMENT", header_media_url="https://cdn.example.com/a.pdf", body_text="Hi"), ctx()),
    ("header_media_type_lowercase", rule(), tpl(header_media_type="image", header_media_url="https://cdn.example.com/a.jpg", body_text="Hi"), ctx()),
    ("header_media_without_url_no_header", rule(), tpl(header_media_type="IMAGE", header_media_url=None, body_text="Hi"), ctx()),
    ("header_media_wins_over_header_text", rule(), tpl(header_media_type="IMAGE", header_media_url="https://cdn.example.com/a.jpg", header_text="Hi {{1}}", body_text="Hi"), ctx()),
    ("header_media_type_none_falls_to_text", rule(), tpl(header_media_type="NONE", header_text="Hi {{1}}", body_text="Hi"), ctx()),
    ("button_dynamic_url_text_suffix", rule(button_param={"source": "text", "value": "ORD-42"}),
     tpl(body_text="Hi", buttons=[URL_BTN]), ctx()),
    ("button_dynamic_url_encoded_suffix", rule(button_param={"source": "text", "value": "order 42/ä?x=1&y=2 #frag%"}),
     tpl(body_text="Hi", buttons=[URL_BTN]), ctx()),
    ("button_dynamic_url_from_extra", rule(button_param={"source": "extra", "key": "order_id", "fallback": "none"}),
     tpl(body_text="Hi", buttons=[URL_BTN]), ctx(extra={"order_id": "A/B 7"})),
    ("button_dynamic_url_no_param_uses_dash", rule(), tpl(body_text="Hi", buttons=[URL_BTN]), ctx()),
    ("button_second_index_and_non_url_skipped", rule(button_param={"source": "text", "value": "x"}),
     tpl(body_text="Hi", buttons=[{"type": "QUICK_REPLY", "text": "Yes"}, URL_BTN,
                                  {"type": "URL", "text": "Static", "url": "https://example.com/static"},
                                  {"type": "url", "text": "Lower", "url": "https://example.com/{{1}}"}]), ctx()),
    ("link_in_first_name_replaced_by_fallback", rule([{"source": "first_name", "fallback": "there"}]),
     tpl(body_text="Hi {{1}}"), ctx(first_name="visit evil.com")),
    ("link_in_full_name_replaced", rule([{"source": "full_name", "fallback": "friend"}]),
     tpl(body_text="Hi {{1}}"), ctx(first_name="Asha", full_name="Asha http://x.io/win")),
    ("link_in_extra_replaced", rule([{"source": "extra", "key": "note", "fallback": "n/a"}]),
     tpl(body_text="{{1}}"), ctx(extra={"note": "see www.spam.top now"})),
    ("link_in_default_first_name_becomes_dash", rule(), tpl(body_text="Hi {{1}}"), ctx(first_name="Anna.co")),
    ("link_tld_boundary_cases", rule([
        {"source": "extra", "key": "a", "fallback": "FB"},
        {"source": "extra", "key": "b", "fallback": "FB"},
        {"source": "extra", "key": "c", "fallback": "FB"},
        {"source": "extra", "key": "d", "fallback": "FB"},
    ]), tpl(body_text="{{1}} {{2}} {{3}} {{4}}"),
     ctx(extra={"a": "report.pdf", "b": "Dr. Smith", "c": "shop.in", "d": "a-b.com"})),
    ("link_allowed_in_text_and_page_url", rule([
        {"source": "text", "value": "https://example.com/offer", "fallback": "-"},
        {"source": "page_url", "fallback": "-"},
    ]), tpl(body_text="{{1}} {{2}}"), ctx(page_url="https://example.com/landing")),
    ("newlines_tabs_flattened", rule([
        {"source": "full_name", "fallback": "-"},
        {"source": "text", "value": "line1\n\nline2\tcol   gap", "fallback": "-"},
    ]), tpl(body_text="{{1}} / {{2}}"), ctx(first_name="Asha", full_name="Asha\n\tRao   Kumar")),
    ("value_truncated_to_500", rule([{"source": "text", "value": "x" * 700, "fallback": "-"}]),
     tpl(body_text="{{1}}"), ctx()),
    ("fallback_is_cleaned", rule([{"source": "extra", "key": "k", "fallback": "a\n b\t c"}]),
     tpl(body_text="{{1}}"), ctx()),
    ("full_example_header_body_button", rule([{"source": "first_name", "fallback": "there"}, {"source": "text", "value": "INV 7"}],
                                              {"source": "text", "value": "INV 7"}),
     tpl(header_media_type="IMAGE", header_media_url="https://cdn.example.com/h.png", body_text="Hi {{1}}, invoice {{2}}", buttons=[URL_BTN]), ctx()),
]

EVENT_INPUTS = [
    None, "", "   ", "interested", "Interested", "  INTERESTED  ", "interest", "enquiry", "inquiry", "lead", "enquired",
    "signed_up", "signup", "sign_up", "sign-up", "Sign Up", "register", "registered", "registration",
    "purchased", "purchase", "order", "order_placed", "Order Placed", "ORDER-PLACED", "__order__placed__", "bought",
    "paid", "sale", "refund", "unknown", "purchas", "pur chase!", "signed up now",
    # custom event slugs: ^[a-z][a-z0-9_]{1,39}$ after trim + lowercase, no mapping invented for them
    "Refund", "  KYC_done  ", "cart_abandoned_2", "ab", "a" + "b" * 39,
    # junk that stays rejected
    "a", "1abc", "_abc", "abc-def", "abc def", "refund!", "a" + "b" * 40, "é", "ab\ncd", "-", "__",
]

PHONE_INPUTS = [
    "9876543210", "+919876543210", "919876543210", "09876543210", "0919876543210", "+91 98765 43210",
    "98765-43210", "(987) 654-3210", "  9876543210  ", "1234567890", "5876543210", "+14155552671",
    "14155552671", "+44 20 7946 0958", "00919876543210", "+1234567", "+12345678", "+1234567890123456",
    "+123456789012345", "123456789", "12345678", "1234567", "123456789012345", "1234567890123456",
    "abc", "", None, "+", "000", "+0", "98+76543210", "919876543210x", "+91-98765-43210 ext 5", "9123456789",
]

PARSE_INPUTS = [
    {"phone": "9876543210", "name": "Asha Rao", "event": "purchase", "page_url": "https://x.com/p"},
    {"Mobile Number": "x", "mobile_number": "9876543210", "Your_Name": "  Asha  ", "type": "signup"},
    {"whatsapp": "9876543210", "first_name": "Asha", "last_name": "Rao", "city": "Pune", "Plan": "Gold"},
    {"contact": "9876543210", "first_name": "Asha", "_hidden": "x", "empty": "", "nested": {"a": 1}, "list": [1], "n": 5},
    {"number": "9876543210", "name": "", "full_name": "Fallback Name", "url": "https://u.com", "link": "https://l.com"},
    {"phone": "9876543210", "customer_name": "C" * 300},
    {**{"phone": "9876543210"}, **{f"k{i:02d}": f"v{i}" for i in range(25)}},
    {"PHONE": " 9876543210 ", "Trigger": "Order", "ZZ" + "k" * 60: "long key"},
    {"mobile": None, "name": None, "flag": True, "zero": 0},
]


def write(name: str, doc: dict) -> None:
    os.makedirs(OUT, exist_ok=True)
    with open(os.path.join(OUT, name), "w", encoding="utf-8") as fh:
        json.dump(doc, fh, indent=2, ensure_ascii=False)
        fh.write("\n")


def main() -> None:
    components = [
        {"name": name, "rule": r, "template": t, "ctx": c, "expected_components": build_components(t, r, c)}
        for name, r, t, c in COMPONENT_CASES
    ]
    write("components.json", {
        "description": "build_components(template, rule, ctx) -> Meta template components. Generated from the backend.",
        "cases": components,
    })
    write("normalize.json", {
        "description": "events: [input, expected_or_null] via normalize_event (built-in aliases, or a custom slug ^[a-z][a-z0-9_]{1,39}$). phones: [input, expected_or_null] via _normalize_phone.",
        "events": [[e, normalize_event(e)] for e in EVENT_INPUTS],
        "phones": [[p, _normalize_phone(p)] for p in PHONE_INPUTS],
    })
    write("parse.json", {
        "description": "parse_payload(payload) -> {phone, name, event_raw, page_url, extra}. Generated from the backend.",
        "cases": [{"name": f"parse_{i}", "payload": p, "expected": parse_payload(p)} for i, p in enumerate(PARSE_INPUTS)],
    })
    print(f"wrote {len(components)} component cases, {len(EVENT_INPUTS)} events, {len(PHONE_INPUTS)} phones, {len(PARSE_INPUTS)} parse cases")


if __name__ == "__main__":
    main()
