"""
Word-level chapter transcripts and clip subtitles.

A chapter is transcribed once (Whisper + DTW word timestamps), aligned with the
official NIV-UK text, and every clip is served by slicing those words, so moving
the timeline never re-runs Whisper. Baked transcripts live in assets/transcripts/
(committed, so they survive Render restarts); transcripts generated at runtime go
to cache/transcripts/.
"""
import json
import os
import logging
import threading
import uuid

import audio_engine
import downloader
import subtitles
import text_alignment

logger = logging.getLogger("transcripts")

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
BAKED_DIR = os.path.join(BASE_DIR, "assets", "transcripts")
RUNTIME_DIR = os.path.join(BASE_DIR, "cache", "transcripts")
FORMAT_VERSION = 1

# Whole-chapter Whisper takes ~5s on a Mac with Metal but minutes on a shared
# 0.1 vCPU, so the Docker image turns it off and falls back to per-clip Whisper.
CHAPTER_WHISPER = os.environ.get("CHAPTER_WHISPER", "1") == "1"

# Phrases of clips transcribed with Whisper in this process, by clip key
SESSION_CLIP_CACHE = {}

_words_memory = {}
_transcribe_lock = threading.Lock()

def _filename(osis: str, chapter: int) -> str:
    return f"{osis}_{chapter}.json"

def chapter_audio_path(osis: str, chapter: int) -> str:
    return os.path.join(downloader.CACHE_DIR, f"{osis}_{chapter}.mp3")

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

def available_chapters() -> dict[str, list[int]]:
    """Chapters with a transcript (they load instantly), as {osis: [chapter, ...]}."""
    chapters = {}
    for directory in (BAKED_DIR, RUNTIME_DIR):
        if not os.path.isdir(directory):
            continue
        for name in os.listdir(directory):
            if not name.endswith(".json"):
                continue
            osis, _, chapter = name[:-len(".json")].rpartition("_")
            if osis and chapter.isdigit():
                chapters.setdefault(osis, set()).add(int(chapter))
    return {osis: sorted(chs) for osis, chs in chapters.items()}

def save_words(osis: str, chapter: int, words: list[list], duration: float,
               directory: str = RUNTIME_DIR, aligned: bool = False) -> str:
    os.makedirs(directory, exist_ok=True)
    path = os.path.join(directory, _filename(osis, chapter))
    data = {
        "version": FORMAT_VERSION,
        "osis": osis,
        "chapter": chapter,
        "model": os.path.basename(subtitles.WHISPER_MODEL),
        "aligned": aligned,
        "duration": round(duration, 2),
        "words": words,
    }
    tmp_path = f"{path}.tmp"
    with open(tmp_path, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, separators=(",", ":"))
    os.replace(tmp_path, path)
    _words_memory[(osis, chapter)] = words
    return path

def align_with_official_text(osis: str, chapter: int, words: list[list]) -> tuple[list[list], bool]:
    """Take spelling and punctuation from the NIV-UK text; returns (words, aligned?)."""
    text = downloader.fetch_passage_text(osis, chapter).get("text", "")
    aligned, ratio = text_alignment.align_words_to_text(words, text)
    ok = ratio >= text_alignment.MIN_MATCH_RATIO
    if not ok:
        logger.warning(f"{osis} {chapter}: text alignment skipped (match {ratio:.2f})")
    return (aligned if ok else words), ok

def transcribe_chapter(osis: str, chapter: int, audio_path: str, directory: str = RUNTIME_DIR,
                       on_progress=None) -> list[list] | None:
    """Whisper the full chapter, align it with the official text and persist it (no-op if it exists)."""
    with _transcribe_lock:
        words = load_words(osis, chapter)
        if words:
            return words
        words = subtitles.transcribe_words(audio_path, on_progress=on_progress)
        if not words:
            return None
        words, aligned = align_with_official_text(osis, chapter, words)
        duration = audio_engine.get_audio_duration(audio_path) or words[-1][2]
        save_words(osis, chapter, words, duration, directory, aligned=aligned)
        return words

def realign_saved(osis: str, chapter: int, directory: str = BAKED_DIR) -> bool | None:
    """Align an already saved transcript with the official text. None if it was already aligned."""
    path = os.path.join(directory, _filename(osis, chapter))
    with open(path, "r", encoding="utf-8") as f:
        data = json.load(f)
    if data.get("aligned"):
        return None
    words, aligned = align_with_official_text(osis, chapter, data["words"])
    if aligned:
        save_words(osis, chapter, words, data["duration"], directory, aligned=True)
    return aligned

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

def clip_cache_key(osis: str, chapter: int, start_sec: float, end_sec: float) -> str:
    return f"{osis}_{chapter}_{start_sec:.1f}_{end_sec:.1f}"

def get_clip_phrases(osis: str, chapter: int, start_sec: float, end_sec: float,
                     should_abort=None, on_progress=None) -> tuple[list, str]:
    """
    Timed subtitle phrases for a clip, relative to its start. Returns (phrases, source):
    "chapter" (transcript slice), "session" (clip already transcribed), "whisper",
    "estimate" (no Whisper available) or "superseded" (should_abort said stop).
    on_progress(dict) receives stage updates for the background job view.
    """
    raw_audio = chapter_audio_path(osis, chapter)
    report = on_progress or (lambda update: None)

    def ensure_audio():
        if not os.path.exists(raw_audio):
            report({"stage": "download"})
        downloader.download_audio_chapter(osis, chapter)

    # 1. Slice the chapter transcript (baked, or generated now where whole-chapter Whisper is fast)
    words = load_words(osis, chapter)
    if words is None and CHAPTER_WHISPER:
        ensure_audio()
        words = transcribe_chapter(osis, chapter, raw_audio, on_progress=on_progress)
    if words:
        return clip_phrases(words, start_sec, end_sec), "chapter"

    key = clip_cache_key(osis, chapter, start_sec, end_sec)
    if key in SESSION_CLIP_CACHE:
        return SESSION_CLIP_CACHE[key], "session"

    # 2. Whisper just this clip, then fix its spelling against the chapter text
    ensure_audio()
    report({"stage": "trim"})
    temp_voice = os.path.join(BASE_DIR, "cache", f"transcribe_voice_{uuid.uuid4().hex}.mp3")
    try:
        audio_engine.trim_speech_audio(raw_audio, temp_voice, start_sec, end_sec, enhance_voice=False)
        clip_words = subtitles.transcribe_words(temp_voice, should_abort=should_abort, on_progress=on_progress)
    finally:
        if os.path.exists(temp_voice):
            os.remove(temp_voice)

    if clip_words is None:
        return [], "superseded"
    clip_duration = max(1.0, end_sec - start_sec)
    if clip_words:
        clip_words, _ = align_with_official_text(osis, chapter, clip_words)
        phrases = subtitles.words_to_phrases(clip_words, max_chars=26, clip_end=clip_duration)
        if phrases:
            SESSION_CLIP_CACHE[key] = phrases
            return phrases, "whisper"

    # 3. No Whisper available: spread the official text proportionally over the clip
    full_txt = downloader.fetch_passage_text(osis, chapter).get("text", "")
    if not full_txt:
        return [], "none"
    total_duration = audio_engine.get_audio_duration(raw_audio) or max(end_sec, 1.0)
    ratio = max(0.0, min(1.0, start_sec / max(1.0, total_duration)))
    text_words = full_txt.split()
    start_idx = int(ratio * len(text_words))
    num_words = max(8, int(clip_duration * 2.8))
    txt = " ".join(text_words[start_idx:start_idx + num_words])
    return subtitles.generate_timed_subtitles(txt, clip_duration), "estimate"
