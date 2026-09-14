---
title: Bible Studio
emoji: ✝️
colorFrom: gray
colorTo: yellow
sdk: docker
app_port: 7860
pinned: false
---

# ✝ Bible Studio — Sacred Scripture Video Generator

Automated suite and web studio to generate high-retention vertical videos (9:16, 1080×1920) for TikTok, Instagram Reels, and YouTube Shorts featuring **David Suchet's** official NIV-UK spoken narration from BibleGateway, sacred classical art, atmospheric worship soundscapes, and synchronized subtitles.

---

## ✨ Features

1. **Complete 66-Book NIV-UK Biblical Audio**:
   - Spoken by renowned British actor David Suchet.
   - Quick access to viral calibrated passages (John 3:16, Psalm 23, Romans 8, Isaiah 40, etc.).
2. **Interactive Audio Trimmer & Text Reader**:
   - Dual-handle scrubber for exact second-level snippet selection.
   - Real-time scripture text viewer with phrase synchronization.
3. **Sacred Art Library & Visual Modes**:
   - Classical oil paintings and etching engravings (Rembrandt, Dürer, Caravaggio).
   - **Canvas Modes**:
     - `pitch_black`: Pure black background (`#000000`) with artwork framed in golden ratio with rounded corners.
     - `fullscreen`: Full vertical coverage with subtle cinematic vignetting.
     - `ambient`: Immersive blurred ambient backdrop.
   - Ultra-smooth Ken Burns continuous slow camera push-in.
4. **Viral Worship & Atmospheric Soundtracks**:
   - Integrated curated ambient tracks with intelligent vocal sidechain ducking.
5. **GPU/CPU Accelerated Whisper Subtitles**:
   - Word-level timing using `whisper-cli`.
   - Typography styles: Typewriter, SpokenByHim, ClassicSerif, ModernBold.
6. **Mobile Preview & Batch Library**:
   - Real-time phone viewport mockup with custom handle watermark overlay (`@channel`).
   - One-click rendering and downloaded video library.

---

## 🚀 Running Locally

```bash
# Clone the repository
git clone https://github.com/lorenzolole/bible-studio.git
cd bible-studio

# Run local setup script
./run.sh
```

Or with Docker:

```bash
docker build -t bible-studio .
docker run -p 7860:7860 bible-studio
```

Open `http://localhost:7860` (or `http://localhost:8000` when running `./run.sh`) in your browser.

---

## 💻 CLI Usage

```bash
python3 create_clip.py --book "Salmos" --chapter 23 --start 0 --end 15 --citation "PSALM 23:1-3" --style typewriter
```

---

## 📁 Project Structure

- `app.py`: FastAPI server with audio trimming, transcription, and render orchestration.
- `downloader.py`: Audio extraction engine for BibleGateway David Suchet narration.
- `audio_engine.py`: Audio processing pipeline with vocal compression and music ducking.
- `subtitles.py`: ASS subtitle generator with whisper-cli word-level (DTW) transcription.
- `transcripts.py`: Per-chapter word transcripts, sliced instantly for any clip.
- `text_alignment.py`: Aligns Whisper word timings with the official NIV-UK text.
- `beats.py`: Numpy beat tracker used to cut the "Jesus Edit" montage on the music's beats.
- `figures.py`: Cached still layers (foreground figures with glow, frame finishes, fullscreen vignette).
- `tools/lift_subject.js`: Cuts a subject out of an artwork with Apple Vision to create new figures.
- `docs/CODEX_PROMPTS.md`: Prompts to generate new figures and montage artworks with Codex.
- `bake_transcripts.py`: Pre-generates transcripts for popular chapters into `assets/transcripts/`.
- `video_engine.py`: FFmpeg vertical video compositor with motion & vignette filters.
- `create_clip.py`: Command-line batch generator.
- `assets/`: Sacred visuals, background worship audio, and cinematic overlays.
- `Dockerfile`: Multi-stage build for Hugging Face Spaces and containerized deployment.
