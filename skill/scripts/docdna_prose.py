#!/usr/bin/env python3
"""Advisory prose inspection and protected-inventory comparison for Markdown."""

# Implements: P-MUST-01

import argparse
import json
import os
import re
import sys
from collections import Counter

HERE = os.path.dirname(os.path.abspath(__file__))
if HERE not in sys.path:
    sys.path.insert(0, HERE)

from docdna_fs import MAX_CONTROL_BYTES, read_bounded_path


MAX_PROSE_BYTES = MAX_CONTROL_BYTES


FENCE = re.compile(r"^ {0,3}(`{3,}|~{3,})(.*)$")
HEADING = re.compile(r"^\s{0,3}#{1,6}\s+(.+?)\s*#*\s*$")
LIST_ITEM = re.compile(r"^ {0,3}(?:[*+-]|\d{1,9}[.)])(?:[ \t]+|$)")
WORD = re.compile(r"[A-Za-z][A-Za-z0-9'\-]*")
AUTOLINK = re.compile(
    r"<(?:[A-Za-z][A-Za-z0-9+.-]{0,31}:[^<>\x00-\x20]*|"
    r"[A-Za-z0-9.!#$%&'*+/=?^_`{|}~-]+@"
    r"[A-Za-z0-9](?:[A-Za-z0-9-]{0,61}[A-Za-z0-9])?"
    r"(?:\.[A-Za-z0-9](?:[A-Za-z0-9-]{0,61}[A-Za-z0-9])?)*)>",
)
REFERENCE_DEFINITION = re.compile(r"^ {0,3}\[(?:\\.|[^\]\\\n])+\]:[ \t]*")
QUOTED_LITERAL = re.compile(r'"(?:\\.|[^"\n])*"|\u201c[^\u201d\n]*\u201d')

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

SIGNPOST = re.compile(
    r"\b(?:in this|in the following|the following) section,?\s+"
    r"(?:we(?:'|\u2019)?ll\s+|we will\s+)?"
    r"(?:cover|discuss|explore|examine|look at|walk through)\b",
    re.I,
)
TRANSITION = re.compile(r"^\s*(?:additionally|furthermore|moreover|in addition),", re.I)
CHAT_CONTAMINATION = re.compile(
    r"\b(?:would you like me to|i can (?:also|help|provide)|feel free to ask|"
    r"if you(?:'|\u2019)d like,? i can)\b",
    re.I,
)
KNOWLEDGE_CUTOFF = re.compile(
    r"\b(?:as of my (?:last )?knowledge (?:update|cutoff)|"
    r"up to my last training update|"
    r"my knowledge (?:only extends|is current) (?:to|through))\b",
    re.I,
)
DIFF_ANCHORED = re.compile(
    r"\b(?:(?:we|the team)\s+(?:have\s+)?(?:added|removed|changed|updated|introduced|fixed)|"
    r"this (?:release|change|update)\s+(?:adds|removes|changes|updates|introduces|fixes)|"
    r"(?:is|are|was|were) (?:added to|removed from)|has been updated to|now uses|"
    r"replaces? the (?:old|previous)|previously (?:used|was|were))\b",
    re.I,
)
LEXICAL = re.compile(
    r"\b(?:delve(?:s|d|ing)?|intricate|tapestry|multifaceted|pivotal|"
    r"ever-evolving|realm|testament)\b",
    re.I,
)

DETAILS = {
    "signposting": "the prose announces its structure; start with the subject or action",
    "chat-contamination": ("the phrase belongs to an assistant exchange rather than the document; "
                           "remove it"),
    "knowledge-cutoff-disclaimer": ("the document contains a model knowledge disclaimer; verify the "
                                    "claim against current project evidence"),
    "diff-anchored-prose": ("the sentence describes an edit instead of the current state; state the "
                            "steady-state behavior"),
    "lexical-cluster": ("several stock abstract terms cluster in the document; replace each with the "
                        "specific mechanism when the evidence supports it"),
}

SOFT_INFERENCE_QUESTIONS = (
    ("causal", "Could the edit change a cause, reason, condition, or consequence?"),
    ("temporal", "Could the edit change order, timing, duration, or lifecycle state?"),
    ("quantitative", "Could the edit change an amount, scope, comparison, or limit?"),
)

CITATION = re.compile(
    r"\[`[^`\]\n]+`(?:\s+\"(?:\\.|[^\"\n])*\")?\]|"
    r"\[(?:run|ref|human):[^\]\n]+\]",
    re.I,
)
GAP_MARKER = re.compile(r"\bGAP\s+[A-Z][A-Z0-9]*(?:-[A-Z0-9]+)+\b")
NUMBER = re.compile(r"(?<![A-Za-z_])\d+(?:\.\d+)*(?![A-Za-z_])")
PATH_TOKEN = re.compile(
    r"(?<![A-Za-z0-9_])(?:\.?\.?/)?(?:[A-Za-z0-9_.-]+/)+[A-Za-z0-9_.#-]+"
)


def _escaped(text, index):
    slashes = 0
    index -= 1
    while index >= 0 and text[index] == "\\":
        slashes += 1
        index -= 1
    return slashes % 2 == 1


def _inline_ranges(line):
    ranges = []
    cursor = 0
    while cursor < len(line):
        if line[cursor] != "`" or _escaped(line, cursor):
            cursor += 1
            continue
        end = cursor + 1
        while end < len(line) and line[end] == "`":
            end += 1
        delimiter = line[cursor:end]
        search = end
        closing = None
        while search < len(line):
            found = line.find(delimiter, search)
            if found < 0:
                break
            before_same = found > 0 and line[found - 1] == "`"
            after = found + len(delimiter)
            after_same = after < len(line) and line[after] == "`"
            if not before_same and not after_same and not _escaped(line, found):
                closing = after
                break
            search = found + 1
        if closing is None:
            cursor = end
            continue
        ranges.append((cursor, closing))
        cursor = closing
    return ranges


def _link_title_close(line, cursor):
    while cursor < len(line) and line[cursor] in " \t":
        cursor += 1
    if cursor >= len(line) or line[cursor] == ")":
        return cursor
    opener = line[cursor]
    closer = {"\"": "\"", "'": "'", "(": ")"}.get(opener)
    if closer is None:
        return None
    cursor += 1
    while cursor < len(line):
        character = line[cursor]
        if character == "\\":
            cursor += 2 if cursor + 1 < len(line) else 1
            continue
        if character == closer:
            cursor += 1
            while cursor < len(line) and line[cursor] in " \t":
                cursor += 1
            return cursor
        cursor += 1
    return None


def _link_destination(line, start, unavailable):
    if start >= len(line):
        return None, start
    if line[start] == ")":
        return (start, start, start), start
    if line[start] == "<":
        cursor = start + 1
        while cursor < len(line):
            if unavailable[cursor]:
                return None, cursor + 1
            character = line[cursor]
            if character == "\\":
                if cursor + 1 < len(line) and unavailable[cursor + 1]:
                    return None, cursor + 2
                cursor += 2 if cursor + 1 < len(line) else 1
                continue
            if character in "\n<":
                return None, cursor + 1
            if character == ">":
                title_close = _link_title_close(line, cursor + 1)
                if title_close is not None and title_close < len(line) \
                        and line[title_close] == ")":
                    return (start + 1, cursor, title_close), title_close
                return None, max(cursor + 1, title_close or 0)
            cursor += 1
        return None, len(line)
    depth = 0
    cursor = start
    while cursor < len(line):
        if unavailable[cursor]:
            return None, cursor + 1
        character = line[cursor]
        if character == "\\":
            if cursor + 1 < len(line) and unavailable[cursor + 1]:
                return None, cursor + 2
            cursor += 2 if cursor + 1 < len(line) else 1
            continue
        if character in " \t":
            title_close = _link_title_close(line, cursor)
            if title_close is not None and title_close < len(line) \
                    and line[title_close] == ")":
                return (start, cursor, title_close), title_close
            return None, max(cursor + 1, title_close or 0)
        if character == "(":
            depth += 1
        elif character == ")":
            if depth == 0:
                return (start, cursor, cursor), cursor
            depth -= 1
        cursor += 1
    return None, len(line)


def _link_ranges(line, unavailable):
    ranges = []
    brackets = []
    cursor = 0
    while cursor < len(line):
        if unavailable[cursor]:
            cursor += 1
            continue
        character = line[cursor]
        if character == "\\":
            cursor += 2 if cursor + 1 < len(line) else 1
            continue
        if character == "[":
            brackets.append(cursor)
            cursor += 1
            continue
        if character != "]":
            cursor += 1
            continue
        opener = brackets.pop() if brackets else None
        if (opener is None or cursor + 1 >= len(line) or line[cursor + 1] != "("
                or unavailable[cursor + 1]):
            cursor += 1
            continue
        destination, scanned_to = _link_destination(line, cursor + 2, unavailable)
        if destination is None:
            if scanned_to >= len(line):
                break
            cursor = max(cursor + 1, scanned_to)
            continue
        start, end, close = destination
        ranges.append((start, end))
        cursor = close + 1
    return ranges


def _reference_target(line, unavailable):
    match = REFERENCE_DEFINITION.match(line)
    if not match or any(unavailable[match.start():match.end()]):
        return None
    start = match.end()
    if start >= len(line):
        return None
    if line[start] == "<":
        index = start + 1
        while index < len(line):
            character = line[index]
            if character == "\\":
                index += 2 if index + 1 < len(line) else 1
                continue
            if character == ">":
                return start, index + 1, line[start + 1:index]
            index += 1
        return None
    depth = 0
    index = start
    while index < len(line):
        character = line[index]
        if character == "\\":
            index += 2 if index + 1 < len(line) else 1
            continue
        if character in " \t" and depth == 0:
            break
        if character == "(":
            depth += 1
        elif character == ")":
            if depth == 0:
                break
            depth -= 1
        index += 1
    if index == start or depth != 0:
        return None
    return start, index, line[start:index]


def _mask_inline(line, protected_mask=None):
    chars = list(line)
    unavailable = (list(protected_mask) if protected_mask is not None
                   else [False] * len(line))
    if protected_mask is None:
        code_ranges = _inline_ranges(line)
    else:
        code_ranges = ()
        for index, masked in enumerate(protected_mask):
            if masked:
                chars[index] = " "
    for start, end in code_ranges:
        for index in range(start, end):
            chars[index] = " "
            unavailable[index] = True
    for start, end in _link_ranges(line, unavailable):
        for index in range(start, end):
            chars[index] = " "
            unavailable[index] = True
    reference = _reference_target(line, unavailable)
    if reference is not None:
        start, end, _ = reference
        for index in range(start, end):
            chars[index] = " "
            unavailable[index] = True
    return "".join(chars)


def _opening_fence(line):
    match = FENCE.match(line)
    if not match:
        return None
    marker = match.group(1)
    if marker[0] == "`" and "`" in match.group(2):
        return None
    return marker[0], len(marker)


def _closing_fence(line, fence):
    match = FENCE.match(line)
    if not match:
        return False
    marker = match.group(1)
    return (marker[0] == fence[0] and len(marker) >= fence[1]
            and not match.group(2).strip())


def _blockquote_content(line):
    cursor = 0
    depth = 0
    while cursor < len(line):
        probe = cursor
        spaces = 0
        while probe < len(line) and line[probe] == " " and spaces < 3:
            probe += 1
            spaces += 1
        if probe >= len(line) or line[probe] != ">":
            break
        probe += 1
        if probe < len(line) and line[probe] in " \t":
            probe += 1
        cursor = probe
        depth += 1
    return cursor, line[cursor:], depth


def _block_structure(text):
    lines = text.splitlines()
    masked = [False] * len(lines)
    blocks = []
    frontmatter = bool(lines and lines[0].strip() == "---")
    if frontmatter:
        for index, line in enumerate(lines):
            masked[index] = True
            if index > 0 and line.strip() in ("---", "..."):
                break
    fenced = None
    fence_depth = 0
    current = []
    for index, raw in enumerate(lines):
        if masked[index]:
            continue
        _, content, quote_depth = _blockquote_content(raw)
        if fenced is not None:
            if quote_depth < fence_depth:
                blocks.append("\n".join(current))
                fenced = None
                current = []
            else:
                masked[index] = True
                current.append(raw)
                if quote_depth == fence_depth and _closing_fence(content, fenced):
                    blocks.append("\n".join(current))
                    fenced = None
                    current = []
                continue
        opening = _opening_fence(content)
        if opening is not None:
            fenced = opening
            fence_depth = quote_depth
            masked[index] = True
            current = [raw]
    if current:
        blocks.append("\n".join(current))
    return lines, masked, blocks


def _inline_code_masks(lines, block_mask):
    masks = [[False] * len(line) for line in lines]
    values = []

    def scan_segment(start, end):
        segment_lines = lines[start:end]
        segment = "\n".join(segment_lines)
        offsets = []
        offset = 0
        for line in segment_lines:
            offsets.append(offset)
            offset += len(line) + 1
        for span_start, span_end in _inline_ranges(segment):
            values.append(segment[span_start:span_end])
            for relative, line in enumerate(segment_lines):
                line_start = offsets[relative]
                line_end = line_start + len(line)
                overlap_start = max(span_start, line_start)
                overlap_end = min(span_end, line_end)
                for position in range(overlap_start, overlap_end):
                    masks[start + relative][position - line_start] = True

    segment_start = None
    segment_quote_depth = None
    for index, line in enumerate(lines):
        boundary = block_mask[index] or not line.strip()
        if boundary:
            if segment_start is not None:
                scan_segment(segment_start, index)
                segment_start = None
                segment_quote_depth = None
            continue
        _, content, quote_depth = _blockquote_content(line)
        heading = HEADING.match(content) is not None
        list_item = LIST_ITEM.match(content) is not None
        if segment_start is not None and (quote_depth != segment_quote_depth
                                          or heading or list_item):
            scan_segment(segment_start, index)
            segment_start = None
            segment_quote_depth = None
        if heading:
            scan_segment(index, index + 1)
            continue
        if segment_start is None:
            segment_start = index
            segment_quote_depth = quote_depth
    if segment_start is not None:
        scan_segment(segment_start, len(lines))
    return masks, values


def _protected_inline_masks(lines, block_mask, code_masks):
    masks = [list(mask) for mask in code_masks]
    comment_masks = [[False] * len(line) for line in lines]
    autolinks = [[] for _ in lines]
    for line_number, line in enumerate(lines):
        if block_mask[line_number]:
            continue
        for match in QUOTED_LITERAL.finditer(line):
            if not any(masks[line_number][match.start():match.end()]):
                for index in range(match.start(), match.end()):
                    masks[line_number][index] = True
        for match in AUTOLINK.finditer(line):
            if not any(masks[line_number][match.start():match.end()]):
                autolinks[line_number].append(match)
                for index in range(match.start(), match.end()):
                    masks[line_number][index] = True

    comment = False
    for line_number, line in enumerate(lines):
        if block_mask[line_number]:
            continue
        cursor = 0
        while cursor < len(line):
            if comment:
                end = line.find("-->", cursor)
                stop = len(line) if end < 0 else end + 3
                for index in range(cursor, stop):
                    masks[line_number][index] = True
                    comment_masks[line_number][index] = True
                if end < 0:
                    break
                cursor = stop
                comment = False
                continue
            start = line.find("<!--", cursor)
            if start < 0:
                break
            if any(masks[line_number][start:start + 4]):
                cursor = start + 1
                continue
            comment = True
            cursor = start

    for line_number, matches in enumerate(autolinks):
        autolinks[line_number] = [
            match for match in matches
            if not any(comment_masks[line_number][match.start():match.end()])
        ]
    return masks, autolinks


def _masked_lines(text):
    rows = []
    lines, block_mask, _ = _block_structure(text)
    code_masks, _ = _inline_code_masks(lines, block_mask)
    protected_masks, _ = _protected_inline_masks(lines, block_mask, code_masks)
    for line_number, raw in enumerate(lines, 1):
        if block_mask[line_number - 1]:
            rows.append((line_number, raw, " " * len(raw)))
            continue
        visible = _mask_inline(raw, protected_masks[line_number - 1])
        rows.append((line_number, raw, visible))
    return rows


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


def _finding(kind, line_number, match, detail):
    raw = match.group(0)
    leading_space = len(raw) - len(raw.lstrip())
    return {"kind": kind, "line": line_number,
            "column": match.start() + leading_space + 1,
            "match": raw.strip(), "detail": detail}


def _allows_diff_language(path):
    normalized = (path or "").replace("\\", "/").lower()
    parts = [part for part in normalized.split("/") if part]
    basename = parts[-1] if parts else ""
    return ("changelog" in basename
            or any("release-notes" in part or "release_notes" in part for part in parts)
            or any("migration" in part for part in parts)
            or "releases" in parts)


def iter_findings(text, path=None):
    rows = _masked_lines(text)
    findings = []
    transitions = []
    lexical = []
    paragraph = 0
    for line_number, _, visible in rows:
        if not visible.strip():
            paragraph += 1
            continue
        heading = HEADING.match(visible)
        if heading and _title_case(heading.group(1)):
            findings.append({"kind": "title-case-heading", "line": line_number,
                             "column": heading.start(1) + 1,
                             "match": heading.group(1).strip(),
                             "detail": ("the heading uses title case; use sentence case unless the "
                                        "text is a name")})
        for kind, pattern, detail in PATTERNS:
            for match in pattern.finditer(visible):
                findings.append(_finding(kind, line_number, match, detail))
        for match in SIGNPOST.finditer(visible):
            findings.append(_finding("signposting", line_number, match, DETAILS["signposting"]))
        transitions.extend((paragraph, line_number, match)
                           for match in TRANSITION.finditer(visible))
        for match in CHAT_CONTAMINATION.finditer(visible):
            findings.append(_finding("chat-contamination", line_number, match,
                                     DETAILS["chat-contamination"]))
        for match in KNOWLEDGE_CUTOFF.finditer(visible):
            findings.append(_finding("knowledge-cutoff-disclaimer", line_number, match,
                                     DETAILS["knowledge-cutoff-disclaimer"]))
        if not _allows_diff_language(path):
            for match in DIFF_ANCHORED.finditer(visible):
                findings.append(_finding("diff-anchored-prose", line_number, match,
                                         DETAILS["diff-anchored-prose"]))
        lexical.extend((paragraph, line_number, match) for match in LEXICAL.finditer(visible))
    transition_counts = Counter(item[0] for item in transitions)
    for paragraph_number, line_number, match in transitions:
        if transition_counts[paragraph_number] >= 2:
            findings.append(_finding("signposting", line_number, match, DETAILS["signposting"]))
    lexical_counts = Counter(item[0] for item in lexical)
    for paragraph_number, line_number, match in lexical:
        if lexical_counts[paragraph_number] >= 2:
            findings.append(_finding("lexical-cluster", line_number, match,
                                     DETAILS["lexical-cluster"]))
    for finding in sorted(findings, key=lambda row: (row["line"], row["column"], row["kind"])):
        yield finding


def inspect_text(text, path=None):
    return list(iter_findings(text, path=path))


def _frontmatter_items(text):
    lines = text.splitlines()
    if not lines or lines[0].strip() != "---":
        return []
    values = []
    for line in lines[1:]:
        if line.strip() in ("---", "..."):
            break
        if line.strip():
            values.append(line.strip())
    return values


def _fenced_blocks(text):
    _, _, blocks = _block_structure(text)
    return blocks


def _inline_items(text):
    lines, block_mask, _ = _block_structure(text)
    _, values = _inline_code_masks(lines, block_mask)
    return values


def _link_targets(text):
    values = []
    lines, block_mask, _ = _block_structure(text)
    code_masks, _ = _inline_code_masks(lines, block_mask)
    protected_masks, autolinks = _protected_inline_masks(lines, block_mask, code_masks)
    for line_number, line in enumerate(lines):
        if block_mask[line_number]:
            continue
        unavailable = list(protected_masks[line_number])
        for start, end in _link_ranges(line, unavailable):
            values.append(line[start:end])
            for index in range(start, end):
                unavailable[index] = True
        reference = _reference_target(line, unavailable)
        if reference is not None:
            start, end, value = reference
            values.append(value)
            for index in range(start, end):
                unavailable[index] = True
        for match in autolinks[line_number]:
            values.append(match.group(0)[1:-1])
    return values


def _table_columns(line):
    unavailable = [False] * len(line)
    for start, end in _inline_ranges(line):
        for index in range(start, end):
            unavailable[index] = True
    separators = [index for index, character in enumerate(line)
                  if character == "|" and not unavailable[index] and not _escaped(line, index)]
    return len(separators) - 1


def protected_inventory(text):
    table_shape = []
    for line in text.splitlines():
        stripped = line.strip()
        if stripped.startswith("|") and stripped.endswith("|"):
            table_shape.append("columns:%d" % _table_columns(stripped))
    inventory = {
        "frontmatter": _frontmatter_items(text),
        "citations": CITATION.findall(text),
        "gap_markers": GAP_MARKER.findall(text),
        "numbers": NUMBER.findall(text),
        "inline_code": _inline_items(text),
        "link_targets": _link_targets(text),
        "fenced_blocks": _fenced_blocks(text),
        "path_tokens": PATH_TOKEN.findall(text),
        "table_shape": table_shape,
    }
    return {key: sorted(values) for key, values in inventory.items()}


def _counter_difference(left, right):
    difference = Counter(left) - Counter(right)
    return [value for value in sorted(difference) for _ in range(difference[value])]


def _soft_inference_review():
    return {
        "status": "unverified",
        "questions": [
            {"kind": kind, "question": question, "requires_meaning_review": True}
            for kind, question in SOFT_INFERENCE_QUESTIONS
        ],
    }


def compare_texts(before, after):
    before_inventory = protected_inventory(before)
    after_inventory = protected_inventory(after)
    added = {}
    removed = {}
    for category in sorted(before_inventory):
        category_added = _counter_difference(after_inventory[category],
                                             before_inventory[category])
        category_removed = _counter_difference(before_inventory[category],
                                               after_inventory[category])
        if category_added:
            added[category] = category_added
        if category_removed:
            removed[category] = category_removed
    return {
        "protected_inventory_unchanged": not added and not removed,
        "before": before_inventory,
        "after": after_inventory,
        "added": added,
        "removed": removed,
        "soft_inference_review": _soft_inference_review(),
    }


def _print_comparison(result):
    state = "unchanged" if result["protected_inventory_unchanged"] else "changed"
    print("protected inventory: %s" % state)
    for change in ("removed", "added"):
        for category in sorted(result[change]):
            for value in result[change][category]:
                print("  %s %s: %r" % (change, category, value))
    print("soft-inference meaning review: unverified")
    for question in result["soft_inference_review"]["questions"]:
        print("  %s: %s" % (question["kind"], question["question"]))


def main(argv=None):
    parser = argparse.ArgumentParser(
        description="Compare protected Markdown inventory before and after a prose edit."
    )
    parser.add_argument("--compare", nargs=2, required=True, metavar=("BEFORE", "AFTER"))
    parser.add_argument("--json", action="store_true", help="emit JSON instead of text")
    args = parser.parse_args(argv)
    contents = []
    for label, path in zip(("BEFORE", "AFTER"), args.compare):
        try:
            contents.append(read_bounded_path(path, MAX_PROSE_BYTES))
        except (ValueError, UnicodeError):
            sys.stderr.write("docdna_prose: cannot read %s input: %s\n" % (label, path))
            return 2
    before, after = contents
    result = compare_texts(before, after)
    if args.json:
        print(json.dumps(result, indent=2, sort_keys=True))
    else:
        _print_comparison(result)
    return 0 if result["protected_inventory_unchanged"] else 1


if __name__ == "__main__":
    sys.exit(main())
