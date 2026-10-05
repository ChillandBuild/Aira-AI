"""Meta's template rules, checked before a template is sent for review.

Every rule here comes from Meta's official template docs (Components, Template
review, Utility templates). The builder screen runs the same rules live
(frontend/app/dashboard/templates/template-rules.ts); this module repeats them so
a template that skips the screen is still refused with a clear message instead of
coming back REJECTED from Meta.

Each check returns a list of plain-language problems. An empty list means the
part is fine.
"""
import re

VAR_RE = re.compile(r"\{\{(\d+)\}\}")
_NAMED_OR_BROKEN_VAR_RE = re.compile(r"\{\{(?!\d+\}\})[^{}]*\}\}")


def variable_indices(text: str | None) -> list[int]:
    return sorted({int(m) for m in VAR_RE.findall(text or "")})


def body_problems(text: str) -> list[str]:
    trimmed = (text or "").strip()
    if not trimmed:
        return []
    problems: list[str] = []
    if re.match(r"^\{\{\d+\}\}", trimmed):
        problems.append("Variables can't be at the start of the template.")
    if re.search(r"\{\{\d+\}\}$", trimmed):
        problems.append("Variables can't be at the end of the template.")
    indices = variable_indices(trimmed)
    if indices and indices != list(range(1, len(indices) + 1)):
        found = ", ".join("{{" + str(i) + "}}" for i in indices)
        problems.append(f"Variables must be numbered in order from {{{{1}}}} with no gaps (found {found}).")
    bad = _NAMED_OR_BROKEN_VAR_RE.search(trimmed)
    if bad:
        problems.append(f"{bad.group(0)} isn't a numbered variable. Variables look like {{{{1}}}}.")
    if trimmed.count("{{") != trimmed.count("}}"):
        problems.append("A variable is missing a brace. Each variable looks like {{1}}.")
    return problems


def header_problems(text: str | None) -> list[str]:
    if not text or not text.strip():
        return []
    problems: list[str] = []
    if len(variable_indices(text)) > 1:
        problems.append("The header can hold only one variable.")
    elif variable_indices(text) not in ([], [1]):
        problems.append("The header variable must be {{1}}.")
    return problems


def footer_problems(text: str | None) -> list[str]:
    if text and "{{" in text:
        return ["The footer can't contain variables."]
    return []


def url_problems(url: str | None) -> list[str]:
    url = (url or "").strip()
    if not url:
        return ["A website button needs a link."]
    problems: list[str] = []
    if not url.lower().startswith("https://"):
        problems.append("Website links must start with https://.")
    count = len(VAR_RE.findall(url))
    if count > 1:
        problems.append("A website link can hold only one variable.")
    elif count == 1 and not re.search(r"\{\{\d+\}\}$", url):
        problems.append("Put the link variable at the very end of the link.")
    return problems


def samples_for(text: str | None, samples: list[str] | None, where: str) -> list[str]:
    """The sample values Meta needs for `text`, in variable order.

    Raises ValueError naming the first variable that has no sample, because Meta
    requires a sample for every variable and invented ones get templates rejected.
    """
    indices = variable_indices(text)
    if not indices:
        return []
    given = [str(s).strip() for s in (samples or [])]
    for pos, idx in enumerate(indices):
        if pos >= len(given) or not given[pos]:
            raise ValueError(f"Add a sample value for {{{{{idx}}}}} in the {where}.")
    return given[: len(indices)]


def url_with_sample(url: str, sample: str | None) -> str:
    """Meta's URL example is the full link with the sample in place of the variable."""
    if not VAR_RE.search(url):
        return url
    value = (sample or "").strip()
    if not value:
        raise ValueError("Add a sample value for the website link variable.")
    return VAR_RE.sub(lambda _m: value, url, count=1)
