"""
Align Whisper word timestamps with the official NIV-UK text.

Whisper times words well but misspells names and splits or merges words
("for knew" for "foreknew", "Curia Thaba" for "Kiriath Arba"). The official text
is always right about the words, so we keep Whisper's timing and take the words,
punctuation and capitalization from the official text.
"""
import difflib
import re

_OPENERS = "\"'“‘("
_DASHES = {"–", "—", "-"}
# Below this share of matching words the audio and text probably don't correspond; keep Whisper's words
MIN_MATCH_RATIO = 0.6

def _key(word: str) -> str:
    """Comparison key: lowercase letters and digits only."""
    return re.sub(r"[\W_]", "", word.lower())

def tokenize_text(text: str) -> list[str]:
    """Split text into words, attaching standalone punctuation to a neighbour word."""
    tokens = []
    prefix = ""
    for raw in text.split():
        if not re.search(r"\w", raw):
            if raw[0] in _OPENERS:
                prefix += raw
            elif tokens:
                tokens[-1] += (" " + raw) if raw in _DASHES else raw
            continue
        tokens.append(prefix + raw)
        prefix = ""
    return tokens

def _distribute(tokens: list[str], start: float, end: float) -> list[list]:
    """Spread tokens over [start, end] proportionally to their length."""
    span = max(0.0, end - start)
    total_chars = sum(len(t) for t in tokens) or 1
    out = []
    t = start
    for tok in tokens:
        dur = span * len(tok) / total_chars
        out.append([tok, round(t, 2), round(t + max(0.05, dur), 2)])
        t += dur
    return out

def align_words_to_text(words: list[list], text: str) -> tuple[list[list], float]:
    """
    Replace Whisper's spelling with the official text while keeping its timestamps.
    Works for a whole chapter or for a clip against its chapter text. Words outside
    the matched stretch (e.g. the spoken "Psalm 23" heading) keep Whisper's spelling.
    Returns (aligned words, share of Whisper words that matched the text exactly).
    """
    tokens = tokenize_text(text or "")
    if not words or not tokens:
        return words, 0.0
    w_keys = [_key(w[0]) for w in words]
    t_keys = [_key(t) for t in tokens]

    # Locate the stretch of text the audio covers: the longest exact run, widened by the
    # words Whisper heard before and after it (a clip only covers a few verses)
    longest = difflib.SequenceMatcher(None, w_keys, t_keys, autojunk=False).find_longest_match(
        0, len(w_keys), 0, len(t_keys))
    if longest.size < min(3, len(w_keys)):
        return words, 0.0
    slack = 10
    t_from = max(0, longest.b - longest.a - slack)
    t_to = min(len(t_keys), longest.b + longest.size + (len(w_keys) - longest.a - longest.size) + slack)

    matcher = difflib.SequenceMatcher(None, w_keys, t_keys[t_from:t_to], autojunk=False)
    blocks = [b for b in matcher.get_matching_blocks() if b.size >= 2] or \
             [b for b in matcher.get_matching_blocks() if b.size]
    w_lo, w_hi = blocks[0].a, blocks[-1].a + blocks[-1].size
    t_lo, t_hi = t_from + blocks[0].b, t_from + blocks[-1].b + blocks[-1].size
    matched = sum(b.size for b in matcher.get_matching_blocks() if w_lo <= b.a < w_hi)
    ratio = matched / max(1, w_hi - w_lo)
    if ratio < MIN_MATCH_RATIO:
        return words, ratio

    inner_w = words[w_lo:w_hi]
    inner_t = tokens[t_lo:t_hi]
    out = [list(w) for w in words[:w_lo]]
    ops = difflib.SequenceMatcher(None, w_keys[w_lo:w_hi], t_keys[t_lo:t_hi], autojunk=False).get_opcodes()
    for tag, i1, i2, j1, j2 in ops:
        if tag == "equal":
            for k in range(i2 - i1):
                w = inner_w[i1 + k]
                out.append([inner_t[j1 + k], w[1], w[2]])
        elif tag == "delete":
            # Spoken but not in the text: keep what Whisper heard
            out.extend(list(w) for w in inner_w[i1:i2])
        elif tag == "replace":
            # Official words take over the time span of the words Whisper got wrong
            out.extend(_distribute(inner_t[j1:j2], inner_w[i1][1], inner_w[i2 - 1][2]))
        else:  # insert: Whisper skipped words; fit them between the neighbours
            prev_end = out[-1][2] if out else inner_w[0][1]
            next_start = inner_w[i1][1] if i1 < len(inner_w) else prev_end
            out.extend(_distribute(inner_t[j1:j2], min(prev_end, next_start), next_start))
    out.extend(list(w) for w in words[w_hi:])

    # Keep onsets monotonic and ends before the next onset
    for i in range(1, len(out)):
        if out[i][1] < out[i - 1][1]:
            out[i][1] = out[i - 1][1]
    for i, w in enumerate(out):
        limit = out[i + 1][1] if i + 1 < len(out) else w[2]
        w[2] = round(max(w[1] + 0.05, min(w[2], limit)), 2)
    return out, ratio
