"""Any question with options goes out with tappable options, never as bare text.

The model ends a message that asks the customer to pick with one line:
    CHOICES: Morning | Evening
Code removes that line and attaches the options as WhatsApp reply buttons (2-3 short
options) or a list (up to 10). When the model forgets the line but still writes its
options as a numbered or bulleted list under a question, the list itself becomes the
options (the backstop). Channels without buttons get the options written out instead.

The model has three ways to offer choices, most reliable first: the offer_choices tool
(it writes the message and the options in one call), the CHOICES line, and plain options
the backstops recognise (a list under a question, or "Morning, Afternoon or Evening?").

Pure functions only; deal_turn.converse_once applies them to every reply.
"""
import json
import re

MARKER = "CHOICES"
BUTTON_TITLE_MAX = 20  # WhatsApp reply button title limit
BUTTON_COUNT_MAX = 3
LIST_ROW_TITLE_MAX = 24
LIST_ROW_DESCRIPTION_MAX = 72
LIST_ROW_COUNT_MAX = 10
LIST_BUTTON_TEXT = "Choose"
OPTION_MAX_CHARS = 72  # longer than this is a sentence, not an option
ID_PREFIX = "choice:"

_MARKER_RE = re.compile(r"^[ \t>*_`]*CHOICES?[ \t*_`]*[:：][ \t]*(.*?)[ \t*_`]*$", re.IGNORECASE | re.MULTILINE)
_LIST_ITEM_RE = re.compile(
    r"^[ \t]*(?:[-•*▪►‣◦]|\d{1,2}[.)]|\d️⃣|[a-hA-H][.)])[ \t]+(.+?)[ \t]*$"
)
# A question that asks the customer to pick, in English and romanised Tamil/Hindi.
PICK_CUE_RE = re.compile(
    r"\b(which|choose|pick|select|prefer|option|options|or|edhu|ethu|endha|entha|konsa|kaunsa|"
    r"illa|illana|allathu|venuma|vendumaa?)\b|எது|எந்த|அல்லது",
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


def build_menu(options: list[str]) -> dict | None:
    """A menu in the shape deal_turn.send_menu sends, or None for fewer than 2 options.
    More than 10 options keep the first 10: WhatsApp cannot show more in one list."""
    options = _unique([o.strip() for o in options if o and o.strip()])[:LIST_ROW_COUNT_MAX]
    if len(options) < 2:
        return None
    ids = [f"{ID_PREFIX}{i + 1}" for i in range(len(options))]
    if len(options) <= BUTTON_COUNT_MAX and all(len(o) <= BUTTON_TITLE_MAX for o in options):
        buttons = [{"id": i, "title": o} for i, o in zip(ids, options)]
        return {"kind": "buttons", "options": options, "buttons": buttons}
    rows = []
    for i, option in zip(ids, options):
        row = {"id": i, "title": _row_title(option)}
        if row["title"] != option:
            row["description"] = option[:LIST_ROW_DESCRIPTION_MAX]
        rows.append(row)
    return {
        "kind": "list", "options": [r["title"] for r in rows],
        "sections": [{"rows": rows}], "button_text": LIST_BUTTON_TEXT,
    }


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
    r"pogalama|solla(?:va|tuma))\s*[?？]$|[\u0B80-\u0BFF]+ா\s*[?？]$",
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
                "Put your whole message in 'message'; do not list the options in it. For this "
                "business's packages use show_options instead."
            ),
            "parameters": {
                "type": "object",
                "properties": {
                    "message": {"type": "string", "description": "The full message to send above the options, in the customer's language."},
                    "options": {"type": "array", "items": {"type": "string"}, "minItems": 2, "maxItems": LIST_ROW_COUNT_MAX,
                                "description": "Short option labels, ideally 20 characters or fewer."},
                },
                "required": ["message", "options"],
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
    "with your whole message and the options; the customer gets them as buttons to tap. If you "
    "cannot call it, end the message with ONE final line: CHOICES: first | second | third. "
    "Never type the options as a list for them to copy. When they ask what options exist "
    "(timings, batches, sizes, flavours), name them and let them pick. When you cannot do what "
    "they asked (a closed day, something out of stock), offer the nearest real alternatives to "
    "pick from. For this business's packages call show_options instead. Never ask which language "
    "they want to chat in: the business sets the reply language."
)
