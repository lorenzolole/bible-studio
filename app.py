import json
import os
import shutil
import time
import logging
import subprocess
from fastapi import FastAPI, UploadFile, File, Form, HTTPException
from fastapi.responses import HTMLResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel
from typing import List, Union, Optional

import downloader
import audio_engine
import subtitles
import video_engine

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger("tiktok_bible_app")

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
CACHE_DIR = os.path.join(BASE_DIR, "cache")
OUTPUTS_DIR = os.path.join(BASE_DIR, "outputs")
OUTPUTS_THUMBS = os.path.join(OUTPUTS_DIR, "thumbnails")
ASSETS_DIR = os.path.join(BASE_DIR, "assets")
VISUALS_DIR = os.path.join(ASSETS_DIR, "visuals")
MUSIC_DIR = os.path.join(ASSETS_DIR, "music")
THUMBS_DIR = os.path.join(ASSETS_DIR, "thumbnails")
UPLOADS_DIR = os.path.join(CACHE_DIR, "uploads")

os.makedirs(CACHE_DIR, exist_ok=True)
os.makedirs(OUTPUTS_DIR, exist_ok=True)
os.makedirs(OUTPUTS_THUMBS, exist_ok=True)
os.makedirs(VISUALS_DIR, exist_ok=True)
os.makedirs(MUSIC_DIR, exist_ok=True)
os.makedirs(THUMBS_DIR, exist_ok=True)
os.makedirs(UPLOADS_DIR, exist_ok=True)

app = FastAPI(title="Bible Studio")

app.mount("/static", StaticFiles(directory=os.path.join(BASE_DIR, "static")), name="static")
app.mount("/cache", StaticFiles(directory=CACHE_DIR), name="cache")
app.mount("/assets", StaticFiles(directory=ASSETS_DIR), name="assets")
app.mount("/thumbnails", StaticFiles(directory=THUMBS_DIR), name="thumbnails")
app.mount("/outputs", StaticFiles(directory=OUTPUTS_DIR), name="outputs")

class TranscribeRequest(BaseModel):
    book: str
    chapter: int
    start_sec: float
    end_sec: float

class RenderRequest(BaseModel):
    book: str
    chapter: int
    start_sec: float
    end_sec: float
    citation: str
    visual_paths: Union[str, List[str]]
    music_path: str = ""
    music_volume: float = 0.16
    subtitle_style: str = "typewriter"
    enable_subtitles: bool = True
    corner_radius: int = 42
    phrases: Optional[List[dict]] = None
    custom_text: Optional[str] = None
    slideshow_pacing: str = "cinematic"
    watermark: Optional[str] = None
    subtitle_position: str = "bottom"
    text_case: str = "original"
    framing_mode: str = "pitch_black"
    enable_particles: bool = True
    enable_light_leak: bool = True
    enable_dynamic_motion: bool = True
    enable_film_grain: bool = True

@app.get("/", response_class=HTMLResponse)
async def read_index():
    template_path = os.path.join(BASE_DIR, "templates", "index.html")
    with open(template_path, "r", encoding="utf-8") as f:
        return HTMLResponse(content=f.read())

@app.get("/api/books")
async def get_books():
    return {"books": downloader.BIBLE_BOOKS}

@app.get("/api/chapter_info")
async def get_chapter_info(book: str, chapter: int):
    try:
        audio_info = downloader.download_audio_chapter(book, chapter)
        passage = downloader.fetch_passage_text(book, chapter)
        duration = audio_engine.get_audio_duration(audio_info["local_path"])
        rel_audio_url = f"/cache/audio/{os.path.basename(audio_info['local_path'])}"
        
        return {
            "success": True,
            "book": audio_info["book"],
            "chapter": chapter,
            "audio_url": rel_audio_url,
            "duration": round(duration, 2),
            "passage": passage
        }
    except Exception as e:
        logger.error(f"Error getting chapter info: {e}")
        raise HTTPException(status_code=500, detail=str(e))

@app.get("/api/chapter_transcription")
async def get_chapter_transcription(book: str, chapter: int):
    try:
        book_info = downloader.resolve_book(book)
        if not book_info:
            raise HTTPException(status_code=400, detail="Invalid book")
        osis = book_info["osis"]
        raw_audio = os.path.join(CACHE_DIR, "audio", f"{osis}_{chapter}.mp3")
        if not os.path.exists(raw_audio):
            downloader.download_audio_chapter(book, chapter)
        
        json_path = f"{raw_audio}.json"
        if not os.path.exists(json_path):
            whisper_bin = subtitles.find_whisper_cli() or "whisper-cli"
            cmd = [whisper_bin, "-m", subtitles.WHISPER_MODEL, "-f", raw_audio, "-oj", "-of", raw_audio, "--no-prints"]
            try:
                subprocess.run(cmd, check=True, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
            except Exception as err:
                logger.warning(f"Chapter-wide whisper skipped or failed: {err}")
            
        if os.path.exists(json_path):
            with open(json_path, "r", encoding="utf-8") as f:
                data = json.load(f)
            segments = data.get("transcription", [])
            phrases = []
            for seg in segments:
                t_from = seg.get("timestamps", {}).get("from", "00:00:00,000")
                t_to = seg.get("timestamps", {}).get("to", "00:00:00,000")
                text = seg.get("text", "").strip()
                if not text:
                    continue
                start_sec = subtitles.parse_whisper_time(t_from)
                end_sec = subtitles.parse_whisper_time(t_to)
                phrases.append({
                    "start": round(start_sec, 2),
                    "end": round(max(start_sec + 0.8, end_sec), 2),
                    "text": text
                })
            return {"success": True, "phrases": phrases}
        return {"success": True, "phrases": []}
    except Exception as e:
        logger.error(f"Error getting chapter transcription: {e}")
        return {"success": False, "phrases": [], "error": str(e)}

@app.post("/api/transcribe")
async def transcribe_audio_segment(req: TranscribeRequest):
    try:
        book_info = downloader.resolve_book(req.book)
        if not book_info:
            raise HTTPException(status_code=400, detail="Invalid book")
        osis = book_info["osis"]
        raw_audio = os.path.join(CACHE_DIR, "audio", f"{osis}_{req.chapter}.mp3")
        if not os.path.exists(raw_audio):
            downloader.download_audio_chapter(req.book, req.chapter)

        timestamp = int(time.time() * 1000)
        temp_voice = os.path.join(CACHE_DIR, f"transcribe_voice_{timestamp}.mp3")
        audio_engine.trim_speech_audio(raw_audio, temp_voice, req.start_sec, req.end_sec, enhance_voice=False)

        phrases = subtitles.transcribe_with_whisper(temp_voice, max_chars=26)
        if not phrases:
            # Fallback to chapter text aligned proportionally to the selected time range
            passage = downloader.fetch_passage_text(req.book, req.chapter)
            full_txt = passage.get("text", "")
            if full_txt:
                total_duration = audio_engine.get_audio_duration(raw_audio) or max(req.end_sec, 1.0)
                ratio = max(0.0, min(1.0, req.start_sec / max(1.0, total_duration)))
                words = full_txt.split()
                start_idx = int(ratio * len(words))
                segment_duration = max(1.0, req.end_sec - req.start_sec)
                num_words = max(8, int(segment_duration * 2.8))
                segment_words = words[start_idx : start_idx + num_words]
                txt = " ".join(segment_words)
                phrases = subtitles.generate_timed_subtitles(txt, segment_duration)

        if os.path.exists(temp_voice):
            os.remove(temp_voice)

        return {"success": True, "phrases": phrases}
    except Exception as e:
        logger.error(f"Transcription failed: {e}")
        raise HTTPException(status_code=500, detail=str(e))

@app.get("/api/presets")
async def get_presets():
    visuals = [
        {
            "id": "tiktok_pfp_jesus.jpg",
            "name": "Jesús en Claroscuro (PFP Oficial)",
            "category": "Arte Bíblico",
            "path": "assets/visuals/tiktok_pfp_jesus.jpg",
            "thumb": "/thumbnails/tiktok_pfp_jesus.jpg",
            "url": "/assets/visuals/tiktok_pfp_jesus.jpg",
            "type": "image"
        },
        {
            "id": "jesus_shepherd_etching.jpg",
            "name": "El Buen Pastor (Grabado @nehzro)",
            "category": "Arte Bíblico",
            "path": "assets/visuals/jesus_shepherd_etching.jpg",
            "thumb": "/thumbnails/jesus_shepherd_etching.jpg",
            "url": "/assets/visuals/jesus_shepherd_etching.jpg",
            "type": "image"
        },
        {
            "id": "jesus_cross_icon.jpg",
            "name": "Cristo con la Cruz (Icono @nanagoes5)",
            "category": "Arte Bíblico",
            "path": "assets/visuals/jesus_cross_icon.jpg",
            "thumb": "/thumbnails/jesus_cross_icon.jpg",
            "url": "/assets/visuals/jesus_cross_icon.jpg",
            "type": "image"
        },
        {
            "id": "jesus_walking_waves.jpg",
            "name": "Salvando a Pedro en las Aguas",
            "category": "Arte Bíblico",
            "path": "assets/visuals/jesus_walking_waves.jpg",
            "thumb": "/thumbnails/jesus_walking_waves.jpg",
            "url": "/assets/visuals/jesus_walking_waves.jpg",
            "type": "image"
        },
        {
            "id": "jesus_light_world.jpg",
            "name": "La Luz del Mundo (Puerta)",
            "category": "Arte Bíblico",
            "path": "assets/visuals/jesus_light_world.jpg",
            "thumb": "/thumbnails/jesus_light_world.jpg",
            "url": "/assets/visuals/jesus_light_world.jpg",
            "type": "image"
        },
        {
            "id": "jesus_good_shepherd.jpg",
            "name": "El Buen Pastor (Óleo Clásico)",
            "category": "Arte Bíblico",
            "path": "assets/visuals/jesus_good_shepherd.jpg",
            "thumb": "/thumbnails/jesus_good_shepherd.jpg",
            "url": "/assets/visuals/jesus_good_shepherd.jpg",
            "type": "image"
        },
        {
            "id": "moses_mount_sinai.jpg",
            "name": "Moisés en el Monte Sinaí",
            "category": "Arte Bíblico",
            "path": "assets/visuals/moses_mount_sinai.jpg",
            "thumb": "/thumbnails/moses_mount_sinai.jpg",
            "url": "/assets/visuals/moses_mount_sinai.jpg",
            "type": "image"
        },
        {
            "id": "isaiah_prophet_temple.jpg",
            "name": "El Profeta Isaías en el Templo",
            "category": "Arte Bíblico",
            "path": "assets/visuals/isaiah_prophet_temple.jpg",
            "thumb": "/thumbnails/isaiah_prophet_temple.jpg",
            "url": "/assets/visuals/isaiah_prophet_temple.jpg",
            "type": "image"
        },
        {
            "id": "crossing_red_sea.jpg",
            "name": "El Paso del Mar Rojo",
            "category": "Arte Bíblico",
            "path": "assets/visuals/crossing_red_sea.jpg",
            "thumb": "/thumbnails/crossing_red_sea.jpg",
            "url": "/assets/visuals/crossing_red_sea.jpg",
            "type": "image"
        },
        {
            "id": "christ_in_gethsemane.jpg",
            "name": "Cristo en Getsemaní",
            "category": "Arte Bíblico",
            "path": "assets/visuals/christ_in_gethsemane.jpg",
            "thumb": "/thumbnails/christ_in_gethsemane.jpg",
            "url": "/assets/visuals/christ_in_gethsemane.jpg",
            "type": "image"
        },
        {
            "id": "storm_on_galilee.jpg",
            "name": "Tormenta en Galilea",
            "category": "Arte Bíblico",
            "path": "assets/visuals/storm_on_galilee.jpg",
            "thumb": "/thumbnails/storm_on_galilee.jpg",
            "url": "/assets/visuals/storm_on_galilee.jpg",
            "type": "image"
        },
        {
            "id": "christ_walking_water.jpg",
            "name": "Caminando sobre las Aguas",
            "category": "Arte Bíblico",
            "path": "assets/visuals/christ_walking_water.jpg",
            "thumb": "/thumbnails/christ_walking_water.jpg",
            "url": "/assets/visuals/christ_walking_water.jpg",
            "type": "image"
        },
        {
            "id": "resurrection_dawn.jpg",
            "name": "Amanecer de Resurrección",
            "category": "Arte Bíblico",
            "path": "assets/visuals/resurrection_dawn.jpg",
            "thumb": "/thumbnails/resurrection_dawn.jpg",
            "url": "/assets/visuals/resurrection_dawn.jpg",
            "type": "image"
        },
        {
            "id": "creation_light.jpg",
            "name": "Creación de la Luz",
            "category": "Arte Bíblico",
            "path": "assets/visuals/creation_light.jpg",
            "thumb": "/thumbnails/creation_light.jpg",
            "url": "/assets/visuals/creation_light.jpg",
            "type": "image"
        },
        {
            "id": "king_david_harp.jpg",
            "name": "Rey David y el Arpa Sagrada",
            "category": "Arte Bíblico",
            "path": "assets/visuals/king_david_harp.jpg",
            "thumb": "/thumbnails/king_david_harp.jpg",
            "url": "/assets/visuals/king_david_harp.jpg",
            "type": "image"
        },
        {
            "id": "sunset_mountains.jpg",
            "name": "Atardecer en la Montaña",
            "category": "Naturaleza",
            "path": "assets/visuals/sunset_mountains.jpg",
            "thumb": "/thumbnails/sunset_mountains.jpg",
            "url": "/assets/visuals/sunset_mountains.jpg",
            "type": "image"
        },
        {
            "id": "loop_good_shepherd.mp4",
            "name": "Bucle: El Buen Pastor",
            "category": "Video Loops",
            "path": "assets/visuals/loop_good_shepherd.mp4",
            "thumb": "/thumbnails/loop_good_shepherd.jpg",
            "url": "/assets/visuals/loop_good_shepherd.mp4",
            "type": "video"
        }
    ]

    collections = [
        {
            "id": "col_jesus_sacred",
            "name": "Jesús: Claroscuro & Sagrado (@nehzro / @nanagoes5)",
            "description": "Estética viral sobria: Jesús en claroscuro, grabado del Buen Pastor, icono bizantino con la cruz y salvando en las aguas",
            "paths": [
                "assets/visuals/tiktok_pfp_jesus.jpg",
                "assets/visuals/jesus_shepherd_etching.jpg",
                "assets/visuals/jesus_cross_icon.jpg",
                "assets/visuals/jesus_walking_waves.jpg",
                "assets/visuals/jesus_light_world.jpg"
            ],
            "thumb": "/thumbnails/tiktok_pfp_jesus.jpg"
        },
        {
            "id": "col_covenant_prophets",
            "name": "Profetas, Alianza & Éxodo",
            "description": "Gran epopeya bíblica: Creación de la Luz, El Paso del Mar Rojo, Moisés en el Monte Sinaí, el Rey David e Isaías",
            "paths": [
                "assets/visuals/creation_light.jpg",
                "assets/visuals/crossing_red_sea.jpg",
                "assets/visuals/moses_mount_sinai.jpg",
                "assets/visuals/king_david_harp.jpg",
                "assets/visuals/isaiah_prophet_temple.jpg"
            ],
            "thumb": "/thumbnails/moses_mount_sinai.jpg"
        },
        {
            "id": "col_jesus_life",
            "name": "Vida y Milagros de Jesús",
            "description": "Pasajes del Evangelio: El Buen Pastor, Aguas de Galilea, Getsemaní, Tormenta y Resurrección",
            "paths": [
                "assets/visuals/jesus_good_shepherd.jpg",
                "assets/visuals/christ_walking_water.jpg",
                "assets/visuals/christ_in_gethsemane.jpg",
                "assets/visuals/storm_on_galilee.jpg",
                "assets/visuals/resurrection_dawn.jpg"
            ],
            "thumb": "/thumbnails/christ_walking_water.jpg"
        },
        {
            "id": "col_peace_glory",
            "name": "Paz & Majestad Celestial",
            "description": "Composiciones serenas de contemplación: El Buen Pastor, Isaías en adoración, atardecer y amanecer",
            "paths": [
                "assets/visuals/jesus_good_shepherd.jpg",
                "assets/visuals/isaiah_prophet_temple.jpg",
                "assets/visuals/sunset_mountains.jpg",
                "assets/visuals/resurrection_dawn.jpg"
            ],
            "thumb": "/thumbnails/isaiah_prophet_temple.jpg"
        }
    ]

    music_titles = {
        "Emile_Mosseri_Jacob_And_The_Stone.mp3": "Jacob and the Stone — Emile Mosseri (Minari)",
        "Salvia_Palth_Dream.mp3": "(dream) — Salvia Palth",
        "Disasterpeace_The_Sound_Of_Myself.mp3": "The Sound of Myself — Disasterpeace",
        "Soil_Wilderness.mp3": "Wilderness — Soil",
        "Cloud9ine_Magic_Slowed_Reverb.mp3": "Magic (Slowed + Reverb) — cloud9ine",
        "Daniel_mp3_Gods_Creation.mp3": "Gods Creation — daniel.mp3",
        "Arcade_Fire_Owen_Pallett_Dimensions.mp3": "Dimensions — Arcade Fire, Owen Pallett"
    }

    music = []
    for f in sorted(os.listdir(MUSIC_DIR)):
        if f.lower().endswith((".mp3", ".wav", ".m4a")):
            name = music_titles.get(f, f.replace("_", " ").title().split(".")[0])
            music.append({
                "id": f,
                "name": name,
                "path": os.path.join("assets", "music", f),
                "url": f"/assets/music/{f}"
            })
            
    return {"visuals": visuals, "collections": collections, "music": music}

@app.post("/api/upload_visual")
async def upload_visual(file: UploadFile = File(...)):
    filename = f"upload_{int(time.time())}_{file.filename}"
    save_path = os.path.join(UPLOADS_DIR, filename)
    with open(save_path, "wb") as buffer:
        shutil.copyfileobj(file.file, buffer)
        
    return {
        "success": True,
        "path": save_path,
        "url": f"/cache/uploads/{filename}",
        "thumb": f"/cache/uploads/{filename}",
        "name": file.filename
    }

@app.post("/api/upload_music")
async def upload_music(file: UploadFile = File(...)):
    filename = f"upload_music_{int(time.time())}_{file.filename}"
    save_path = os.path.join(UPLOADS_DIR, filename)
    with open(save_path, "wb") as buffer:
        shutil.copyfileobj(file.file, buffer)
        
    return {
        "success": True,
        "path": save_path,
        "url": f"/cache/uploads/{filename}",
        "name": file.filename
    }

@app.post("/api/render")
async def render_video(req: RenderRequest):
    try:
        book_info = downloader.resolve_book(req.book)
        if not book_info:
            raise HTTPException(status_code=400, detail="Invalid book")
            
        osis = book_info["osis"]
        book_name_clean = book_info["name_es"].replace(" ", "_").replace("á","a").replace("é","e").replace("í","i").replace("ó","o").replace("ú","u")
        raw_audio = os.path.join(CACHE_DIR, "audio", f"{osis}_{req.chapter}.mp3")
        if not os.path.exists(raw_audio):
            downloader.download_audio_chapter(req.book, req.chapter)
            
        timestamp = int(time.time())
        clip_duration = req.end_sec - req.start_sec
        trimmed_voice = os.path.join(CACHE_DIR, f"voice_{osis}_{req.chapter}_{timestamp}.mp3")
        audio_engine.trim_speech_audio(
            raw_audio,
            trimmed_voice,
            start_sec=req.start_sec,
            end_sec=req.end_sec,
            enhance_voice=True
        )

        english_citation = downloader.normalize_citation_english(req.citation)

        ass_path = None
        if req.enable_subtitles and req.subtitle_style != "none":
            if req.phrases and len(req.phrases) > 0:
                timed_phrases = req.phrases
            else:
                timed_phrases = subtitles.transcribe_with_whisper(trimmed_voice, max_chars=26)
                if not timed_phrases:
                    txt = req.custom_text or downloader.fetch_passage_text(req.book, req.chapter).get("text", "")
                    timed_phrases = subtitles.generate_timed_subtitles(txt, clip_duration)

            ass_path = os.path.join(CACHE_DIR, f"sub_{osis}_{req.chapter}_{timestamp}.ass")
            subtitles.create_ass_subtitles(
                timed_phrases=timed_phrases,
                output_ass_path=ass_path,
                style_name=req.subtitle_style,
                citation=english_citation,
                citation_duration=clip_duration,
                position=req.subtitle_position,
                text_case=req.text_case,
                watermark=req.watermark or ""
            )
        elif req.citation or req.watermark:
            # Subtitles disabled, but user provided citation or watermark
            ass_path = os.path.join(CACHE_DIR, f"sub_cit_{osis}_{req.chapter}_{timestamp}.ass")
            subtitles.create_ass_subtitles(
                timed_phrases=[],
                output_ass_path=ass_path,
                style_name="classicserif",
                citation=english_citation,
                citation_duration=clip_duration,
                position=req.subtitle_position,
                text_case=req.text_case,
                watermark=req.watermark or ""
            )
        
        if isinstance(req.visual_paths, list):
            resolved_vis = [p if os.path.isabs(p) else os.path.join(BASE_DIR, p) for p in req.visual_paths]
        else:
            resolved_vis = req.visual_paths if os.path.isabs(req.visual_paths) else os.path.join(BASE_DIR, req.visual_paths)

        mus_path = req.music_path
        if mus_path and not os.path.isabs(mus_path):
            mus_path = os.path.join(BASE_DIR, mus_path)
            
        # Human-readable filename
        out_filename = f"{book_name_clean}_{req.chapter}_{int(clip_duration)}s_{time.strftime('%H%M%S')}.mp4"
        out_path = os.path.join(OUTPUTS_DIR, out_filename)
        
        video_engine.render_tiktok_video(
            voice_audio=trimmed_voice,
            visual_path=resolved_vis,
            music_audio=mus_path if mus_path and os.path.exists(mus_path) else None,
            subtitle_ass=ass_path,
            output_path=out_path,
            music_volume=req.music_volume,
            corner_radius=req.corner_radius,
            slideshow_pacing=req.slideshow_pacing,
            framing_mode=req.framing_mode,
            whisper_phrases=timed_phrases if timed_phrases else None,
            enable_particles=req.enable_particles,
            enable_light_leak=req.enable_light_leak,
            enable_dynamic_motion=req.enable_dynamic_motion,
            enable_film_grain=req.enable_film_grain
        )

        # Generate thumbnail for library
        thumb_filename = os.path.splitext(out_filename)[0] + ".jpg"
        thumb_path = os.path.join(OUTPUTS_THUMBS, thumb_filename)
        subprocess.run([
            "ffmpeg", "-y", "-ss", f"{min(2.0, clip_duration / 2):.1f}", "-i", out_path,
            "-vframes", "1",
            "-vf", "scale=160:284:force_original_aspect_ratio=increase,crop=160:284",
            thumb_path
        ], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
        
        return {
            "success": True,
            "filename": out_filename,
            "video_url": f"/outputs/{out_filename}",
            "thumb_url": f"/outputs/thumbnails/{thumb_filename}",
            "duration": clip_duration,
            "title": f"{book_info['name_es']} {req.chapter}"
        }
    except Exception as e:
        logger.error(f"Render failed: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=str(e))

def get_video_duration_fast(fpath):
    try:
        res = subprocess.run([
            "ffprobe", "-v", "error", "-show_entries", "format=duration",
            "-of", "default=noprint_wrappers=1:nokey=1", fpath
        ], capture_output=True, text=True, timeout=2)
        sec = float(res.stdout.strip())
        if sec < 60:
            return f"{int(round(sec))}s"
        else:
            m = int(sec // 60)
            s = int(round(sec % 60))
            return f"{m}m {s}s" if s > 0 else f"{m}m"
    except Exception:
        return ""

@app.get("/api/videos")
async def list_videos():
    vids = []
    # Collect all .mp4 files
    mp4_files = [f for f in os.listdir(OUTPUTS_DIR) if f.endswith(".mp4")]
    
    # Sort strictly by last modified time (newest first!)
    mp4_files.sort(key=lambda f: os.path.getmtime(os.path.join(OUTPUTS_DIR, f)), reverse=True)
    
    now = time.time()
    for f in mp4_files:
        fpath = os.path.join(OUTPUTS_DIR, f)
        mtime = os.path.getmtime(fpath)
        thumb_name = os.path.splitext(f)[0] + ".jpg"
        thumb_path = os.path.join(OUTPUTS_THUMBS, thumb_name)
        
        # Ensure thumbnail exists
        if not os.path.exists(thumb_path):
            subprocess.run([
                "ffmpeg", "-y", "-ss", "00:00:01", "-i", fpath,
                "-vframes", "1",
                "-vf", "scale=160:284:force_original_aspect_ratio=increase,crop=160:284",
                thumb_path
            ], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)

        # Build clean display title
        display_title = f
        if f.startswith("test_tiktok_ps23"):
            display_title = "Salmos 23"
        elif f.startswith("tiktok_"):
            parts = f.replace(".mp4", "").split("_")
            if len(parts) >= 3:
                osis = parts[1]
                ch = parts[2]
                b_info = downloader.resolve_book(osis)
                b_name = b_info["name_es"] if b_info else osis
                display_title = f"{b_name} {ch}"
        else:
            parts = f.replace(".mp4", "").split("_")
            if len(parts) >= 2:
                b_name = parts[0]
                ch = parts[1]
                b_info = downloader.resolve_book(b_name)
                b_title = b_info["name_es"] if b_info else b_name
                display_title = f"{b_title} {ch}"

        duration_label = get_video_duration_fast(fpath)

        m_struct = time.localtime(mtime)
        if time.strftime("%Y-%m-%d", m_struct) == time.strftime("%Y-%m-%d", time.localtime(now)):
            date_str = time.strftime("Hoy, %H:%M", m_struct)
        else:
            date_str = time.strftime("%d %b, %H:%M", m_struct)

        vids.append({
            "filename": f,
            "title": display_title,
            "duration": duration_label,
            "url": f"/outputs/{f}",
            "thumb_url": f"/outputs/thumbnails/{thumb_name}" if os.path.exists(thumb_path) else "",
            "size_mb": round(os.path.getsize(fpath) / (1024 * 1024), 2),
            "created_at": date_str,
            "mtime": mtime
        })
        
    return {"videos": vids}

@app.delete("/api/videos/{filename}")
async def delete_video(filename: str):
    clean_name = os.path.basename(filename)
    fpath = os.path.join(OUTPUTS_DIR, clean_name)
    thumb_name = os.path.splitext(clean_name)[0] + ".jpg"
    thumb_path = os.path.join(OUTPUTS_THUMBS, thumb_name)
    
    if not os.path.exists(fpath):
        raise HTTPException(status_code=404, detail="Video no encontrado")
        
    try:
        os.remove(fpath)
        if os.path.exists(thumb_path):
            os.remove(thumb_path)
        return {"success": True, "message": f"Video {clean_name} eliminado"}
    except Exception as e:
        logger.error(f"Error eliminando video {clean_name}: {e}")
        raise HTTPException(status_code=500, detail=str(e))

if __name__ == "__main__":
    import uvicorn
    port = int(os.environ.get("PORT", 8000))
    uvicorn.run("app:app", host="0.0.0.0", port=port, reload=True)
