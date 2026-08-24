# Intake Package Buttons Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Replace the typed package choice in the intake flow with tappable WhatsApp reply buttons.

**Architecture:** The sending function (`send_interactive_buttons`) and the receiving path (the webhook normalising a tap into text) both already exist. This plan adds the missing middle: an eligibility helper that decides when buttons are usable, a send-and-log wrapper that falls back to text on any failure, wiring at the two places the package list is asked, and a per-package short-label field in the settings UI.

**Tech Stack:** FastAPI (`backend/app/`), pytest + `unittest.mock`, Next.js 14 (`frontend/app/dashboard/`), Supabase, WhatsApp Cloud API.

**Spec:** [docs/superpowers/specs/2026-08-24-intake-package-buttons-design.md](../specs/2026-08-24-intake-package-buttons-design.md)

## Global Constraints

- WhatsApp reply buttons: **max 3 per message**, **title max 20 characters**.
- WhatsApp interactive body text: **max 1024 characters**.
- Package prices are rendered in Python, **never** by the LLM, and **never** on a button title.
- `_send_and_log`'s contract holds for any new send helper: **a logging failure must never raise**, or `route_intake`'s caller treats the turn as unconsumed and `generate_reply()` sends a second reply on top of the one already delivered.
- Intake is WhatsApp-only (`_send_and_log` hardcodes `"channel": "whatsapp"`). No other channel needs handling.
- Backend tests: `cd backend && pytest`. Frontend verification is **both** `npm run lint` and `npm run typecheck` — CI runs lint, and tsc alone passes code that lint rejects.
- Do not `git push`. Local commits only.

---

### Task 1: Make `send_interactive_buttons` reject over-long titles

Silent truncation is the failure this whole feature steers around. The function has zero callers today, so tightening it is safe.

**Files:**
- Modify: `backend/app/services/meta_cloud.py:606-638`
- Test: `backend/tests/test_meta_cloud_interactive_buttons.py` (create)

**Interfaces:**
- Consumes: nothing.
- Produces: `send_interactive_buttons(to_number, body_text, buttons, phone_number_id=None, access_token=None, tenant_id=None) -> dict` — raises `ValueError` on a button title longer than 20 characters or a `buttons` list that is empty or longer than 3. `buttons` items are `{"id": str, "title": str}`.

- [ ] **Step 1: Write the failing tests**

Create `backend/tests/test_meta_cloud_interactive_buttons.py`:

```python
import sys
import unittest
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock, patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import pytest

from app.services.meta_cloud import send_interactive_buttons


@pytest.mark.asyncio
async def test_send_interactive_buttons_rejects_long_title():
    with pytest.raises(ValueError, match="20 characters"):
        await send_interactive_buttons(
            to_number="+919000000000",
            body_text="Pick one",
            buttons=[{"id": "a", "title": "Detailed Consultation"}],  # 21 chars
            tenant_id="tenant-1",
        )


@pytest.mark.asyncio
async def test_send_interactive_buttons_rejects_too_many():
    with pytest.raises(ValueError, match="3 buttons"):
        await send_interactive_buttons(
            to_number="+919000000000",
            body_text="Pick one",
            buttons=[{"id": str(i), "title": f"B{i}"} for i in range(4)],
            tenant_id="tenant-1",
        )


@pytest.mark.asyncio
async def test_send_interactive_buttons_rejects_empty():
    with pytest.raises(ValueError, match="at least one"):
        await send_interactive_buttons(
            to_number="+919000000000",
            body_text="Pick one",
            buttons=[],
            tenant_id="tenant-1",
        )


@pytest.mark.asyncio
async def test_send_interactive_buttons_sends_valid_payload():
    mock_response = MagicMock()
    mock_response.is_success = True
    mock_response.json.return_value = {"messages": [{"id": "wamid.1"}]}

    with patch("httpx.AsyncClient") as MockClient:
        instance = MockClient.return_value.__aenter__.return_value
        instance.post = AsyncMock(return_value=mock_response)
        with patch("app.services.meta_cloud._creds", return_value=("pid-1", "tok-1")):
            result = await send_interactive_buttons(
                to_number="+919000000000",
                body_text="Pick one",
                buttons=[{"id": "basic", "title": "One Question"}],
                tenant_id="tenant-1",
            )

    assert result["messages"][0]["id"] == "wamid.1"
    payload = instance.post.call_args.kwargs["json"]
    assert payload["interactive"]["action"]["buttons"] == [
        {"type": "reply", "reply": {"id": "basic", "title": "One Question"}}
    ]
```

- [ ] **Step 2: Run the tests to verify they fail**

Run: `cd backend && pytest tests/test_meta_cloud_interactive_buttons.py -v`

Expected: the three `raises` tests FAIL (no `ValueError` raised — the current code truncates instead).

- [ ] **Step 3: Add validation**

In `backend/app/services/meta_cloud.py`, add near the other module constants at the top:

```python
BUTTON_TITLE_MAX = 20
BUTTON_COUNT_MAX = 3
```

Then in `send_interactive_buttons`, insert immediately after the `pid, tok = _creds(...)` line:

```python
    if not buttons:
        raise ValueError("send_interactive_buttons needs at least one button")
    if len(buttons) > BUTTON_COUNT_MAX:
        raise ValueError(f"WhatsApp allows at most {BUTTON_COUNT_MAX} buttons, got {len(buttons)}")
    for b in buttons:
        if len(b["title"]) > BUTTON_TITLE_MAX:
            raise ValueError(
                f"Button title {b['title']!r} exceeds {BUTTON_TITLE_MAX} characters — "
                "WhatsApp truncates silently, so callers must shorten it first"
            )
```

And replace the truncating comprehension:

```python
                "buttons": [
                    {"type": "reply", "reply": {"id": b["id"], "title": b["title"][:20]}}
                    for b in buttons[:3]
                ],
```

with:

```python
                "buttons": [
                    {"type": "reply", "reply": {"id": b["id"], "title": b["title"]}}
                    for b in buttons
                ],
```

- [ ] **Step 4: Run the tests to verify they pass**

Run: `cd backend && pytest tests/test_meta_cloud_interactive_buttons.py -v`

Expected: 4 passed.

- [ ] **Step 5: Commit**

```bash
git add backend/app/services/meta_cloud.py backend/tests/test_meta_cloud_interactive_buttons.py
git commit -m "fix(meta): reject over-long button titles instead of truncating silently"
```

---

### Task 2: Package button eligibility helper

**Files:**
- Modify: `backend/app/services/intake.py` (add after `package_list_message`, around line 325)
- Test: `backend/tests/test_intake_package_buttons.py` (create)

**Interfaces:**
- Consumes: `BUTTON_TITLE_MAX` from Task 1.
- Produces:
  - `package_button_title(pkg: dict) -> str | None` — the title to show, or `None` if this package cannot be a button.
  - `package_buttons(packages: list[dict]) -> list[dict] | None` — `[{"id": key, "title": title}, ...]` or `None` when buttons are not usable for this set.

- [ ] **Step 1: Write the failing tests**

Create `backend/tests/test_intake_package_buttons.py`:

```python
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from app.services.intake import package_button_title, package_buttons


def _pkg(key, name, button_label=None):
    p = {"key": key, "name": name, "amount_paise": 10000, "description": ""}
    if button_label is not None:
        p["button_label"] = button_label
    return p


def test_title_uses_name_when_short_enough():
    assert package_button_title(_pkg("basic", "One Question")) == "One Question"


def test_title_prefers_button_label_over_name():
    assert package_button_title(_pkg("det", "Detailed Consultation", "Detailed")) == "Detailed"


def test_title_none_when_name_too_long_and_no_label():
    assert package_button_title(_pkg("det", "Detailed Consultation")) is None


def test_title_none_when_button_label_itself_too_long():
    assert package_button_title(_pkg("det", "Short", "A" * 21)) is None


def test_title_none_when_name_blank():
    assert package_button_title(_pkg("det", "   ")) is None


def test_buttons_none_for_single_package():
    assert package_buttons([_pkg("a", "One Question")]) is None


def test_buttons_none_for_four_packages():
    pkgs = [_pkg(f"k{i}", f"Name {i}") for i in range(4)]
    assert package_buttons(pkgs) is None


def test_buttons_none_when_empty():
    assert package_buttons([]) is None


def test_buttons_for_two_packages():
    pkgs = [_pkg("basic", "One Question"), _pkg("det", "Detailed Consultation", "Detailed")]
    assert package_buttons(pkgs) == [
        {"id": "basic", "title": "One Question"},
        {"id": "det", "title": "Detailed"},
    ]


def test_buttons_for_three_packages():
    pkgs = [_pkg("a", "Basic"), _pkg("b", "Standard"), _pkg("c", "Premium")]
    assert package_buttons(pkgs) == [
        {"id": "a", "title": "Basic"},
        {"id": "b", "title": "Standard"},
        {"id": "c", "title": "Premium"},
    ]


def test_buttons_none_when_any_package_ineligible():
    pkgs = [_pkg("a", "Basic"), _pkg("b", "Detailed Consultation")]
    assert package_buttons(pkgs) is None
```

- [ ] **Step 2: Run the tests to verify they fail**

Run: `cd backend && pytest tests/test_intake_package_buttons.py -v`

Expected: FAIL at import — `cannot import name 'package_button_title'`.

- [ ] **Step 3: Implement the helpers**

First, add the import to the module header in `backend/app/services/intake.py`, alongside
the existing `from app.services.gemini_client import ...` line (verified safe: `meta_cloud`
imports only `app.config`/`app.config_dynamic`, so there is no cycle — unlike `ai_reply`,
which `_send_and_log` deliberately imports lazily inside the function):

```python
from app.services.meta_cloud import BUTTON_COUNT_MAX, BUTTON_TITLE_MAX
```

Then add the helpers immediately after `package_list_message` (which ends around line 325):

```python
# WhatsApp caps reply buttons at 3 per message and 20 characters per title, and
# truncates over-long titles without erroring. Prices are deliberately never put on
# a button -- they would not survive the 20-character limit, and they stay in the
# body text where package_list_block renders them in Python.
_BUTTON_PACKAGE_MIN = 2


def package_button_title(pkg: dict) -> str | None:
    """The reply-button title for one package, or None if it cannot be a button.

    Prefers an explicit `button_label` so a tenant can shorten a long package name;
    falls back to `name` when that already fits.
    """
    label = (pkg.get("button_label") or "").strip()
    if label:
        return label if len(label) <= BUTTON_TITLE_MAX else None
    name = (pkg.get("name") or "").strip()
    if name and len(name) <= BUTTON_TITLE_MAX:
        return name
    return None


def package_buttons(packages: list[dict]) -> list[dict] | None:
    """Reply buttons for the package picker, or None to fall back to a text list.

    All-or-nothing: one ineligible package sends the whole set to text rather than
    showing a partial menu that hides an option the lead can pay for.
    """
    if not (_BUTTON_PACKAGE_MIN <= len(packages) <= BUTTON_COUNT_MAX):
        return None
    out: list[dict] = []
    for p in packages:
        title = package_button_title(p)
        if not title:
            return None
        out.append({"id": p["key"], "title": title})
    return out
```

- [ ] **Step 4: Run the tests to verify they pass**

Run: `cd backend && pytest tests/test_intake_package_buttons.py -v`

Expected: 11 passed.

- [ ] **Step 5: Commit**

```bash
git add backend/app/services/intake.py backend/tests/test_intake_package_buttons.py
git commit -m "feat(intake): add package reply-button eligibility helpers"
```

---

### Task 3: Match a tapped `button_label` without the LLM

`match_package` short-circuits on an exact `name` or `key` match before calling the LLM. A tenant who sets `button_label: "Detailed"` gets a tapped reply of `"Detailed"`, which matches neither — silently falling through to the LLM and losing the determinism buttons exist to provide.

**Files:**
- Modify: `backend/app/services/intake.py:346-349`
- Test: `backend/tests/test_intake_package_buttons.py` (append)

**Interfaces:**
- Consumes: `match_package(message, packages, tenant_id) -> dict | None` (existing).
- Produces: same signature; exact-match short-circuit now also covers `button_label`.

- [ ] **Step 1: Write the failing tests**

Append to `backend/tests/test_intake_package_buttons.py`:

```python
from unittest.mock import AsyncMock, patch

import pytest

from app.services.intake import match_package


@pytest.mark.asyncio
async def test_match_package_matches_button_label_without_llm():
    pkgs = [_pkg("basic", "One Question"), _pkg("det", "Detailed Consultation", "Detailed")]
    with patch("app.services.intake.gemini_chat_completion_json", new=AsyncMock()) as llm:
        result = await match_package("Detailed", pkgs, "tenant-1")
    assert result["key"] == "det"
    llm.assert_not_called()


@pytest.mark.asyncio
async def test_match_package_button_label_is_case_insensitive():
    pkgs = [_pkg("basic", "One Question"), _pkg("det", "Detailed Consultation", "Detailed")]
    with patch("app.services.intake.gemini_chat_completion_json", new=AsyncMock()) as llm:
        result = await match_package("  detailed  ", pkgs, "tenant-1")
    assert result["key"] == "det"
    llm.assert_not_called()


@pytest.mark.asyncio
async def test_match_package_still_matches_name_without_llm():
    pkgs = [_pkg("basic", "One Question"), _pkg("det", "Detailed Consultation", "Detailed")]
    with patch("app.services.intake.gemini_chat_completion_json", new=AsyncMock()) as llm:
        result = await match_package("One Question", pkgs, "tenant-1")
    assert result["key"] == "basic"
    llm.assert_not_called()
```

- [ ] **Step 2: Run the tests to verify they fail**

Run: `cd backend && pytest tests/test_intake_package_buttons.py -k match_package -v`

Expected: `test_match_package_matches_button_label_without_llm` and the case-insensitive one FAIL (the LLM mock gets called, and the `AsyncMock` return has no usable `key`). The `name` test passes already.

- [ ] **Step 3: Extend the short-circuit**

In `backend/app/services/intake.py`, replace the loop at lines 346-349:

```python
    cleaned = message.strip().lower()
    for p in packages:
        if cleaned == p["name"].strip().lower() or cleaned == p["key"].strip().lower():
            return dict(p)
```

with:

```python
    cleaned = message.strip().lower()
    for p in packages:
        # button_label is included because a tapped reply button sends its title
        # back verbatim -- without this a shortened label misses the short-circuit
        # and burns an LLM call to re-derive what the tap already told us exactly.
        candidates = [p["name"], p["key"], p.get("button_label") or ""]
        if any(cleaned == c.strip().lower() for c in candidates if c and c.strip()):
            return dict(p)
```

- [ ] **Step 4: Run the tests to verify they pass**

Run: `cd backend && pytest tests/test_intake_package_buttons.py -v`

Expected: 14 passed.

- [ ] **Step 5: Commit**

```bash
git add backend/app/services/intake.py backend/tests/test_intake_package_buttons.py
git commit -m "feat(intake): exact-match tapped button labels without the LLM matcher"
```

---

### Task 4: `_send_buttons_and_log` with text fallback

**Files:**
- Modify: `backend/app/services/intake.py` (add after `_send_and_log`, which ends around line 445)
- Test: `backend/tests/test_intake_package_buttons.py` (append)

**Interfaces:**
- Consumes: `_send_and_log(phone, text, tenant_id, lead_id, db)` (existing), `send_interactive_buttons` from Task 1.
- Produces: `_send_buttons_and_log(phone, text, buttons, tenant_id, lead_id, db) -> None` — never raises.

- [ ] **Step 1: Write the failing tests**

Append to `backend/tests/test_intake_package_buttons.py`:

```python
from unittest.mock import MagicMock

from app.services.intake import _send_buttons_and_log

_BUTTONS = [{"id": "basic", "title": "One Question"}, {"id": "det", "title": "Detailed"}]


def _fake_db():
    db = MagicMock()
    db.table.return_value.insert.return_value.execute.return_value = MagicMock()
    return db


@pytest.mark.asyncio
async def test_send_buttons_logs_body_and_labels():
    db = _fake_db()
    send = AsyncMock(return_value={"messages": [{"id": "wamid.9"}]})
    with patch("app.services.meta_cloud.send_interactive_buttons", new=send):
        await _send_buttons_and_log("+919000000000", "Pick one", _BUTTONS, "t1", "l1", db)

    send.assert_awaited_once()
    logged = db.table.return_value.insert.call_args[0][0]
    assert logged["content"] == "Pick one\n\n[One Question] [Detailed]"
    assert logged["meta_message_id"] == "wamid.9"
    assert logged["channel"] == "whatsapp"
    assert logged["reply_source"] == "expert_handoff"


@pytest.mark.asyncio
async def test_send_buttons_falls_back_to_text_when_send_fails():
    db = _fake_db()
    send = AsyncMock(side_effect=RuntimeError("meta down"))
    fallback = AsyncMock()
    with patch("app.services.meta_cloud.send_interactive_buttons", new=send):
        with patch("app.services.intake._send_and_log", new=fallback):
            await _send_buttons_and_log("+919000000000", "Pick one", _BUTTONS, "t1", "l1", db)

    fallback.assert_awaited_once_with("+919000000000", "Pick one", "t1", "l1", db)


@pytest.mark.asyncio
async def test_send_buttons_falls_back_when_body_too_long():
    db = _fake_db()
    long_body = "x" * 1025
    send = AsyncMock()
    fallback = AsyncMock()
    with patch("app.services.meta_cloud.send_interactive_buttons", new=send):
        with patch("app.services.intake._send_and_log", new=fallback):
            await _send_buttons_and_log("+919000000000", long_body, _BUTTONS, "t1", "l1", db)

    send.assert_not_awaited()
    fallback.assert_awaited_once()


@pytest.mark.asyncio
async def test_send_buttons_never_raises_when_logging_fails():
    db = MagicMock()
    db.table.return_value.insert.return_value.execute.side_effect = RuntimeError("constraint")
    send = AsyncMock(return_value={"messages": [{"id": "wamid.9"}]})
    with patch("app.services.meta_cloud.send_interactive_buttons", new=send):
        await _send_buttons_and_log("+919000000000", "Pick one", _BUTTONS, "t1", "l1", db)
    # No assertion needed: the test fails if this raises.
```

- [ ] **Step 2: Run the tests to verify they fail**

Run: `cd backend && pytest tests/test_intake_package_buttons.py -k send_buttons -v`

Expected: FAIL at import — `cannot import name '_send_buttons_and_log'`.

- [ ] **Step 3: Implement the helper**

In `backend/app/services/intake.py`, add immediately after `_send_and_log`:

```python
# WhatsApp's interactive body cap. Over this the API rejects the message, so fall
# back to a plain text list rather than lose the turn.
_WA_INTERACTIVE_BODY_MAX = 1024


async def _send_buttons_and_log(
    phone: str, text: str, buttons: list[dict], tenant_id: str, lead_id: str, db
) -> None:
    """Send `text` as a WhatsApp interactive button message, then log it.

    Carries _send_and_log's guarantee: this never raises. A failure to send falls
    back to the plain text list, and a failure to log is swallowed -- either one
    escaping would make route_intake's caller treat the turn as unconsumed and send
    a second, unrelated reply on top of one the customer already received.
    """
    from app.services.meta_cloud import send_interactive_buttons

    if len(text) > _WA_INTERACTIVE_BODY_MAX:
        await _send_and_log(phone, text, tenant_id, lead_id, db)
        return

    try:
        data = await send_interactive_buttons(
            to_number=phone, body_text=text, buttons=buttons, tenant_id=tenant_id
        )
    except Exception:
        logger.exception("Intake package buttons send failed, falling back to text list")
        await _send_and_log(phone, text, tenant_id, lead_id, db)
        return

    mid = (data.get("messages") or [{}])[0].get("id")
    # Log the labels alongside the body so the thread the AI reads back, and the
    # operator inbox, both show what the lead was actually offered.
    logged = text + "\n\n" + " ".join(f"[{b['title']}]" for b in buttons)
    try:
        db.table("messages").insert({
            "lead_id": lead_id,
            "tenant_id": tenant_id,
            "direction": "outbound",
            "channel": "whatsapp",
            "content": logged,
            "is_ai_generated": True,
            "meta_message_id": mid,
            "reply_source": "expert_handoff",
        }).execute()
    except Exception:
        logger.exception(
            "Failed to log intake package button message for lead %s", lead_id
        )
```

- [ ] **Step 4: Run the tests to verify they pass**

Run: `cd backend && pytest tests/test_intake_package_buttons.py -v`

Expected: 18 passed.

- [ ] **Step 5: Commit**

```bash
git add backend/app/services/intake.py backend/tests/test_intake_package_buttons.py
git commit -m "feat(intake): add button send helper with text fallback"
```

---

### Task 5: Wire buttons into both package-ask sites

Two places ask the lead to choose: the first ask, and the re-ask after a failed match. A lead who already failed to match once is exactly who benefits most from tapping, so both get buttons.

**Files:**
- Modify: `backend/app/services/intake.py:566-577` (first ask) and `:585-593` (re-ask)
- Test: `backend/tests/test_intake_package_buttons.py` (append)

**Interfaces:**
- Consumes: `package_buttons` (Task 2), `_send_buttons_and_log` (Task 4).
- Produces: no new public names.

- [ ] **Step 1: Write the failing tests**

Append to `backend/tests/test_intake_package_buttons.py`:

```python
from app.services.intake import _dispatch_package_ask


@pytest.mark.asyncio
async def test_dispatch_uses_buttons_when_eligible():
    db = _fake_db()
    pkgs = [_pkg("basic", "One Question"), _pkg("det", "Detailed Consultation", "Detailed")]
    btn = AsyncMock()
    txt = AsyncMock()
    with patch("app.services.intake._send_buttons_and_log", new=btn):
        with patch("app.services.intake._send_and_log", new=txt):
            await _dispatch_package_ask("+919000000000", "Pick one", pkgs, "t1", "l1", db)

    btn.assert_awaited_once()
    txt.assert_not_awaited()
    assert btn.call_args[0][2] == [
        {"id": "basic", "title": "One Question"},
        {"id": "det", "title": "Detailed"},
    ]


@pytest.mark.asyncio
async def test_dispatch_uses_text_when_four_packages():
    db = _fake_db()
    pkgs = [_pkg(f"k{i}", f"Name {i}") for i in range(4)]
    btn = AsyncMock()
    txt = AsyncMock()
    with patch("app.services.intake._send_buttons_and_log", new=btn):
        with patch("app.services.intake._send_and_log", new=txt):
            await _dispatch_package_ask("+919000000000", "Pick one", pkgs, "t1", "l1", db)

    txt.assert_awaited_once_with("+919000000000", "Pick one", "t1", "l1", db)
    btn.assert_not_awaited()
```

- [ ] **Step 2: Run the tests to verify they fail**

Run: `cd backend && pytest tests/test_intake_package_buttons.py -k dispatch -v`

Expected: FAIL at import — `cannot import name '_dispatch_package_ask'`.

- [ ] **Step 3: Add the dispatcher**

In `backend/app/services/intake.py`, add immediately after `_send_buttons_and_log`:

```python
async def _dispatch_package_ask(
    phone: str, text: str, packages: list[dict], tenant_id: str, lead_id: str, db
) -> None:
    """Send an already-composed package question as buttons when eligible, else text."""
    buttons = package_buttons(packages)
    if buttons:
        await _send_buttons_and_log(phone, text, buttons, tenant_id, lead_id, db)
    else:
        await _send_and_log(phone, text, tenant_id, lead_id, db)
```

- [ ] **Step 4: Route the first ask through it**

In the `status == "offer_pending"` branch, replace lines 566-577:

```python
            _update_session(session["id"], {"status": "awaiting_package_choice"}, db)
            await _send_and_log(
                phone,
                await compose_wrapped(
                    "packages",
                    tenant_id=tenant_id,
                    language_mode=language_mode,
                    customer_message=body,
                    block=package_list_block(packages),
                    thread=thread,
                ),
                tenant_id, lead_id, db,
            )
            return True
```

with:

```python
            _update_session(session["id"], {"status": "awaiting_package_choice"}, db)
            packages_text = await compose_wrapped(
                "packages",
                tenant_id=tenant_id,
                language_mode=language_mode,
                customer_message=body,
                block=package_list_block(packages),
                thread=thread,
            )
            await _dispatch_package_ask(phone, packages_text, packages, tenant_id, lead_id, db)
            return True
```

- [ ] **Step 5: Route the re-ask through it**

In the `status == "awaiting_package_choice"` branch, replace the `chosen is None` send at lines 585-593:

```python
                await _send_and_log(
                    phone,
                    f"{intro}\n\n{package_list_block(packages)}",
                    tenant_id, lead_id, db,
                )
                return True
```

with:

```python
                await _dispatch_package_ask(
                    phone,
                    f"{intro}\n\n{package_list_block(packages)}",
                    packages, tenant_id, lead_id, db,
                )
                return True
```

- [ ] **Step 6: Run the full backend suite**

Run: `cd backend && pytest -q`

Expected: all pass, no regressions in existing intake tests.

- [ ] **Step 7: Commit**

```bash
git add backend/app/services/intake.py backend/tests/test_intake_package_buttons.py
git commit -m "feat(intake): send package picker as reply buttons when eligible"
```

---

### Task 6: Short-label field in the intake settings UI

**Files:**
- Modify: `frontend/app/dashboard/settings/IntakeConfigPanel.tsx` — interface at `:17-22`, editor rows at `:194-232`

**Interfaces:**
- Consumes: nothing from earlier tasks (the backend reads `button_label` defensively via `.get()`).
- Produces: `IntakePackage.button_label?: string` on the `intake_config` JSON blob.

- [ ] **Step 1: Add the field to the interface**

Replace the interface at `:17-22`:

```ts
interface IntakePackage {
  key: string;
  name: string;
  amount_paise: number;
  description: string;
}
```

with:

```ts
// WhatsApp truncates reply-button titles past 20 chars without erroring, so a
// package whose name is longer needs an explicit short label or it drops out of
// the button menu entirely.
const BUTTON_TITLE_MAX = 20;
const BUTTON_COUNT_MAX = 3;

interface IntakePackage {
  key: string;
  name: string;
  amount_paise: number;
  description: string;
  button_label?: string;
}
```

- [ ] **Step 2: Add the input to each package row**

In the `draft.packages.map(...)` block, insert directly after the description `<input>` (before the closing `</div>` of the package card at `:231`):

```tsx
                <div className="flex items-center gap-2">
                  <input
                    type="text"
                    value={pkg.button_label ?? ""}
                    onChange={(e) =>
                      updatePackage(index, { button_label: e.target.value.slice(0, BUTTON_TITLE_MAX) })
                    }
                    placeholder={
                      pkg.name.length > BUTTON_TITLE_MAX
                        ? "Short button label (required — name is too long)"
                        : "Short button label (optional)"
                    }
                    disabled={!canManage}
                    className="flex-1 px-3 py-1.5 rounded-lg border border-border text-sm font-body text-ink bg-white"
                  />
                  <span
                    className={`font-label text-xs tabular-nums ${
                      (pkg.button_label ?? "").length >= BUTTON_TITLE_MAX
                        ? "text-red-600"
                        : "text-ink-muted"
                    }`}
                  >
                    {(pkg.button_label ?? "").length}/{BUTTON_TITLE_MAX}
                  </span>
                </div>
```

- [ ] **Step 3: Add the eligibility notice**

Insert directly after the closing `))}` of the packages `.map()` and before the `draft.packages.length === 0` block at `:233`:

```tsx
            {draft.packages.length > BUTTON_COUNT_MAX && (
              <p className="font-body text-xs text-ink-muted">
                With more than {BUTTON_COUNT_MAX} packages, WhatsApp can&apos;t show tap buttons —
                leads will see the priced list as text and type their choice.
              </p>
            )}
            {draft.packages.length >= 2 &&
              draft.packages.length <= BUTTON_COUNT_MAX &&
              draft.packages.some(
                (p) => !(p.button_label ?? "").trim() && p.name.length > BUTTON_TITLE_MAX,
              ) && (
                <p className="font-body text-xs text-amber-700">
                  One or more package names are longer than {BUTTON_TITLE_MAX} characters and have no
                  short button label — leads will see the text list instead of tap buttons.
                </p>
              )}
```

- [ ] **Step 4: Verify with lint and typecheck**

Run both — CI runs lint, and tsc alone passes code lint rejects:

```bash
cd frontend && npm run lint && npm run typecheck
```

Expected: both clean.

- [ ] **Step 5: Commit**

```bash
git add frontend/app/dashboard/settings/IntakeConfigPanel.tsx
git commit -m "feat(intake-config): add per-package short button label with eligibility hints"
```

---

### Task 7: Live verification on a real number

Automated tests cannot prove Meta accepts the payload or that a tap round-trips. Per the repo's standing rule, a code path is not proof the product has the behaviour.

**Files:** none — manual.

- [ ] **Step 1: Configure two packages**

In the dashboard, set intake packages to exactly two, one with a name over 20 characters plus a short button label (e.g. `Detailed Consultation` / `Detailed`).

- [ ] **Step 2: Trigger the offer and accept it**

From a test WhatsApp number, send the message that triggers intake, then reply affirmatively.

- [ ] **Step 3: Confirm the button message**

Expected: the priced list arrives as text in the bubble body, with two tappable buttons beneath it. The long-named package shows as `Detailed`, not `Detailed Consultatio`.

- [ ] **Step 4: Tap a button and confirm the session advances**

Expected: the session moves from `awaiting_package_choice` to `collecting` (or `awaiting_confirmation` if no fields are missing), and the chosen package is snapshotted on the row.

- [ ] **Step 5: Confirm the LLM matcher was skipped**

Check backend logs for the turn: there must be **no** `intake_package_match` LLM call. The tapped label hit the exact-match short-circuit from Task 3.

- [ ] **Step 6: Confirm the fallback**

Add a fourth package and repeat from Step 2. Expected: the picker arrives as plain text with no buttons, and typing a choice still works exactly as before.

---

## Notes for the nested-packages plan

Recorded in the spec's section 9 and repeated here because the two plans touch the same config shape:

- The recursive node shape must carry `button_label` on every node.
- `package_buttons()` will need revisiting to read whichever tree level is currently being asked.
- Buttons stay one level at a time. A button configured to open another button set is the Bot Flow Builder removed on 2026-06-01 and is out of scope.
