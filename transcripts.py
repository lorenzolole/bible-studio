"""
Word-level chapter transcripts.

A chapter is transcribed once (Whisper + DTW word timestamps) and every clip is
served by slicing those words, so moving the timeline never re-runs Whisper.
Baked transcripts live in assets/transcripts/ (committed, so they survive Render
restarts); transcripts generated at runtime go to cache/transcripts/.
"""
import json
import os
import logging
import threading

import audio_engine
import subtitles

logger = logging.getLogger("transcripts")

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
BAKED_DIR = os.path.join(BASE_DIR, "assets", "transcripts")
RUNTIME_DIR = os.path.join(BASE_DIR, "cache", "transcripts")
FORMAT_VERSION = 1

# Whole-chapter Whisper takes ~5s on a Mac with Metal but minutes on a shared
# 0.1 vCPU, so the Docker image turns it off and falls back to per-clip Whisper.
CHAPTER_WHISPER = os.environ.get("CHAPTER_WHISPER", "1") == "1"

_words_memory = {}
_transcribe_lock = threading.Lock()

def _filename(osis: str, chapter: int) -> str:
    return f"{osis}_{chapter}.json"

def load_words(osis: str, chapter: int) -> list[list] | None:
    """Stored [[word, start, end], ...] for a chapter, or None if it was never transcribed."""
    key = (osis, chapter)
    if key in _words_memory:
        return _words_memory[key]
    for directory in (BAKED_DIR, RUNTIME_DIR):
        path = os.path.join(directory, _filename(osis, chapter))
        if not os.path.exists(path):
            continue
        try:
            with open(path, "r", encoding="utf-8") as f:
                data = json.load(f)
            if data.get("version") == FORMAT_VERSION and data.get("words"):
                _words_memory[key] = data["words"]
                return data["words"]
        except Exception as e:
            logger.warning(f"Unreadable transcript {path}: {e}")
    return None

def has_transcript(osis: str, chapter: int) -> bool:
    return load_words(osis, chapter) is not None

def save_words(osis: str, chapter: int, words: list[list], duration: float, directory: str = RUNTIME_DIR) -> str:
    os.makedirs(directory, exist_ok=True)
    path = os.path.join(directory, _filename(osis, chapter))
    data = {
        "version": FORMAT_VERSION,
        "osis": osis,
        "chapter": chapter,
        "model": os.path.basename(subtitles.WHISPER_MODEL),
        "duration": round(duration, 2),
        "words": words,
    }
    tmp_path = f"{path}.tmp"
    with open(tmp_path, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, separators=(",", ":"))
    os.replace(tmp_path, path)
    _words_memory[(osis, chapter)] = words
    return path

def transcribe_chapter(osis: str, chapter: int, audio_path: str, directory: str = RUNTIME_DIR) -> list[list] | None:
    """Whisper the full chapter and persist its words; no-op if a transcript already exists."""
    with _transcribe_lock:
        words = load_words(osis, chapter)
        if words:
            return words
        words = subtitles.transcribe_words(audio_path)
        if not words:
            return None
        duration = audio_engine.get_audio_duration(audio_path) or words[-1][2]
        save_words(osis, chapter, words, duration, directory)
        return words

def slice_words(words: list[list], start: float, end: float) -> list[list]:
    """Words spoken inside the clip, re-timed relative to start. A word starting in the
    last 0.35s would be cut off by the audio trim, so it is left out."""
    clip = []
    for text, w_start, w_end in words:
        if start - 0.1 <= w_start < end - 0.35:
            clip.append([text, round(max(0.0, w_start - start), 2), round(min(w_end, end) - start, 2)])
    return clip

def clip_phrases(words: list[list], start: float, end: float, max_chars: int = 26) -> list[dict]:
    """Subtitle phrases for a clip of the chapter, timed relative to the clip start."""
    phrases = subtitles.words_to_phrases(slice_words(words, start, end), max_chars=max_chars, clip_end=round(end - start, 2))
    # A clip cut mid-sentence can leave a dangling "and" / "the" as its last line
    if phrases and all(w.lower() in subtitles._WEAK_LINE_ENDINGS for w in phrases[-1]["text"].split()):
        phrases.pop()
    return phrases
