"""Any question with options goes out with tappable options, never as bare text.

The model ends a message that asks the customer to pick with one line:
    CHOICES: Morning | Evening
Code removes that line and attaches the options in one fixed shape: two options are WhatsApp
reply buttons, three to ten are a list (the bar under the message that opens the options),
and one link is a URL button. More than ten keep the first ten. When the model forgets the
line but still writes its options as a numbered or bulleted list under a question, the list
itself becomes the options (the backstop). Channels without buttons get the options written
out instead.

The model has three ways to offer choices, most reliable first: the offer_choices tool
(it writes the message and the options in one call), the CHOICES line, and plain options
the backstops recognise (a list under a question, or "Morning, Afternoon or Evening?").
A reply that still asks for a pick but matches none of these goes to classify(), one small
timed-out model call that fails open to plain text.

Every WhatsApp limit is applied here before anything is sent (meta_cloud checks them again).
Pure functions only, apart from classify(); deal_turn.converse_once applies them to every reply.
"""
import asyncio
import base64
import binascii
import json
import logging
import re
from typing import NamedTuple

logger = logging.getLogger(__name__)

MARKER = "CHOICES"
BUTTON_TITLE_MAX = 20  # WhatsApp reply button title limit
REPLY_BUTTON_COUNT = 2  # two options sit under the message as buttons; more go in a list
LIST_ROW_TITLE_MAX = 24
LIST_ROW_DESCRIPTION_MAX = 72
LIST_ROW_COUNT_MAX = 10
LIST_ROW_ID_MAX = 200
LIST_LABEL_MAX = 20
OPTION_MAX_CHARS = 72  # longer than this is a sentence, not an option
ID_PREFIX = "choice:"
DETAIL_ID_PREFIX = f"{ID_PREFIX}detail:"
INTERACTIVE_ID_MAX = 256
INTERACTIVE_BODY_MAX = 1024
LINK_URL_MAX = 2000

_MARKER_RE = re.compile(r"^[ \t>*_`]*CHOICES?[ \t*_`]*[:：][ \t]*(.*?)[ \t*_`]*$", re.IGNORECASE | re.MULTILINE)
_LIST_ITEM_RE = re.compile(
    r"^[ \t]*(?:[-•*▪►‣◦]|\d{1,2}[.)]|\d️⃣|[a-hA-H][.)])[ \t]+(.+?)[ \t]*$"
)
# A question that asks the customer to pick, in English and romanised Tamil/Hindi.
PICK_CUE_RE = re.compile(
    r"\b(which|choose|pick|select|prefer|option|options|or|edhu|ethu|endha|entha|konsa|kaunsa|"
    r"edhula|ethula|illa|illana|allathu|venuma|vendumaa?)\b|எது|எந்த|அல்லது",
    re.IGNORECASE,
)


def _clean_option(raw: str) -> str:
    text = re.sub(r"[*_`]+", "", raw).strip(" \t-–—:;,.")
    return re.sub(r"\s+", " ", text)


def _unique(options: list[str]) -> list[str]:
    seen, out = set(), []
    for option in options:
        key = option.lower()
        if option and key not in seen:
            seen.add(key)
            out.append(option)
    return out


def _from_marker(text: str) -> tuple[str, list[str]] | None:
    matches = list(_MARKER_RE.finditer(text))
    if not matches:
        return None
    options: list[str] = []
    for match in matches:
        options += [_clean_option(part) for part in re.split(r"\s*[|｜]\s*", match.group(1))]
    body = _MARKER_RE.sub("", text)
    body = re.sub(r"\n{3,}", "\n\n", body).strip()
    return body, _unique([o for o in options if o])


def _asks(line: str) -> bool:
    """A question, or a lead-in to the options ("Please choose one:")."""
    stripped = line.strip()
    return "?" in stripped or "？" in stripped or stripped.endswith(":")


def _from_list(text: str) -> tuple[str, list[str]] | None:
    """The backstop: one block of 2-10 consecutive list lines, with a picking question
    right before or after it. Longer items are descriptions, not options, and a list with
    no picking question is information ("what's included"), so both are left alone."""
    lines = text.split("\n")
    blocks: list[tuple[int, int]] = []
    start = None
    for i, line in enumerate(lines + [""]):
        if i < len(lines) and _LIST_ITEM_RE.match(line):
            start = i if start is None else start
        elif start is not None:
            blocks.append((start, i))
            start = None
    if len(blocks) != 1:
        return None
    first, end = blocks[0]
    items = [_clean_option(_LIST_ITEM_RE.match(lines[i]).group(1)) for i in range(first, end)]
    if not 2 <= len(items) <= LIST_ROW_COUNT_MAX or any(len(item) > OPTION_MAX_CHARS for item in items):
        return None
    before = [line for line in lines[:first] if line.strip()]
    after = [line for line in lines[end:] if line.strip()]
    asks = [line for line in before[-1:] + after if _asks(line)]
    if not any(PICK_CUE_RE.search(line) for line in asks):
        return None
    body = "\n".join(lines[:first] + lines[end:])
    body = re.sub(r"\n{3,}", "\n\n", body).strip()
    return body, _unique(items)


INLINE_OPTION_MAX_WORDS = 3
INLINE_OPTION_MAX = 5
_SENTENCE_RE = re.compile(r"[^.!?？\n]*[?？]")
_INLINE_SPLIT_RE = re.compile(
    r"\s*,\s*(?:(?:or|illa|allathu|ya|அல்லது)\s+)?|\s+(?:or|illa|allathu|ya|அல்லது)\s+",
    re.IGNORECASE,
)
_QUESTION_WORD_RE = re.compile(r"^(which|what|who|how|edhu|ethu|endha|entha|enna|எது|எந்த)\b", re.IGNORECASE)
_LEAD_IN_RE = re.compile(
    r"^(?:would you (?:like|prefer)|do you (?:want|prefer)|shall (?:i|we) (?:book|go with)|"
    r"which (?:one|works)|prefer|is it)\s+",
    re.IGNORECASE,
)


def inline_options(text: str) -> list[str]:
    """The last question, when it is nothing but its options: "Morning, Afternoon, or
    Evening?", "What time works: morning or evening?", "காலை, மதியம் அல்லது மாலை?".
    The text is kept as it is; the options are only attached."""
    questions = _SENTENCE_RE.findall(text or "")
    if not questions:
        return []
    question = questions[-1].strip().rstrip("?？").strip()
    candidates = [question]
    for delimiter in (":", " — ", " – ", " - "):
        if delimiter in question:
            before, after = question.rsplit(delimiter, 1)
            candidates = [after, before]  # "...: A or B?" and "A, B or C - which suits you?"
            break
    for candidate in candidates:
        options = _options_in(candidate)
        if options:
            return options
    return []


def _options_in(segment: str) -> list[str]:
    segment = _LEAD_IN_RE.sub("", segment.strip())
    parts = [_clean_option(p) for p in _INLINE_SPLIT_RE.split(segment)]
    if parts and _QUESTION_WORD_RE.match(parts[-1]):
        parts = parts[:-1]  # "Morning or evening, which works?"
    if not 2 <= len(parts) <= INLINE_OPTION_MAX or any(not p for p in parts):
        return []
    if any(len(p.split()) > INLINE_OPTION_MAX_WORDS or len(p) > LIST_ROW_TITLE_MAX for p in parts):
        return []
    return _unique([p[:1].upper() + p[1:] for p in parts])


def extract(text: str) -> tuple[str, list[str]]:
    """(message without the options, the options). Options are [] when the message
    offers no choice. The CHOICES line is always removed, even when unusable."""
    text = text or ""
    marked = _from_marker(text)
    if marked is not None:
        body, options = marked
        return body, options if 2 <= len(options) else []
    listed = _from_list(text)
    if listed is not None:
        return listed
    return text, []


def _row_title(option: str) -> str:
    if len(option) <= LIST_ROW_TITLE_MAX:
        return option
    return option[: LIST_ROW_TITLE_MAX - 1].rstrip() + "…"


def _distinct_titles(rows: list[dict]) -> None:
    """Two long options can be cut to the same 24 characters; a number keeps them apart."""
    seen: set[str] = set()
    for n, row in enumerate(rows, 1):
        title = row["title"]
        if title.casefold() in seen:
            suffix = f" {n}"
            title = title[: LIST_ROW_TITLE_MAX - len(suffix)].rstrip("… ") + suffix
            row["title"] = title
        seen.add(title.casefold())


def build_menu(options: list[str], list_label: str = "") -> dict | None:
    """A menu in the shape deal_turn.send_menu sends, or None for fewer than 2 options.
    Two options are reply buttons, three to ten a list. More than 10 options keep the first
    10: WhatsApp cannot show more in one list. list_label is the text on the bar that opens
    the list, already in the customer's language (see list_label_for)."""
    options = _unique([o.strip() for o in options if o and o.strip()])[:LIST_ROW_COUNT_MAX]
    if len(options) < 2:
        return None
    ids = [f"{ID_PREFIX}{i + 1}" for i in range(len(options))]
    if len(options) == REPLY_BUTTON_COUNT and all(len(o) <= BUTTON_TITLE_MAX for o in options):
        buttons = [{"id": i, "title": o} for i, o in zip(ids, options)]
        return {"kind": "buttons", "options": options, "buttons": buttons}
    rows = []
    for i, option in zip(ids, options):
        row = {"id": i, "title": _row_title(option)}
        if row["title"] != option:
            row["description"] = option[:LIST_ROW_DESCRIPTION_MAX]
        rows.append(row)
    _distinct_titles(rows)
    from_model = usable_label(list_label)
    return {
        "kind": "list", "options": [r["title"] for r in rows],
        "sections": [{"rows": rows}], "button_text": from_model or LIST_LABELS["en"],
        "label_from_model": bool(from_model),
    }


# The bar that opens a list, and the button under a link, in the customer's language. The
# model's own wording (offer_choices list_label, or the classifier's label) always wins, which
# is what covers every language written in Latin script; these cover the scripts and Tanglish
# that code can recognise without a model call. Every value is at most 20 characters.
LIST_LABELS = {
    "en": "Options", "tanglish": "Options paarunga", "ta": "தேர்வுகள்", "hi": "विकल्प देखें",
    "te": "ఎంపికలు", "kn": "ಆಯ್ಕೆಗಳು", "ml": "ഓപ്ഷനുകൾ", "bn": "বিকল্প দেখুন",
    "gu": "વિકલ્પો જુઓ", "pa": "ਵਿਕਲਪ ਵੇਖੋ", "ar": "الخيارات", "th": "ตัวเลือก",
    "ru": "Варианты", "zh": "查看选项", "ja": "選択肢を見る", "ko": "옵션 보기",
    "he": "אפשרויות", "el": "Επιλογές",
}
# (open a link, pay)
LINK_LABELS = {
    "en": ("Open link", "Pay now"), "tanglish": ("Link paarunga", "Pay pannunga"),
    "ta": ("லிங்க் திறக்க", "பணம் செலுத்து"), "hi": ("लिंक खोलें", "भुगतान करें"),
    "te": ("లింక్ తెరవండి", "చెల్లించండి"), "kn": ("ಲಿಂಕ್ ತೆರೆಯಿರಿ", "ಪಾವತಿಸಿ"),
    "ml": ("ലിങ്ക് തുറക്കുക", "പണമടയ്ക്കുക"), "bn": ("লিংক খুলুন", "পেমেন্ট করুন"),
    "gu": ("લિંક ખોલો", "ચુકવણી કરો"), "pa": ("ਲਿੰਕ ਖੋਲ੍ਹੋ", "ਭੁਗਤਾਨ ਕਰੋ"),
    "ar": ("فتح الرابط", "ادفع الآن"), "th": ("เปิดลิงก์", "ชำระเงิน"),
    "ru": ("Открыть ссылку", "Оплатить"), "zh": ("打开链接", "立即付款"),
    "ja": ("リンクを開く", "支払う"), "ko": ("링크 열기", "결제하기"),
    "he": ("פתח קישור", "שלם עכשיו"), "el": ("Άνοιγμα συνδέσμου", "Πληρωμή"),
}
_SCRIPT_RANGES = (
    ("ta", 0x0B80, 0x0BFF), ("te", 0x0C00, 0x0C7F), ("kn", 0x0C80, 0x0CFF), ("ml", 0x0D00, 0x0D7F),
    ("hi", 0x0900, 0x097F), ("bn", 0x0980, 0x09FF), ("gu", 0x0A80, 0x0AFF), ("pa", 0x0A00, 0x0A7F),
    ("ar", 0x0600, 0x06FF), ("th", 0x0E00, 0x0E7F), ("ru", 0x0400, 0x04FF), ("zh", 0x4E00, 0x9FFF),
    ("ja", 0x3040, 0x30FF), ("ko", 0xAC00, 0xD7AF), ("he", 0x0590, 0x05FF), ("el", 0x0370, 0x03FF),
)


def language_of(text: str) -> str:
    """A key of LIST_LABELS for the text: its dominant non-Latin script, "tanglish" for romanised
    Tamil, otherwise "en"."""
    counts: dict[str, int] = {}
    latin = 0
    for ch in text or "":
        cp = ord(ch)
        if cp < 128 and ch.isalpha():
            latin += 1
            continue
        for code, low, high in _SCRIPT_RANGES:
            if low <= cp <= high:
                counts[code] = counts.get(code, 0) + 1
                break
    if counts and max(counts.values()) >= latin:  # one foreign word in an English reply is not a language switch
        return max(counts, key=counts.__getitem__)
    try:
        from app.services.ai_reply import _detect_lang
        return "tanglish" if _detect_lang(text or "") == "tanglish" else "en"
    except Exception:  # the label is cosmetic: never let language detection cost the menu
        return "en"


def usable_label(label: str | None) -> str:
    """The model's own label for a button, or "" when it is empty or over WhatsApp's 20 characters."""
    label = re.sub(r"\s+", " ", label or "").strip()
    return label if 0 < len(label) <= LIST_LABEL_MAX else ""


def list_label_for(text: str, hint: str | None = None) -> str:
    return usable_label(hint) or LIST_LABELS.get(language_of(text), LIST_LABELS["en"])


class Link(NamedTuple):
    body: str  # the message without its link; "" when the link was all there was
    url: str
    label: str


_URL_RE = re.compile(r"https?://[^\s<>\"'`]+", re.IGNORECASE)
_URL_TRAILING = ".,;:!?)]}»›\"'।。"
_PAYMENT_HOST_RE = re.compile(r"https?://(?:[\w-]+\.)*(?:rzp\.io|razorpay\.(?:com|me))(?:[/?#]|$)", re.IGNORECASE)


def split_link(text: str) -> Link | None:
    """One https link in a message becomes a URL button: (the message without it, the link,
    the button label). None for no link, two different links (Meta allows one per message),
    an insecure or oversized link, or a message too long for a button body."""
    text = text or ""
    urls = {m.group(0).rstrip(_URL_TRAILING) for m in _URL_RE.finditer(text)}
    if len(urls) != 1:
        return None
    url = next(iter(urls))
    if not url.lower().startswith("https://") or len(url) > LINK_URL_MAX or len(url) <= len("https://"):
        return None
    body = re.sub(rf"\[([^\]]*)\]\({re.escape(url)}\)", r"\1", text)
    body = re.sub(rf"{re.escape(url)}[{re.escape(_URL_TRAILING)}]*", "", body)
    body = re.sub(r"[ \t]{2,}", " ", body)
    body = re.sub(r"[ \t]+\n", "\n", body)
    body = re.sub(r"\n{3,}", "\n\n", body).strip()
    if len(body) > INTERACTIVE_BODY_MAX:
        return None
    open_label, pay_label = LINK_LABELS.get(language_of(_URL_RE.sub(" ", text)), LINK_LABELS["en"])
    return Link(body, url, pay_label if _PAYMENT_HOST_RE.match(url) else open_label)


def build_detail_menu(field: dict, session_id: str) -> dict | None:
    """Build saved field choices with canonical, session-bound tap values."""
    if not isinstance(field, dict) or not isinstance(session_id, str) or not session_id.strip():
        return None
    field_key = field.get("key")
    options = field.get("options")
    if not isinstance(field_key, str) or not field_key.strip() or not isinstance(options, list):
        return None
    if any(not isinstance(option, str) for option in options):
        return None
    options = _unique([option.strip() for option in options if option.strip()])[:LIST_ROW_COUNT_MAX]
    menu = build_menu(options)
    if menu is None:
        return None
    ids = []
    for option in options:
        payload = json.dumps([session_id, field_key, option], ensure_ascii=False, separators=(",", ":"))
        encoded = base64.urlsafe_b64encode(payload.encode("utf-8")).decode("ascii").rstrip("=")
        interactive_id = DETAIL_ID_PREFIX + encoded
        if len(interactive_id) > (LIST_ROW_ID_MAX if menu["kind"] == "list" else INTERACTIVE_ID_MAX):
            return None
        ids.append(interactive_id)
    rows = menu["buttons"] if menu["kind"] == "buttons" else menu["sections"][0]["rows"]
    for row, interactive_id in zip(rows, ids):
        row["id"] = interactive_id
    return menu


def parse_detail_tap(interactive_id: str | None) -> tuple[str, str, str] | None:
    """Decode a detail choice; callers validate its session and saved field options."""
    if not isinstance(interactive_id, str) or len(interactive_id) > INTERACTIVE_ID_MAX:
        return None
    if not interactive_id.startswith(DETAIL_ID_PREFIX):
        return None
    encoded = interactive_id[len(DETAIL_ID_PREFIX):]
    if not re.fullmatch(r"[A-Za-z0-9_-]+", encoded):
        return None
    try:
        payload = base64.b64decode(encoded + "=" * (-len(encoded) % 4), altchars=b"-_", validate=True)
        values = json.loads(payload.decode("utf-8"))
    except (ValueError, UnicodeError, binascii.Error):
        return None
    if not isinstance(values, list) or len(values) != 3:
        return None
    if any(not isinstance(value, str) or not value.strip() for value in values):
        return None
    return tuple(values)


def as_text(body: str, options: list[str]) -> str:
    """For channels without buttons: the options written out, unless already in the text."""
    if not options or all(option.lower() in body.lower() for option in options):
        return body
    listing = "\n".join(f"{i}. {option}" for i, option in enumerate(options, 1))
    return f"{body}\n\n{listing}".strip()


VAGUE_MAX_WORDS = 3
_YES_NO_START_RE = re.compile(
    r"^(would you|do you|did you|shall i|shall we|should i|can i|may i|want me to|is that|are you|"
    r"will you|could you|have you|does that|would that|is it ok|ok to)\b",
    re.IGNORECASE,
)
_YES_NO_END_RE = re.compile(
    r"(venuma+|pannala+ma|paakanuma|anuppa?va|sariya|ok\s*-?\s*(?:va|ah|aa)|thaana|irukkanuma|"
    r"pogalama|solla(?:va|tuma)|correct\s*-?\s*(?:ah|aa|a)|maathano|maathanuma|maatranuma)\s*[?？]$|[\u0B80-\u0BFF]+ா\s*[?？]$",
    re.IGNORECASE,
)
_TAMIL_RE = re.compile(r"[\u0B80-\u0BFF]")


def is_vague(message: str) -> bool:
    """A reply that picks nothing: "ok", "hmm", "👍". Re-sending the same options to it reads
    like a bot; after a real question ("what's the difference?") the options may come again."""
    text = (message or "").strip()
    return "?" not in text and "？" not in text and len(text.split()) <= VAGUE_MAX_WORDS


def yes_no_options(text: str) -> list[str]:
    """A closing yes/no question ("Shall I send the link?", "Options paakanuma?") gets Yes / No."""
    question = inline_last_question(text)
    if not question:
        return []
    if not (_YES_NO_START_RE.search(question) or _YES_NO_END_RE.search(question)):
        return []
    return ["ஆம்", "வேண்டாம்"] if _TAMIL_RE.search(question) else ["Yes", "No"]


def inline_last_question(text: str) -> str:
    questions = _SENTENCE_RE.findall(text or "")
    return questions[-1].strip() if questions else ""


TOOL_NAME = "offer_choices"


def tool_def() -> dict:
    return {
        "type": "function",
        "function": {
            "name": TOOL_NAME,
            "description": (
                "Send your message with tappable options whenever you ask the customer to pick "
                "between two or more things (a time, a date, a type, yes/no, a product, a batch). "
                "Put your whole message in 'message'. For a configured booking detail use "
                "field_key; for configured packages use offering_keys or show_options. Code "
                "supplies their saved option labels and prices. Only use options for other "
                "conversational choices. Use exactly one choice source."
            ),
            "parameters": {
                "type": "object",
                "properties": {
                    "message": {"type": "string", "description": "The full message to send above the options, in the customer's language."},
                    "options": {"type": "array", "items": {"type": "string"}, "minItems": 2, "maxItems": LIST_ROW_COUNT_MAX,
                                "description": "Short option labels, ideally 20 characters or fewer."},
                    "list_label": {"type": "string", "maxLength": LIST_LABEL_MAX,
                                   "description": "For three or more options: the short text (at most 20 characters) on the bar that opens the list, in the customer's language, e.g. 'View options'. Leave out for two options."},
                    "field_key": {"type": "string", "description": "The exact configured booking field key being asked; code attaches its saved choices."},
                    "offering_keys": {"type": "array", "items": {"type": "string"}, "minItems": 2, "maxItems": LIST_ROW_COUNT_MAX,
                                      "description": "Exact configured package keys being offered; code supplies names, prices, and saved button labels."},
                },
                "required": ["message"],
            },
        },
    }


def from_tool_calls(calls: list[dict]) -> tuple[str, list[str]] | None:
    """(message, options) from the first usable offer_choices call."""
    for call in calls or []:
        func = call.get("function") or {}
        if func.get("name") != TOOL_NAME:
            continue
        try:
            args = json.loads(func.get("arguments") or "{}")
        except (ValueError, TypeError):
            continue
        if not isinstance(args, dict):
            continue
        options = [_clean_option(str(o)) for o in args.get("options") or [] if isinstance(o, (str, int, float))]
        options = _unique([o for o in options if o])
        if len(options) >= 2:
            return str(args.get("message") or "").strip(), options
    return None


def field_options_for(text: str, field: dict | None) -> list[str]:
    """A question about a required detail that has fixed options ("What time suits you?"
    for Preferred time: Morning | Afternoon | Evening) gets those options attached."""
    if not field or not field.get("options") or "?" not in (text or "") and "？" not in (text or ""):
        return []
    lowered = text.lower()
    words = [w for w in re.findall(r"\w+", (field.get("label") or "").lower()) if w not in _LABEL_STOPWORDS and len(w) > 2]
    if any(w in lowered for w in words) or any(o.lower() in lowered for o in field["options"]):
        return list(field["options"])
    return []


_LABEL_STOPWORDS = {"your", "preferred", "the", "and", "for", "of"}


def is_choice_tap(interactive_id: str | None) -> bool:
    return bool(interactive_id) and interactive_id.startswith(ID_PREFIX)


PROMPT_BLOCK = (
    "\n\nTAPPABLE CHOICES: whenever you ask the customer to pick between options (two or more: "
    "a time slot, a day, a type, a batch, yes or no, a product, anything), call offer_choices "
    "with your whole message. For a configured booking detail use its exact field_key; code "
    "attaches its saved choices even when your question is in another language. For configured "
    "packages use their exact offering_keys or show_options; code supplies saved names, prices "
    "and button labels. Use options only for other conversational choices, and use exactly one "
    "choice source per call. Explain the attached offerings and their differences using "
    "business information, without inventing services or saying only 'other services'. Answer "
    "general service questions from business information; offer paid package selection only "
    "when your reply clearly introduces those packages. If you "
    "cannot call it, end the message with ONE final line: CHOICES: first | second | third. "
    "Never type the options as a list for them to copy. When they ask what options exist "
    "(timings, batches, sizes, flavours), name them and let them pick. When you cannot do what "
    "they asked (a closed day, something out of stock), offer the nearest real alternatives to "
    "pick from. Never substitute generic options for configured packages or detail fields. Never ask which language "
    "they want to chat in: the business sets the reply language. Two options show as buttons and "
    "three or more as a list, so offer 2-10 short options (up to 20 characters each) and, for "
    "three or more, set list_label to a short phrase in the customer's language. Put at most one "
    "link in a message, as a plain https address; code shows it as a tappable button."
)


_QUESTION_MARK_RE = re.compile(r"[?？؟]")


def might_offer_choice(text: str) -> bool:
    """Cheap pre-filter for the safety net: only a reply with a question in it can be asking
    for a pick, so statements never cost a model call."""
    return bool(_QUESTION_MARK_RE.search(text or ""))


CLASSIFY_PROMPT = (
    "You check one WhatsApp message a business is about to send a customer. Decide whether it "
    "asks the customer to choose between specific options (a yes/no confirmation counts). "
    'Answer with JSON only: {"options": [...], "label": "..."}.\n'
    "- options: 2 to 10 short labels (under 24 characters each), taken from the message, in the "
    "message's own language and script, no numbering. Use [] when the question is open "
    "(a name, a date, a phone number, \"anything else?\", \"tell me more\") or offers no fixed options.\n"
    "- label: only when there are 3 or more options: 1-3 words, at most 20 characters, in the "
    "message's language, meaning \"see the options\". Otherwise \"\"."
)


def parse_classification(raw: str) -> tuple[list[str], str] | None:
    """(options, label) from the classifier's answer; None when it found no usable choice."""
    match = re.search(r"\{.*\}", raw or "", re.DOTALL)
    if not match:
        return None
    try:
        data = json.loads(match.group(0))
    except (ValueError, TypeError):
        return None
    if not isinstance(data, dict) or not isinstance(data.get("options"), list):
        return None
    options = _unique([_clean_option(str(o)) for o in data["options"] if isinstance(o, (str, int, float))])
    options = [o for o in options if o and len(o) <= OPTION_MAX_CHARS]
    if len(options) < 2:
        return None
    return options[:LIST_ROW_COUNT_MAX], usable_label(data.get("label") if isinstance(data.get("label"), str) else "")


async def classify(text: str, customer_message: str, llm, tenant_id: str, *, timeout: float) -> tuple[list[str], str] | None:
    """The safety net for a reply that asks for a pick in words no pattern recognises. One small
    call with a hard time limit: any failure or delay means the reply goes out as plain text."""
    messages = [
        {"role": "system", "content": CLASSIFY_PROMPT},
        {"role": "user", "content": f"Customer wrote:\n{(customer_message or '')[:300]}\n\nBusiness message:\n{(text or '')[:1500]}"},
    ]
    try:
        raw = await asyncio.wait_for(llm(messages, max_tokens=120, tenant_id=tenant_id), timeout)
    except Exception:
        logger.warning("Choice classifier skipped (error or over %.1fs) -- sending plain text", timeout)
        return None
    return parse_classification(raw)
