#!/usr/bin/env python3
"""Deterministic Unicode hygiene for DocDNA documentation text.

Unicode classes and emoji-glue handling are adapted from watermarks-remover.
See ../references/third-party-notices.md for its MIT license notice.
"""

from collections import Counter
import unicodedata


BIDI = {
    0x061C, 0x200E, 0x200F, 0x202A, 0x202B, 0x202C, 0x202D, 0x202E,
    0x2066, 0x2067, 0x2068, 0x2069,
}
ZERO_WIDTH = {
    0x200B, 0x200C, 0x200D, 0x2060, 0xFEFF, 0x180E,
}
EXPLICIT_FORMAT = {
    0x00AD, 0x034F, 0x115F, 0x1160, 0x17B4, 0x17B5,
    0x2061, 0x2062, 0x2063, 0x2064, 0x206A, 0x206B, 0x206C,
    0x206D, 0x206E, 0x206F, 0xFFF9, 0xFFFA, 0xFFFB,
}
SPACE_REPLACEMENTS = {
    0x00A0: " ", 0x1680: " ", 0x2000: " ", 0x2001: " ",
    0x2002: " ", 0x2003: " ", 0x2004: " ", 0x2005: " ",
    0x2006: " ", 0x2007: " ", 0x2008: " ", 0x2009: " ",
    0x200A: " ", 0x202F: " ", 0x205F: " ", 0x3000: " ",
}
EMOJI_GLUE = {0x200D, 0xFE0E, 0xFE0F}


def _is_variation_selector(point):
    return (0x180B <= point <= 0x180D or 0xFE00 <= point <= 0xFE0F
            or 0xE0100 <= point <= 0xE01EF)


def _is_noncharacter(point):
    return 0xFDD0 <= point <= 0xFDEF or (point & 0xFFFF) in (0xFFFE, 0xFFFF)


def _is_emoji_base(point):
    if 0x1F000 <= point <= 0x1FAFF:
        return True
    if 0x2600 <= point <= 0x27BF or 0x2B00 <= point <= 0x2BFF:
        return True
    if point in (0x00A9, 0x00AE, 0x2122, 0x3030, 0x303D, 0x3297, 0x3299,
                 0x0023, 0x002A):
        return True
    return 0x0030 <= point <= 0x0039


def _previous_emoji_base(text, index):
    previous = index - 1
    while previous >= 0 and ord(text[previous]) in (0xFE0E, 0xFE0F):
        previous -= 1
    return previous >= 0 and _is_emoji_base(ord(text[previous]))


def _emoji_glue_is_legitimate(text, index):
    point = ord(text[index])
    if point in (0xFE0E, 0xFE0F):
        return _previous_emoji_base(text, index)
    if point != 0x200D or not _previous_emoji_base(text, index):
        return False
    return index + 1 < len(text) and _is_emoji_base(ord(text[index + 1]))


def _classification(text, index):
    point = ord(text[index])
    category = unicodedata.category(text[index])
    if ((category == "Cc" and point not in (0x09, 0x0A, 0x0D))
            or category == "Cs" or _is_noncharacter(point)):
        return "control", "major", "remove"
    if point in EMOJI_GLUE and _emoji_glue_is_legitimate(text, index):
        return None
    if point in BIDI:
        return "bidi", "major", "remove"
    if 0xE0001 <= point <= 0xE007F:
        return "tag", "major", "remove"
    if point in SPACE_REPLACEMENTS:
        return "space", "minor", "replace"
    if point in ZERO_WIDTH:
        return "zero-width", "minor", "remove"
    if _is_variation_selector(point):
        return "variation-selector", "minor", "remove"
    if point in EXPLICIT_FORMAT or category == "Cf":
        return "format", "minor", "remove"
    return None


def _codepoint(point):
    return "U+%04X" % point


def iter_findings(text):
    """Yield one exact record per suspicious character in ``text``."""
    line = 1
    column = 1
    for offset, character in enumerate(text):
        classification = _classification(text, offset)
        if classification is not None:
            kind, severity, action = classification
            point = ord(character)
            yield {
                "offset": offset,
                "line": line,
                "column": column,
                "codepoint": _codepoint(point),
                "name": unicodedata.name(character, "UNKNOWN"),
                "category": unicodedata.category(character),
                "kind": kind,
                "severity": severity,
                "action": action,
            }
        if character == "\n":
            line += 1
            column = 1
        else:
            column += 1


def inspect_text(text):
    """Return one exact record per suspicious character in ``text``."""
    return list(iter_findings(text))


def clean_generated_text(text):
    """Clean generated prose and return ``(text, transformation_stats)``.

    This deliberately avoids compatibility normalization and confusable-letter
    replacement. Those operations can change identifiers and cited content.
    """
    output = []
    removed = 0
    replaced = 0
    kinds = Counter()
    for index, character in enumerate(text):
        classification = _classification(text, index)
        if classification is None:
            output.append(character)
            continue
        kind, _severity, action = classification
        kinds[kind] += 1
        if action == "replace":
            output.append(SPACE_REPLACEMENTS[ord(character)])
            replaced += 1
        else:
            removed += 1
    return "".join(output), {
        "removed_count": removed,
        "replaced_count": replaced,
        "by_kind": dict(sorted(kinds.items())),
    }
