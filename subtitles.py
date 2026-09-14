import re
import os
import shutil
import subprocess
import json
import logging
import threading
import uuid

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger("subtitles")

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
MODELS_DIR = os.path.join(BASE_DIR, "models")
WHISPER_MODEL = os.path.join(MODELS_DIR, "ggml-base.en.bin")
CACHE_DIR = os.path.join(BASE_DIR, "cache")

# One whisper-cli process at a time: on a shared 0.1 vCPU two runs just starve each other.
WHISPER_LOCK = threading.Lock()

# DTW token alignment. Plain whisper.cpp token offsets drift up to ~1.7s from the
# spoken word; DTW timestamps land within ~0.05s of the real onset.
WHISPER_DTW = os.environ.get("WHISPER_DTW", "1") == "1"

_SENTENCE_END = re.compile(r"[.;:!?][\"'”’)]*$")
_CLAUSE_END = re.compile(r"[,—–][\"'”’)]*$")
_OPENERS = "\"'“‘("
# Words a subtitle line should not end on when it has to be cut mid-clause
_WEAK_LINE_ENDINGS = {"a", "an", "and", "as", "at", "but", "by", "for", "from", "in", "into", "his", "her",
                      "my", "nor", "of", "on", "or", "our", "so", "that", "the", "their", "to", "who", "with", "your"}

def find_whisper_cli() -> str | None:
    """Find whisper-cli binary in PATH or common macOS/Linux system directories."""
    path = shutil.which("whisper-cli")
    if path:
        return path
    for candidate in [
        "/usr/local/bin/whisper-cli",
        "/usr/bin/whisper-cli",
        "/opt/homebrew/bin/whisper-cli",
        os.path.expanduser("~/.local/bin/whisper-cli"),
    ]:
        if os.path.exists(candidate):
            return candidate
    return None

def parse_whisper_time(time_str: str) -> float:
    """Parse 'HH:MM:SS,mmm' or 'HH:MM:SS.mmm' into float seconds."""
    time_str = time_str.strip().replace(",", ".")
    parts = time_str.split(":")
    if len(parts) == 3:
        h, m, s = parts
        return int(h) * 3600 + int(m) * 60 + float(s)
    elif len(parts) == 2:
        m, s = parts
        return int(m) * 60 + float(s)
    return float(time_str)

def format_ass_time(seconds: float) -> str:
    """Format seconds into ASS timestamp: H:MM:SS.cs"""
    seconds = max(0.0, seconds)
    h = int(seconds // 3600)
    m = int((seconds % 3600) // 60)
    s = int(seconds % 60)
    cs = int(round((seconds - int(seconds)) * 100))
    if cs >= 100:
        cs = 99
    return f"{h}:{m:02d}:{s:02d}.{cs:02d}"

def _dtw_preset() -> str:
    """DTW alignment preset matching the model file, e.g. ggml-base.en.bin -> base.en"""
    name = os.path.basename(WHISPER_MODEL)
    if name.startswith("ggml-") and name.endswith(".bin"):
        return name[len("ggml-"):-len(".bin")]
    return "base.en"

def words_from_whisper_json(data: dict, duration: float | None = None) -> list[list]:
    """
    Build [[word, start, end], ...] from whisper-cli full JSON (-ojf) tokens.
    Start is the DTW onset when available; end is estimated from word length,
    never running past the next word's onset.
    """
    words = []
    for seg in data.get("transcription", []):
        for tok in seg.get("tokens", []):
            text = tok.get("text", "")
            if not text.strip() or text.startswith("[_"):
                continue
            t_dtw = tok.get("t_dtw", -1)
            if t_dtw is not None and t_dtw >= 0:
                start = t_dtw / 100.0
            else:
                start = tok.get("offsets", {}).get("from", 0) / 1000.0
            # Tokens with a leading space start a new word; the rest are sub-word pieces
            if text.startswith(" ") or not words:
                words.append([text.strip(), start, 0.0])
            else:
                words[-1][0] += text

    # Drop non-speech annotations like [BLANK_AUDIO] or (music)
    words = [w for w in words if not re.fullmatch(r"\W*[\[\(].*[\]\)]\W*", w[0])]

    # Attach standalone punctuation: opening quotes to the next word, the rest to the previous one
    merged = []
    prefix = ""
    for w in words:
        if not re.search(r"\w", w[0]):
            if w[0][0] in _OPENERS:
                prefix += w[0]
            elif merged:
                merged[-1][0] += w[0]
            continue
        if prefix:
            w[0] = prefix + w[0]
            prefix = ""
        merged.append(w)

    for i, w in enumerate(merged):
        if i and w[1] < merged[i - 1][1]:
            w[1] = merged[i - 1][1]
    for i, w in enumerate(merged):
        if i + 1 < len(merged):
            limit = merged[i + 1][1]
        else:
            limit = duration if duration else float("inf")
        w[2] = round(max(w[1] + 0.05, min(w[1] + 0.12 + 0.07 * len(w[0]), limit)), 2)
    for w in merged:
        w[1] = round(w[1], 2)
    return merged

def transcribe_words(audio_file: str, should_abort=None) -> list[list] | None:
    """
    Run whisper-cli on an audio file and return word-level timestamps
    [[word, start, end], ...]. Returns None when should_abort() says the
    request was superseded while it waited for the Whisper lock.
    """
    whisper_cli = find_whisper_cli()
    if not (whisper_cli and os.path.exists(whisper_cli) and os.path.exists(WHISPER_MODEL)):
        logger.warning(f"Whisper CLI ({whisper_cli}) or model ({WHISPER_MODEL}) not found, falling back to text estimation")
        return []

    os.makedirs(CACHE_DIR, exist_ok=True)
    out_base = os.path.join(CACHE_DIR, f"whisper_{uuid.uuid4().hex}")
    temp_wav = f"{out_base}.wav"
    temp_json = f"{out_base}.json"

    try:
        # 16kHz mono WAV is whisper.cpp's native input
        subprocess.run([
            "ffmpeg", "-y", "-i", audio_file,
            "-ar", "16000", "-ac", "1", "-c:a", "pcm_s16le",
            temp_wav
        ], check=True, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
        duration = max(0.0, (os.path.getsize(temp_wav) - 44) / 32000.0)

        threads = os.environ.get("WHISPER_THREADS", "2")
        base_cmd = [whisper_cli, "-m", WHISPER_MODEL, "-f", temp_wav, "-t", threads,
                    "-ojf", "-of", out_base, "--no-prints"]
        attempts = [base_cmd]
        if WHISPER_DTW:
            # DTW is incompatible with flash attention; retry without DTW if this build rejects it
            attempts.insert(0, base_cmd + ["-dtw", _dtw_preset(), "-nfa"])

        with WHISPER_LOCK:
            if should_abort and should_abort():
                return None
            for cmd in attempts:
                logger.info(f"Running Whisper on {audio_file} ({duration:.1f}s, threads={threads}, dtw={'-dtw' in cmd})...")
                result = subprocess.run(cmd, capture_output=True, text=True)
                # Trust the JSON, not the exit code: argument errors can still exit 0
                if result.returncode == 0 and os.path.exists(temp_json):
                    break
                logger.warning(f"whisper-cli produced no output (exit {result.returncode}, dtw={'-dtw' in cmd}): "
                               f"{(result.stderr or '')[-500:]}")
                if os.path.exists(temp_json):
                    os.remove(temp_json)

        if not os.path.exists(temp_json):
            logger.warning(f"Whisper JSON output missing: {temp_json}")
            return []

        with open(temp_json, "r", encoding="utf-8", errors="replace") as f:
            data = json.load(f)
        words = words_from_whisper_json(data, duration)
        logger.info(f"Whisper transcribed {len(words)} words.")
        return words

    except Exception as e:
        logger.error(f"Error during whisper transcription: {e}")
        return []
    finally:
        for path in (temp_wav, temp_json):
            if os.path.exists(path):
                try:
                    os.remove(path)
                except Exception:
                    pass

def words_to_phrases(words: list[list], max_chars: int = 26, clip_end: float | None = None) -> list[dict]:
    """
    Group timed words into subtitle phrases of at most max_chars, breaking at
    sentence ends, at clauses once the line is reasonably full, and at long pauses.
    Each phrase stays on screen until the next one starts (max 1.5s after its last word).
    """
    def text_of(ws):
        return " ".join(w[0] for w in ws)

    groups, cur = [], []
    for w in words:
        if cur and w[1] - cur[-1][2] > 0.8 and len(text_of(cur)) >= 8:
            groups.append(cur)
            cur = []
        while cur and len(text_of(cur)) + 1 + len(w[0]) > max_chars:
            # Prefer breaking after the last punctuation in the line over a mid-clause cut
            cut = len(cur)
            for k in range(len(cur) - 1, -1, -1):
                ends_clause = _SENTENCE_END.search(cur[k][0]) or _CLAUSE_END.search(cur[k][0])
                if ends_clause and len(text_of(cur[:k + 1])) >= 8:
                    cut = k + 1
                    break
            else:
                # No punctuation: carry dangling words ("and", "the", "in"...) over to the next line
                while cut > 2 and cur[cut - 1][0].lower() in _WEAK_LINE_ENDINGS:
                    cut -= 1
            groups.append(cur[:cut])
            cur = cur[cut:]
        cur.append(w)
        if _SENTENCE_END.search(w[0]) or (_CLAUSE_END.search(w[0]) and len(text_of(cur)) >= max_chars * 0.45):
            groups.append(cur)
            cur = []
    if cur:
        groups.append(cur)

    phrases = []
    for i, g in enumerate(groups):
        start = g[0][1]
        end = max(g[-1][2] + 1.5, start + 0.8)
        if i + 1 < len(groups):
            end = min(end, groups[i + 1][0][1])
        if clip_end is not None:
            end = min(end, clip_end)
        phrases.append({
            "start": round(start, 2),
            "end": round(max(end, start + 0.1), 2),
            "text": text_of(g)
        })
    return phrases

def transcribe_with_whisper(audio_file: str, max_chars: int = 24) -> list[dict]:
    """Whisper an audio file into subtitle phrases: [{'start', 'end', 'text'}]"""
    return words_to_phrases(transcribe_words(audio_file) or [], max_chars=max_chars)

def split_text_into_phrases(text: str, max_words: int = 5) -> list[str]:
    """Split text into short natural phrases."""
    clean_text = re.sub(r'\s+', ' ', text).strip()
    if not clean_text:
        return []
        
    clauses = re.split(r'([,.;:!?—]+)', clean_text)
    raw_segments = []
    current = ""
    
    for part in clauses:
        if re.match(r'[,.;:!?—]+', part):
            current += part
            raw_segments.append(current.strip())
            current = ""
        else:
            if current:
                raw_segments.append(current.strip())
            current = part
    if current:
        raw_segments.append(current.strip())
        
    phrases = []
    for segment in raw_segments:
        words = segment.split()
        if len(words) <= max_words:
            if segment:
                phrases.append(segment)
        else:
            for i in range(0, len(words), max_words):
                chunk = " ".join(words[i:i + max_words])
                if chunk:
                    phrases.append(chunk)
    return phrases

def generate_timed_subtitles(
    text: str,
    total_duration: float,
    start_offset: float = 0.3,
    end_offset: float = 0.5,
    max_words_per_phrase: int = 5
) -> list[dict]:
    """Fallback: distribute text phrases evenly across total duration."""
    phrases = split_text_into_phrases(text, max_words=max_words_per_phrase)
    if not phrases:
        return []
        
    usable_duration = max(1.0, total_duration - start_offset - end_offset)
    total_chars = sum(len(p) for p in phrases)
    
    timed = []
    current_t = start_offset
    for p in phrases:
        p_dur = (len(p) / total_chars) * usable_duration
        p_dur = max(1.1, p_dur)
        timed.append({
            "start": round(current_t, 2),
            "end": round(current_t + p_dur, 2),
            "text": p
        })
        current_t += p_dur
        
    if timed:
        timed[-1]["end"] = min(total_duration, timed[-1]["end"])
    return timed

def create_ass_subtitles(
    timed_phrases: list[dict],
    output_ass_path: str,
    style_name: str = "typewriter",
    citation: str = "",
    citation_duration: float = None,
    position: str = "bottom",
    text_case: str = "original",
    watermark: str = ""
) -> str:
    """Generate ASS subtitle file with configurable position, text case, and watermark."""
    os.makedirs(os.path.dirname(os.path.abspath(output_ass_path)), exist_ok=True)
    
    styles_header = """[Script Info]
Title: TikTok Bible Subtitles
ScriptType: v4.00+
PlayResX: 1080
PlayResY: 1920
ScaledBorderAndShadow: yes

[V4+ Styles]
Format: Name, Fontname, Fontsize, PrimaryColour, SecondaryColour, OutlineColour, BackColour, Bold, Italic, Underline, StrikeOut, ScaleX, ScaleY, Spacing, Angle, BorderStyle, Outline, Shadow, Alignment, MarginL, MarginR, MarginV, Encoding
"""
    
    # Calculate vertical margins based on position
    if position == "center":
        main_mv = 820
        cit_mv = 740
    else:
        main_mv = 480
        cit_mv = 380

    styles = {
        "typewriter": (
            f"Style: Main,Courier New,52,&H0084E3F7,&H000000FF,&H00000000,&HA0141414,1,0,0,0,100,100,0,0,3,10,0,2,80,80,{main_mv},1\n"
            f"Style: Citation,Georgia,36,&H00D0D0D0,&H000000FF,&H00000000,&H00000000,1,1,0,0,100,100,2,0,1,2,2,2,80,80,{cit_mv},1\n"
        ),
        "spokenbyhim": (
            f"Style: Main,Georgia,54,&H0045E1FF,&H000000FF,&H00000000,&H00000000,1,0,0,0,100,100,0,0,1,3,4,5,70,70,{120 if position == 'bottom' else 460},1\n"
            f"Style: Citation,Georgia,36,&H00FFFFFF,&H000000FF,&H00000000,&H00000000,1,1,0,0,100,100,2,0,1,2,2,2,80,80,{cit_mv},1\n"
        ),
        "classicserif": (
            f"Style: Main,Georgia,50,&H00FFFFFF,&H000000FF,&H00000000,&HA0101010,0,0,0,0,100,100,1,0,1,2,3,2,80,80,{main_mv - 20},1\n"
            f"Style: Citation,Georgia,34,&H00C5C5C5,&H000000FF,&H00000000,&H00000000,1,1,0,0,100,100,2,0,1,2,2,2,80,80,{cit_mv},1\n"
        ),
        "modern_bold": (
            f"Style: Main,Helvetica,52,&H00FFFFFF,&H000000FF,&H00000000,&H80000000,1,0,0,0,100,100,0,0,1,3,2,2,80,80,{main_mv - 20},1\n"
            f"Style: Citation,Helvetica,34,&H0084E3F7,&H000000FF,&H00000000,&H00000000,1,0,0,0,100,100,1,0,1,2,2,2,80,80,{cit_mv},1\n"
        )
    }
    
    style_content = styles.get(style_name, styles["typewriter"])
    if watermark and watermark.strip():
        style_content += "Style: Watermark,Helvetica,26,&HA0C5C5C5,&H000000FF,&H00000000,&H00000000,0,0,0,0,100,100,1,0,1,1,2,2,80,80,240,1\n"

    events_header = """\n[Events]
Format: Layer, Start, End, Style, Name, MarginL, MarginR, MarginV, Effect, Text
"""
    
    lines = []
    cit_end = citation_duration or (timed_phrases[-1]["end"] if timed_phrases else 30.0)

    if watermark and watermark.strip():
        wm_text = watermark.strip()
        lines.append(f"Dialogue: 0,0:00:00.00,{format_ass_time(cit_end)},Watermark,,0,0,0,,{wm_text}")

    if citation:
        lines.append(f"Dialogue: 0,0:00:00.00,{format_ass_time(cit_end)},Citation,,0,0,0,,— {citation.upper()} —")
        
    for p in timed_phrases:
        st = format_ass_time(p["start"])
        et = format_ass_time(p["end"])
        txt = p["text"].strip()
        if text_case == "uppercase":
            txt = txt.upper()
        lines.append(f"Dialogue: 1,{st},{et},Main,,0,0,0,,{txt}")
        
    ass_text = styles_header + style_content + events_header + "\n".join(lines) + "\n"
    
    with open(output_ass_path, "w", encoding="utf-8") as f:
        f.write(ass_text)
        
    logger.info(f"Generated ASS subtitle file: {output_ass_path}")
    return output_ass_path
