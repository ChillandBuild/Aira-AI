"""Turn the model's Markdown into WhatsApp's own formatting before a reply is sent.

WhatsApp bolds with one star (*bold*), not two. "**One Question**" arrives with the inner stars
showing, and "* item" / "### Heading" show as raw symbols on older clients. Pure text in, text
out; anything already in WhatsApp syntax is left alone.
"""
import re

_BOLD_RE = re.compile(r"\*\*([^*\n]+?)\*\*")
_UNDERLINE_BOLD_RE = re.compile(r"__([^_\n]+?)__")
_STRIKE_RE = re.compile(r"~~([^~\n]+?)~~")
_BULLET_RE = re.compile(r"^(\s*)[*-]\s+", re.MULTILINE)
_HEADING_RE = re.compile(r"^#{1,6}\s+(.+?)\s*#*\s*$", re.MULTILINE)


def to_whatsapp(text: str) -> str:
    if not text:
        return text
    text = _BULLET_RE.sub(r"\1• ", text)  # before bold, so "* **x**" is not read as bold
    text = _BOLD_RE.sub(r"*\1*", text)
    text = _UNDERLINE_BOLD_RE.sub(r"_\1_", text)
    text = _STRIKE_RE.sub(r"~\1~", text)
    return _HEADING_RE.sub(r"*\1*", text)
