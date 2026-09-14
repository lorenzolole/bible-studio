import re
import os
import shutil
import subprocess
import json
import logging

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger("subtitles")

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
MODELS_DIR = os.path.join(BASE_DIR, "models")
WHISPER_MODEL = os.path.join(MODELS_DIR, "ggml-base.en.bin")
CACHE_DIR = os.path.join(BASE_DIR, "cache")

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

def transcribe_with_whisper(audio_file: str, max_chars: int = 24) -> list[dict]:
    """
    Run local Metal-accelerated whisper-cli on audio file to obtain
    exact spoken timestamps down to short 3-5 word phrases.
    Returns list of dicts: [{'start': float, 'end': float, 'text': str}]
    """
    whisper_cli = find_whisper_cli()
    if not (whisper_cli and os.path.exists(whisper_cli) and os.path.exists(WHISPER_MODEL)):
        logger.warning(f"Whisper CLI ({whisper_cli}) or model ({WHISPER_MODEL}) not found, falling back to text estimation")
        return []

    temp_out_base = os.path.join(CACHE_DIR, f"whisper_{abs(hash(audio_file)) % 1000000}")
    temp_wav = f"{temp_out_base}.wav"
    temp_json = f"{temp_out_base}.json"

    # Convert audio segment to 16kHz mono WAV for fast, native whisper.cpp processing
    wav_target = audio_file
    try:
        conv_cmd = [
            "ffmpeg", "-y", "-i", audio_file,
            "-ar", "16000", "-ac", "1", "-c:a", "pcm_s16le",
            temp_wav
        ]
        subprocess.run(conv_cmd, check=True, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
        if os.path.exists(temp_wav):
            wav_target = temp_wav
    except Exception as conv_err:
        logger.warning(f"WAV pre-conversion failed ({conv_err}), falling back to direct audio")

    threads = os.environ.get("WHISPER_THREADS", "2")

    cmd = [
        whisper_cli,
        "-m", WHISPER_MODEL,
        "-f", wav_target,
        "-t", threads,
        "-ml", str(max_chars),
        "-sow",
        "-oj",
        "-of", temp_out_base,
        "--no-prints"
    ]

    try:
        logger.info(f"Running Whisper transcription on {wav_target} (threads={threads})...")
        subprocess.run(cmd, check=True, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True)
        
        if not os.path.exists(temp_json):
            logger.warning(f"Whisper JSON output missing: {temp_json}")
            return []

        with open(temp_json, "r", encoding="utf-8") as f:
            data = json.load(f)

        segments = data.get("transcription", [])
        timed_phrases = []

        for seg in segments:
            t_from = seg.get("timestamps", {}).get("from", "00:00:00,000")
            t_to = seg.get("timestamps", {}).get("to", "00:00:00,000")
            text = seg.get("text", "").strip()
            
            # Clean text
            text = re.sub(r'\[.*?\]', '', text).strip()
            if not text:
                continue

            start_sec = parse_whisper_time(t_from)
            end_sec = parse_whisper_time(t_to)

            timed_phrases.append({
                "start": round(start_sec, 2),
                "end": round(max(start_sec + 0.8, end_sec), 2),
                "text": text
            })

        logger.info(f"Whisper transcribed {len(timed_phrases)} phrases successfully.")
        return timed_phrases

    except subprocess.CalledProcessError as e:
        logger.error(f"Whisper process error (exit code {e.returncode}): {e.stderr}")
        return []
    except Exception as e:
        logger.error(f"Error during whisper transcription: {e}")
        return []
    finally:
        if os.path.exists(temp_wav):
            try:
                os.remove(temp_wav)
            except Exception:
                pass
        if os.path.exists(temp_json):
            try:
                os.remove(temp_json)
            except Exception:
                pass

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
