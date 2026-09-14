#!/usr/bin/env python3
"""
Pre-generate word-level transcripts into assets/transcripts/ so production
serves these chapters instantly (no Whisper on Render's shared CPU).

Run it on the Mac (Metal whisper, a few seconds per chapter) and commit the JSON:

  WHISPER_THREADS=8 python3 bake_transcripts.py              # popular chapters + full books
  WHISPER_THREADS=8 python3 bake_transcripts.py John 3 Ps 23 # specific chapters
  python3 bake_transcripts.py --force                        # re-transcribe existing ones
  python3 bake_transcripts.py --keep-audio                   # keep downloaded MP3s in cache/audio
"""
import os
import sys
import time

import downloader
import transcripts

POPULAR_CHAPTERS = {
    "Gen": [1, 2, 3, 22, 37, 50], "Exod": [3, 14, 20], "Num": [6], "Deut": [6, 31],
    "Josh": [1], "Ruth": [1], "1Sam": [17], "1Kgs": [19], "2Chr": [7], "Job": [38],
    "Ps": [1, 8, 16, 19, 23, 27, 34, 37, 40, 42, 46, 51, 62, 84, 90, 91, 100, 103, 121, 139, 145, 150],
    "Prov": [3, 16, 31], "Eccl": [3], "Song": [2],
    "Isa": [6, 9, 26, 40, 41, 43, 53, 55, 61], "Jer": [29, 31], "Lam": [3], "Ezek": [37],
    "Dan": [3, 6], "Mic": [6], "Hab": [3], "Zeph": [3],
    "Matt": [5, 6, 7, 11, 14, 26, 27, 28], "Mark": [4, 16], "Luke": [1, 2, 15, 23, 24],
    "John": [1, 3, 4, 6, 8, 10, 11, 14, 15, 17, 20, 21], "Acts": [2, 9],
    "Rom": [5, 8, 10, 12], "1Cor": [13, 15], "2Cor": [4, 5, 12], "Gal": [2, 5],
    "Eph": [1, 2, 3, 6], "Phil": [2, 3, 4], "Col": [3], "1Thess": [4, 5], "2Tim": [3],
    "Heb": [4, 11, 12], "Jas": [1], "1Pet": [2, 5], "1John": [1, 4], "Rev": [1, 21, 22],
}

# Books baked in full: the whole New Testament plus the most quoted Old Testament books
FULL_BOOKS = ["Gen", "Exod", "Ps", "Prov", "Isa"] + [b["osis"] for b in downloader.BIBLE_BOOKS if b["testament"] == "NT"]

def parse_targets(args: list[str]) -> list[tuple[str, int]]:
    if not args:
        chapter_counts = {b["osis"]: b["chapters"] for b in downloader.BIBLE_BOOKS}
        targets = [(osis, ch) for osis, chapters in POPULAR_CHAPTERS.items() for ch in chapters]
        targets += [(osis, ch) for osis in FULL_BOOKS for ch in range(1, chapter_counts[osis] + 1)]
        return list(dict.fromkeys(targets))
    if len(args) % 2:
        sys.exit("Usage: bake_transcripts.py [BOOK CHAPTER ...] [--force] [--keep-audio]")
    targets = []
    for book, chapter in zip(args[::2], args[1::2]):
        info = downloader.resolve_book(book)
        if not info:
            sys.exit(f"Unknown book: {book}")
        targets.append((info["osis"], int(chapter)))
    return targets

def realign_baked():
    """Align already baked transcripts with the official NIV-UK text (no Whisper needed)."""
    names = sorted(f for f in os.listdir(transcripts.BAKED_DIR) if f.endswith(".json"))
    failed = []
    for i, name in enumerate(names, 1):
        osis, _, chapter = name[:-len(".json")].rpartition("_")
        result = transcripts.realign_saved(osis, int(chapter))
        status = {None: "already aligned", True: "aligned", False: "NOT aligned"}[result]
        print(f"[{i}/{len(names)}] {osis} {chapter}: {status}")
        if result is False:
            failed.append(name)
        if result is not None:
            time.sleep(0.5)  # one BibleGateway request per chapter
    if failed:
        print("\nNot aligned (text unavailable or mismatch):", ", ".join(failed))

def main():
    flags = {"--force", "--keep-audio", "--realign"}
    if "--realign" in sys.argv:
        realign_baked()
        return
    force = "--force" in sys.argv
    keep_audio = "--keep-audio" in sys.argv
    targets = parse_targets([a for a in sys.argv[1:] if a not in flags])
    chapter_counts = {b["osis"]: b["chapters"] for b in downloader.BIBLE_BOOKS}

    suspicious = []
    for i, (osis, chapter) in enumerate(targets, 1):
        label = f"[{i}/{len(targets)}] {osis} {chapter}"
        if chapter > chapter_counts[osis]:
            print(f"{label}: invalid chapter, skipped")
            continue
        path = os.path.join(transcripts.BAKED_DIR, f"{osis}_{chapter}.json")
        if os.path.exists(path) and not force:
            print(f"{label}: already baked")
            continue
        if force and os.path.exists(path):
            os.remove(path)
            transcripts._words_memory.pop((osis, chapter), None)

        t0 = time.time()
        audio_path = os.path.join(downloader.CACHE_DIR, f"{osis}_{chapter}.mp3")
        audio_was_cached = os.path.exists(audio_path)
        try:
            audio = downloader.download_audio_chapter(osis, chapter)
            words = transcripts.transcribe_chapter(osis, chapter, audio["local_path"], directory=transcripts.BAKED_DIR)
        except Exception as e:
            print(f"{label}: failed ({e})")
            suspicious.append((osis, chapter, 0.0))
            continue
        finally:
            if not audio_was_cached and not keep_audio and os.path.exists(audio_path):
                os.remove(audio_path)
        if not words:
            print(f"{label}: Whisper returned no words")
            suspicious.append((osis, chapter, 0.0))
            continue

        # Compare against the official NIV-UK word count to catch hallucination loops or dropped audio
        official = downloader.fetch_passage_text(osis, chapter).get("text", "")
        ratio = len(words) / max(1, len(official.split())) if official else 0.0
        flag = "" if 0.9 <= ratio <= 1.15 else "  <-- check"
        if flag:
            suspicious.append((osis, chapter, ratio))
        print(f"{label}: {len(words)} words, ratio {ratio:.2f}, {time.time() - t0:.1f}s{flag}")
        time.sleep(1.0)  # be gentle with BibleGateway

    if suspicious:
        print("\nChapters to review (word ratio vs official text):")
        for osis, chapter, ratio in suspicious:
            print(f"  {osis} {chapter}: {ratio:.2f}")

if __name__ == "__main__":
    main()
