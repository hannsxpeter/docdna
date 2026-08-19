#!/usr/bin/env python3
"""Advisory prose-pattern inspection for DocDNA documentation."""

import re


FENCE = re.compile(r"^\s*(`{3,}|~{3,})")
HEADING = re.compile(r"^\s{0,3}#{1,6}\s+(.+?)\s*#*\s*$")
INLINE_CODE = re.compile(r"(`+)([^`\n]*?)\1")
LINK_TARGET = re.compile(r"(?<=\]\()(?:(?:[^()\n]|\([^()\n]*\))+)(?=\))")
AUTOLINK = re.compile(r"<(?:(?:https?|mailto):[^>\n]+)>")
WORD = re.compile(r"[A-Za-z][A-Za-z0-9'\-]*")

TITLE_SMALL = {
    "a", "an", "and", "as", "at", "but", "by", "for", "from", "if", "in", "into",
    "nor", "of", "on", "or", "over", "per", "the", "to", "up", "via", "with", "yet",
}

PATTERNS = (
    ("vague-attribution",
     re.compile(r"\b(?:experts?|analysts?|observers?|critics?|researchers?)\s+"
                r"(?:believe|say|argue|suggest|warn|note)\b|"
                r"\b(?:industry|research|media)\s+(?:reports?|sources?)\s+"
                r"(?:say|suggest|indicate|show)\b", re.I),
     "the attribution names no source; name the source or remove the claim"),
    ("filler-phrase",
     re.compile(r"\b(?:in order to|due to the fact that|it is important to note that|"
                r"it should be noted that)\b", re.I),
     "the phrase delays the point; state the point directly"),
    ("chatbot-phrase",
     re.compile(r"\b(?:i hope this helps|let me know if|great question|"
                r"you(?:'|\u2019)re absolutely right)\b|^\s*(?:of course|certainly)[!,. :]", re.I),
     "the phrase addresses a chat exchange rather than the document reader; remove it"),
    ("promotional-language",
     re.compile(r"\b(?:breathtaking|groundbreaking|must-visit|nestled|renowned|stunning|vibrant)\b",
                re.I),
     "the adjective promotes instead of describing a mechanism or result; replace it with a fact"),
    ("fancy-copula",
     re.compile(r"\b(?:serves as|stands as|boasts)\b", re.I),
     "the phrase obscures a simpler verb; prefer 'is', 'has', or the action itself"),
    ("stock-contrast",
     re.compile(r"\bnot\s+(?:just|only)\b[^.!?\n]{0,160}?\bbut\s+(?:also\s+)?\b", re.I),
     "the contrast is formulaic; state the stronger point directly"),
    ("generic-conclusion",
     re.compile(r"\b(?:the future looks bright|exciting times (?:are|lie) ahead|"
                r"only time will tell|it remains to be seen)\b", re.I),
     "the conclusion adds no project-specific fact; replace it with a decision or remove it"),
)


def _spaces(match):
    return " " * (match.end() - match.start())


def _mask_inline(line):
    masked = INLINE_CODE.sub(_spaces, line)
    masked = LINK_TARGET.sub(_spaces, masked)
    return AUTOLINK.sub(_spaces, masked)


def _mask_comments(line, inside):
    chars = list(line)
    cursor = 0
    while cursor < len(line):
        if inside:
            end = line.find("-->", cursor)
            if end < 0:
                for index in range(cursor, len(chars)):
                    chars[index] = " "
                return "".join(chars), True
            for index in range(cursor, end + 3):
                chars[index] = " "
            cursor = end + 3
            inside = False
            continue
        start = line.find("<!--", cursor)
        if start < 0:
            break
        end = line.find("-->", start + 4)
        if end < 0:
            for index in range(start, len(chars)):
                chars[index] = " "
            return "".join(chars), True
        for index in range(start, end + 3):
            chars[index] = " "
        cursor = end + 3
    return "".join(chars), inside


def _title_case(text):
    words = WORD.findall(text)
    significant = [word for word in words if word.lower() not in TITLE_SMALL]
    if len(significant) < 3:
        return False
    for word in significant:
        if word.isupper() or (word[0].isupper() and word[1:] == word[1:].lower()):
            continue
        return False
    return True


def iter_findings(text):
    frontmatter = text.startswith("---\n") or text.startswith("---\r\n")
    fenced = None
    comment = False
    for line_number, raw in enumerate(text.splitlines(), 1):
        if frontmatter:
            if line_number > 1 and raw.strip() == "---":
                frontmatter = False
            continue
        fence = FENCE.match(raw)
        if fenced is not None:
            if fence and fence.group(1)[0] == fenced[0] and len(fence.group(1)) >= len(fenced):
                fenced = None
            continue
        if fence:
            fenced = fence.group(1)
            continue
        visible = _mask_inline(raw)
        visible, comment = _mask_comments(visible, comment)
        heading = HEADING.match(visible)
        if heading and _title_case(heading.group(1)):
            yield {"kind": "title-case-heading", "line": line_number,
                   "column": heading.start(1) + 1, "match": heading.group(1).strip(),
                   "detail": "the heading uses title case; use sentence case unless the text is a name"}
        for kind, pattern, detail in PATTERNS:
            for match in pattern.finditer(visible):
                yield {"kind": kind, "line": line_number, "column": match.start() + 1,
                       "match": match.group(0).strip(), "detail": detail}


def inspect_text(text):
    return list(iter_findings(text))
