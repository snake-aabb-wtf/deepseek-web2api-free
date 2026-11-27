"""
Compress the assembled prompt before sending it to DeepSeek's web endpoint.

The web chat input accepts roughly 90,000 "English characters". We measure
length in UTF-16 code units (what the browser's JS ``.length`` sees: a CJK
char counts as 2), which is the binding constraint.

Strategy (lossless first, lossy only when necessary):
  1. Lossless normalization — collapse runs of blank lines and excessive
     horizontal whitespace without changing meaning (outside of fenced code).
  2. Bounded, meaning-preserving trims — cap any single oversized tool result
     and keep its head + tail + an elision marker.
  3. If still over budget, drop whole oldest turns from the front, replacing
     them with a one-line summary per dropped turn so the model keeps the
     thread of the conversation. Newest turns (incl. the current question)
     are always preserved intact.

The prompt is a sequence of role blocks separated by newlines:
    System: ...
    User: ...
    Assistant: ...
    Tool result (call_id=...): ...
A "turn" is a User block together with the Assistant/Tool blocks that follow
it, up to the next User block. System blocks are sticky and never dropped.
"""
from __future__ import annotations

import os
import re
import unicodedata

# 90k English chars; leave a safety margin so we stay comfortably under the
# hard web-input limit even with framing differences.
DEFAULT_LIMIT = int(os.environ.get("DEEPSEEK_PROMPT_CHAR_LIMIT", "88000") or 88000)
_SUMMARY_MARK = "[earlier conversation compressed]"

_role_re = re.compile(r"^(?:System|User|Assistant|Tool result(?: \(call_id=[^)]*\))?):", re.M)


def utf16_len(s: str) -> int:
    """Weighted length: ASCII = 1 char, CJK/fullwidth/emoji = 2 chars.

    This is the "English-character equivalent" the web input's ~90k limit is
    measured in. Counting CJK as 2 is deliberately conservative: if the web
    UI actually counts UTF-16 code units (where a BMP hanzi is 1), we stay
    safely under. Wide/Fullwidth (East Asian Width W/F) and non-BMP code
    points count as 2; everything else as 1.
    """
    if not s:
        return 0
    n = 0
    for ch in s:
        if ord(ch) > 0xFFFF or unicodedata.east_asian_width(ch) in ("W", "F"):
            n += 2
        else:
            n += 1
    return n


def tail_by_weight(s: str, budget: int) -> str:
    """Return the longest tail whose weighted length <= budget (O(n))."""
    if not s or budget <= 0:
        return ""
    total = 0
    out = []
    for ch in reversed(s):
        w = 2 if (ord(ch) > 0xFFFF or unicodedata.east_asian_width(ch) in ("W", "F")) else 1
        if total + w > budget:
            break
        out.append(ch)
        total += w
    out.reverse()
    return "".join(out)


def _normalize_block(body: str) -> str:
    """Lossless-ish whitespace compaction that never touches fenced code.

    * collapse 3+ blank lines to a single blank line
    * collapse runs of 3+ spaces/tabs (outside code fences) to one space
    """
    # Protect fenced code blocks: normalize outside them only.
    parts = re.split(r"(```.*?```)", body, flags=re.S)
    for i in range(0, len(parts), 2):  # even indices are outside fences
        seg = parts[i]
        seg = re.sub(r"[ \t]{3,}", " ", seg)
        seg = re.sub(r"\n{3,}", "\n\n", seg)
        parts[i] = seg
    return "".join(parts)


def _split_blocks(prompt: str) -> list[tuple[str, str]]:
    """Return [(role_line, body), ...]. Text before the first role is kept as one block."""
    matches = list(_role_re.finditer(prompt))
    if not matches:
        return [("", prompt)]
    blocks: list[tuple[str, str]] = []
    pre = prompt[:matches[0].start()]
    if pre.strip():
        blocks.append(("", pre.strip("\n")))
    for idx, m in enumerate(matches):
        end = matches[idx + 1].start() if idx + 1 < len(matches) else len(prompt)
        header = m.group(0)
        body = prompt[m.end():end].strip("\n")
        blocks.append((header, body))
    return blocks


def _block_text(header: str, body: str) -> str:
    return f"{header} {body}" if header else body


def _cap_tool_result(body: str, cap: int = 4000) -> str:
    """Keep head + tail of an oversized tool result with an elision marker."""
    if utf16_len(body) <= cap:
        return body
    take = cap // 2
    return body[:take] + f"\n...[{_SUMMARY_MARK}: {utf16_len(body) - cap} chars elided]...\n" + body[-take:]


def _group_turns(blocks: list[tuple[str, str]]) -> list[list[tuple[str, str]]]:
    """Group blocks into turns. System/sticky blocks form their own leading group."""
    groups: list[list[tuple[str, str]]] = []
    for header, body in blocks:
        is_system = header.startswith("System:")
        is_user = header.startswith("User:")
        if not groups or is_system and groups[-1][0][0].startswith("System:"):
            groups.append([(header, body)])
        elif is_system:
            # A later System block: keep with current turn's tail (rare).
            groups[-1].append((header, body))
        elif is_user:
            groups.append([(header, body)])
        else:
            if not groups:
                groups.append([(header, body)])
            else:
                groups[-1].append((header, body))
    return groups


def _summarize_turn(blocks: list[tuple[str, str]]) -> str:
    """One-line meaning-preserving summary of a dropped turn."""
    bits = []
    for header, body in blocks:
        if header.startswith(("User:", "Assistant:")):
            flat = re.sub(r"\s+", " ", body).strip()
            if flat:
                label = "User" if header.startswith("User:") else "Assistant"
                bits.append(f"{label}: {flat[:40]}")
    joined = " | ".join(bits) or "(non-text turn)"
    return joined


def compress_prompt(prompt: str, limit: int | None = None) -> tuple[str, dict]:
    """Return (compressed_prompt, stats). Never raises on odd input."""
    limit = limit or DEFAULT_LIMIT
    original = utf16_len(prompt)
    stats = {
        "original_chars": original,
        "limit": limit,
        "lossless_only": False,
        "dropped_turns": 0,
        "truncated": False,
    }
    if not prompt or original <= limit:
        return prompt, stats

    blocks = _split_blocks(prompt)
    # 1) lossless normalization + bounded tool results
    norm: list[tuple[str, str]] = []
    for header, body in blocks:
        b = _normalize_block(body)
        if header.startswith("Tool result"):
            b = _cap_tool_result(b)
        norm.append((header, b))
    compact = "\n".join(_block_text(h, b) for h, b in norm)
    clen = utf16_len(compact)
    if clen <= limit:
        stats.update(lossless_only=True, final_chars=clen)
        return compact, stats

    # 2) drop oldest turns (never dropping the newest), keep summaries so the
    # model retains the thread. Reserialize summaries from the *group headers*
    # only (no body text) so they stay tiny; budgets share one limit.
    def render_groups(gs):
        return "\n\n".join("\n".join(_block_text(h, b) for h, b in g) for g in gs)

    def summarize(gs):
        # Keep summaries tiny: at most 6 recent dropped turns, each <=40 chars,
        # plus one coverage line. Older dropped turns are covered by the count.
        if len(gs) <= 6:
            sample = gs
        else:
            sample = gs[-6:]
        lines = ["- " + _summarize_turn(g) for g in sample]
        if len(gs) > 6:
            lines.insert(0, f"- ({len(gs) - 6} earlier turns omitted; newest omitted turns below)")
        return "\n".join(lines)

    groups = _group_turns(norm)
    best = None
    # Try keeping the last k turns (k from all down to 1); the rest become a
    # compact summary line. Leading System group is always retained.
    sys_groups = []
    body_groups = groups
    if groups and groups[0][0][0].startswith("System:"):
        sys_groups, body_groups = groups[:1], groups[1:]
    max_k = len(body_groups)
    for k in range(max_k, 0, -1):
        kept = sys_groups + body_groups[-k:]
        dropped = body_groups[:-k] if k < max_k else []
        summary_text = summarize(dropped) if dropped else ""
        head = (_SUMMARY_MARK + ":\n" + summary_text) if summary_text else ""
        parts = ([render_groups(sys_groups)] if sys_groups else []) + ([head] if head else [])
        parts += [render_groups([g]) for g in body_groups[-k:]]
        candidate = "\n\n".join(x for x in parts if x)
        if utf16_len(candidate) <= limit:
            best = (candidate, len(dropped), summary_text, k)
            break
    if best is not None:
        final, n_dropped, _, _ = best
        stats["dropped_turns"] = n_dropped
        stats.update(final_chars=utf16_len(final))
        return final, stats

    # 3) no combination fits (single turn itself too big): keep the current
    # question whole and hard-cap the tail to the limit.
    final = render_groups([groups[-1]]) if groups else prompt
    if utf16_len(final) > limit:
        # Keep the newest block's header, cap its body by character budget.
        h, b = groups[-1][-1]
        budget = limit - utf16_len(h) - 4
        # b[-budget:] slices Python chars (hanzi=1) but budget is weighted
        # (hanzi=2); walk from the end until the weighted length fits.
        cut = tail_by_weight(b, budget)
        final = _block_text(h, cut)
        stats["truncated"] = True
    stats["dropped_turns"] = max(0, len(groups) - 1)
    stats.update(final_chars=utf16_len(final))
    return final, stats

