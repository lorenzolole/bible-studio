import math
import os
import re
import shutil
import time
import uuid
import logging
import threading
import subprocess
from fastapi import FastAPI, UploadFile, File, Form, HTTPException
from fastapi.responses import HTMLResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel
from typing import List, Union, Optional

import downloader
import audio_engine
import subtitles
import transcripts
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

# Latest /api/transcribe request per browser tab: queued Whisper work for a clip
# the user already moved away from is skipped instead of run.
LATEST_CLIP_REQUEST = {}

# Whisper transcriptions and video renders run as background jobs the browser polls:
# a render takes minutes on Render's shared CPU, too long to hold a request open.
TRANSCRIBE_JOBS = {}
JOBS_BY_CLIP = {}
RENDER_JOBS = {}
JOBS_LOCK = threading.Lock()
JOB_TTL_SEC = 1800
FINISHED_STAGES = ("done", "error", "superseded")

# One heavy job at a time: a render and a Whisper run together would exceed 512 MB.
# It is the same re-entrant lock Whisper uses, so a render can still transcribe its own clip.
RENDER_LOCK = subtitles.WHISPER_LOCK
MAX_RENDER_SEC = 600

# Render temp files and uploads older than these are deleted before each render
# (Render's disk is small and wiped on restart anyway).
CACHE_TEMP_PREFIXES = ("img_loop_", "slideshow_", "mix_", "voice_", "sub_", "transcribe_voice_", "whisper_")
CACHE_TEMP_MAX_AGE_SEC = 6 * 3600
UPLOAD_MAX_AGE_SEC = 24 * 3600
VISUAL_UPLOAD_EXTENSIONS = (".jpg", ".jpeg", ".png", ".webp", ".mp4", ".mov")
MUSIC_UPLOAD_EXTENSIONS = (".mp3", ".wav", ".m4a", ".aac")

class TranscribeRequest(BaseModel):
    book: str
    chapter: int
    start_sec: float
    end_sec: float
    client_id: Optional[str] = None

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

@app.get("/api/health")
def health():
    """Whisper setup as seen by this container (Render logs are not always at hand)."""
    whisper_cli = subtitles.find_whisper_cli()
    help_text = ""
    if whisper_cli:
        try:
            res = subprocess.run([whisper_cli, "--help"], capture_output=True, text=True, timeout=10)
            help_text = res.stdout + res.stderr
        except Exception as e:
            help_text = str(e)
    return {
        "whisper_cli": whisper_cli,
        "model_exists": os.path.exists(subtitles.WHISPER_MODEL),
        "dtw_supported": "--dtw" in help_text and "--no-flash-attn" in help_text,
        "whisper_dtw": subtitles.WHISPER_DTW,
        "last_whisper_error": subtitles.LAST_WHISPER_ERROR,
        "chapter_whisper": transcripts.CHAPTER_WHISPER,
        "baked_transcripts": len([f for f in os.listdir(transcripts.BAKED_DIR) if f.endswith(".json")]) if os.path.isdir(transcripts.BAKED_DIR) else 0,
    }

@app.get("/api/books")
def get_books():
    return {"books": downloader.BIBLE_BOOKS, "instant_chapters": transcripts.available_chapters()}

@app.get("/api/chapter_info")
def get_chapter_info(book: str, chapter: int):
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
def get_chapter_transcription(book: str, chapter: int):
    try:
        book_info = downloader.resolve_book(book)
        if not book_info:
            raise HTTPException(status_code=400, detail="Invalid book")
        osis = book_info["osis"]

        words = transcripts.load_words(osis, chapter)
        if words is None and transcripts.CHAPTER_WHISPER:
            audio_info = downloader.download_audio_chapter(book, chapter)
            words = transcripts.transcribe_chapter(osis, chapter, audio_info["local_path"])

        if not words:
            return {"success": True, "available": False, "phrases": []}
        return {"success": True, "available": True, "phrases": subtitles.words_to_phrases(words, max_chars=90)}
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error getting chapter transcription: {e}")
        return {"success": False, "phrases": [], "error": str(e)}

def prune_finished_jobs():
    """Forget jobs that finished more than JOB_TTL_SEC ago. Call with JOBS_LOCK held."""
    now = time.time()
    for jobs in (TRANSCRIBE_JOBS, RENDER_JOBS):
        for job_id, job in list(jobs.items()):
            if job.get("finished_at") and now - job["finished_at"] > JOB_TTL_SEC:
                jobs.pop(job_id, None)
                if JOBS_BY_CLIP.get(job.get("clip")) is job:
                    JOBS_BY_CLIP.pop(job["clip"], None)

def job_view(job: dict) -> dict:
    """Progress snapshot of a transcription job. Whisper progress blends whisper-cli's own
    percentage (coarse: one step per 30s window) with elapsed time against the learned ETA."""
    stage = job["stage"]
    view = {"job_id": job["id"], "stage": stage, "done": stage in FINISHED_STAGES}
    base = {"starting": 2, "download": 5, "trim": 10, "queue": 12}
    if stage in base:
        view["progress"] = base[stage]
    elif stage == "whisper":
        elapsed = time.time() - job.get("whisper_started_at", time.time())
        expected = max(1.0, job.get("expected_sec", 1.0))
        if elapsed <= expected:
            time_fraction = 0.9 * elapsed / expected
        else:
            # Past the estimate (cold container, throttled CPU): keep creeping instead of freezing
            time_fraction = 0.9 + 0.08 * (1 - math.exp(-(elapsed - expected) / expected))
        pct = job.get("whisper_pct", 0)
        fraction = max(min(0.98, pct / 100.0), time_fraction)
        view["progress"] = round(15 + 82 * fraction)
        # whisper-cli's own percentage wins when it is ahead of the time estimate (e.g. a whole
        # chapter on Metal), so the ETA never contradicts the bar
        remaining = max(0.0, expected - elapsed)
        if pct >= 5:
            remaining = min(remaining, elapsed * (100 - pct) / pct)
        if pct >= 5 or elapsed >= 3:
            # The speed prior is tuned for server clips; give whisper-cli a moment to report first
            view["eta_sec"] = round(remaining, 1)
        view["overtime"] = elapsed > expected and pct < 95
    else:
        view["progress"] = 100
    if stage == "done":
        view.update(success=True, phrases=job.get("phrases", []), source=job.get("source"))
    elif stage == "error":
        view.update(success=False, error=job.get("error"))
    elif stage == "superseded":
        view.update(success=False, superseded=True)
    return view

def run_transcribe_job(job: dict, osis: str, req: TranscribeRequest):
    try:
        phrases, source = transcripts.get_clip_phrases(osis, req.chapter, req.start_sec, req.end_sec,
                                                       should_abort=job["should_abort"], on_progress=job.update)
        job.update(stage="superseded" if source == "superseded" else "done", phrases=phrases, source=source)
    except Exception as e:
        logger.error(f"Transcription job failed: {e}", exc_info=True)
        job.update(stage="error", error=str(e))
    finally:
        job["finished_at"] = time.time()

@app.post("/api/transcribe")
def transcribe_audio_segment(req: TranscribeRequest):
    try:
        book_info = downloader.resolve_book(req.book)
        if not book_info:
            raise HTTPException(status_code=400, detail="Invalid book")
        osis = book_info["osis"]

        # Instant answers: chapter transcript slice or a clip already transcribed this session
        words = transcripts.load_words(osis, req.chapter)
        if words:
            phrases = transcripts.clip_phrases(words, req.start_sec, req.end_sec)
            return {"success": True, "phrases": phrases, "source": "chapter", "cached": True}
        cache_key = transcripts.clip_cache_key(osis, req.chapter, req.start_sec, req.end_sec)
        if cache_key in transcripts.SESSION_CLIP_CACHE:
            return {"success": True, "phrases": transcripts.SESSION_CLIP_CACHE[cache_key], "source": "session", "cached": True}

        # Everything else runs as a background job the browser polls via /api/transcribe_status
        with JOBS_LOCK:
            prune_finished_jobs()
            job = JOBS_BY_CLIP.get(cache_key)
            if job and job["stage"] in FINISHED_STAGES and job["stage"] != "done":
                job = None  # retry clips that failed or were skipped
            if job is None:
                token = object()
                job = {"id": uuid.uuid4().hex, "clip": cache_key, "stage": "starting", "token": token}
                # Skip the queued Whisper run if this tab asks for another clip before it starts
                client_id = req.client_id
                job["should_abort"] = (lambda: LATEST_CLIP_REQUEST.get(client_id) is not token) if client_id else None
                TRANSCRIBE_JOBS[job["id"]] = job
                JOBS_BY_CLIP[cache_key] = job
                threading.Thread(target=run_transcribe_job, args=(job, osis, req), daemon=True).start()
            if req.client_id:
                LATEST_CLIP_REQUEST[req.client_id] = job["token"]

        view = job_view(job)
        if view["done"] and view.get("success"):
            return {"success": True, "phrases": view["phrases"], "source": view["source"], "cached": True}
        return {"success": True, "pending": True, **view}
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Transcription failed: {e}")
        raise HTTPException(status_code=500, detail=str(e))

@app.get("/api/transcribe_status")
def transcribe_status(job_id: str):
    job = TRANSCRIBE_JOBS.get(job_id)
    if not job:
        raise HTTPException(status_code=404, detail="Transcripción no encontrada")
    return job_view(job)

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

def safe_upload_name(prefix: str, original: Optional[str], allowed_extensions: tuple) -> str:
    """Filesystem-safe upload name, rejecting file types the renderer can't use."""
    base = re.sub(r"[^\w.\-]", "_", os.path.basename(original or "archivo"))[-80:]
    if not base.lower().endswith(allowed_extensions):
        raise HTTPException(status_code=400, detail=f"Formato no soportado. Usá: {', '.join(allowed_extensions)}")
    return f"{prefix}_{int(time.time())}_{base}"

@app.post("/api/upload_visual")
def upload_visual(file: UploadFile = File(...)):
    filename = safe_upload_name("upload", file.filename, VISUAL_UPLOAD_EXTENSIONS)
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
def upload_music(file: UploadFile = File(...)):
    filename = safe_upload_name("upload_music", file.filename, MUSIC_UPLOAD_EXTENSIONS)
    save_path = os.path.join(UPLOADS_DIR, filename)
    with open(save_path, "wb") as buffer:
        shutil.copyfileobj(file.file, buffer)

    return {
        "success": True,
        "path": save_path,
        "url": f"/cache/uploads/{filename}",
        "name": file.filename
    }

def resolve_media_path(path: str, label: str) -> str:
    """Absolute path of a visual or music file, limited to the bundled assets and user uploads."""
    full = os.path.realpath(path if os.path.isabs(path) else os.path.join(BASE_DIR, path))
    for root in (ASSETS_DIR, UPLOADS_DIR):
        if full.startswith(os.path.realpath(root) + os.sep) and os.path.isfile(full):
            return full
    raise HTTPException(status_code=400, detail=f"{label} no disponible: {os.path.basename(path)}. Volvé a elegirlo o subirlo.")

def clean_phrases(phrases: Optional[List[dict]]) -> list[dict]:
    """Phrases sent by the browser, keeping only well-formed entries."""
    cleaned = []
    for p in phrases or []:
        try:
            start, end = float(p["start"]), float(p["end"])
        except (KeyError, TypeError, ValueError):
            continue
        text = str(p.get("text", "")).strip()
        if text and end > start:
            cleaned.append({"start": start, "end": end, "text": text})
    return cleaned

def prune_cache():
    """Delete stale render/transcription temp files and old uploads."""
    now = time.time()
    targets = ((CACHE_DIR, CACHE_TEMP_PREFIXES, CACHE_TEMP_MAX_AGE_SEC),
               (UPLOADS_DIR, ("upload_",), UPLOAD_MAX_AGE_SEC))
    for directory, prefixes, max_age in targets:
        for name in os.listdir(directory):
            path = os.path.join(directory, name)
            try:
                if name.startswith(prefixes) and os.path.isfile(path) and now - os.path.getmtime(path) > max_age:
                    os.remove(path)
            except OSError:
                pass

def render_job_view(job: dict) -> dict:
    """Progress snapshot of a render job; FFmpeg stages report real frame-based percentages."""
    stage = job["stage"]
    view = {"job_id": job["id"], "stage": stage, "done": stage in FINISHED_STAGES}
    bands = {"queue": (0, 0), "subtitles": (3, 3), "audio": (6, 6), "visual": (10, 35), "encode": (35, 97), "thumbnail": (98, 98)}
    if stage in bands:
        low, high = bands[stage]
        percent = job.get("percent", 0)
        view["progress"] = round(low + (high - low) * percent / 100)
        if stage == "encode" and percent >= 3:
            elapsed = time.time() - job.get("stage_started_at", time.time())
            view["eta_sec"] = round(elapsed * (100 - percent) / percent)
    else:
        view["progress"] = 100
    if stage == "done":
        view.update(success=True, **job["result"])
    elif stage == "error":
        view.update(success=False, error=job.get("error"))
    return view

def run_render_job(job: dict, book_info: dict, req: RenderRequest, visual, music: Optional[str]):
    temp_files = []

    def on_progress(update: dict):
        if update.get("stage") and update["stage"] != job["stage"]:
            job["stage_started_at"] = time.time()
            job["percent"] = 0
        job.update(update)

    try:
        with RENDER_LOCK:
            prune_cache()
            on_progress({"stage": "subtitles"})
            result = render_clip(book_info, req, visual, music, on_progress, temp_files)
        job.update(stage="done", result=result)
    except Exception as e:
        logger.error(f"Render failed: {e}", exc_info=True)
        job.update(stage="error", error=str(e))
    finally:
        for path in temp_files:
            if path and os.path.exists(path):
                os.remove(path)
        job["finished_at"] = time.time()

@app.post("/api/render")
def render_video(req: RenderRequest):
    """Validate the request and start a background render; poll /api/render_status for progress."""
    book_info = downloader.resolve_book(req.book)
    if not book_info:
        raise HTTPException(status_code=400, detail="Libro inválido")
    clip_duration = req.end_sec - req.start_sec
    if req.start_sec < 0 or clip_duration < 1.0:
        raise HTTPException(status_code=400, detail="El fragmento tiene que durar al menos 1 segundo")
    if clip_duration > MAX_RENDER_SEC:
        raise HTTPException(status_code=400, detail=f"El fragmento no puede superar {MAX_RENDER_SEC // 60} minutos")
    paths = req.visual_paths if isinstance(req.visual_paths, list) else [req.visual_paths]
    if not paths or not all(paths):
        raise HTTPException(status_code=400, detail="Elegí un fondo visual o una colección")
    visuals = [resolve_media_path(p, "Fondo visual") for p in paths]
    music = resolve_media_path(req.music_path, "Música") if req.music_path else None

    job = {"id": uuid.uuid4().hex, "stage": "queue"}
    with JOBS_LOCK:
        prune_finished_jobs()
        RENDER_JOBS[job["id"]] = job
    visual = visuals if isinstance(req.visual_paths, list) else visuals[0]
    threading.Thread(target=run_render_job, args=(job, book_info, req, visual, music), daemon=True).start()
    return {"success": True, "pending": True, **render_job_view(job)}

@app.get("/api/render_status")
def render_status(job_id: str):
    job = RENDER_JOBS.get(job_id)
    if not job:
        raise HTTPException(status_code=404, detail="Render no encontrado: el servidor se reinició. Probá de nuevo.")
    return render_job_view(job)

def render_clip(book_info: dict, req: RenderRequest, visual, music: Optional[str], on_progress, temp_files: list) -> dict:
    """Trim the narration, build subtitles and render the video. Returns the library entry."""
    osis = book_info["osis"]
    book_name_clean = book_info["name_es"].replace(" ", "_").replace("á","a").replace("é","e").replace("í","i").replace("ó","o").replace("ú","u")
    audio_info = downloader.download_audio_chapter(osis, req.chapter)

    stamp = uuid.uuid4().hex[:8]
    clip_duration = req.end_sec - req.start_sec
    trimmed_voice = os.path.join(CACHE_DIR, f"voice_{osis}_{req.chapter}_{stamp}.mp3")
    temp_files.append(trimmed_voice)
    audio_engine.trim_speech_audio(
        audio_info["local_path"],
        trimmed_voice,
        start_sec=req.start_sec,
        end_sec=req.end_sec,
        enhance_voice=True
    )

    english_citation = downloader.normalize_citation_english(req.citation)

    ass_path = None
    timed_phrases = None
    if req.enable_subtitles and req.subtitle_style != "none":
        timed_phrases = clean_phrases(req.phrases)
        if not timed_phrases and req.custom_text:
            timed_phrases = subtitles.generate_timed_subtitles(req.custom_text, clip_duration)
        elif not timed_phrases:
            timed_phrases, _ = transcripts.get_clip_phrases(osis, req.chapter, req.start_sec, req.end_sec)

        ass_path = os.path.join(CACHE_DIR, f"sub_{osis}_{req.chapter}_{stamp}.ass")
        temp_files.append(ass_path)
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
        ass_path = os.path.join(CACHE_DIR, f"sub_cit_{osis}_{req.chapter}_{stamp}.ass")
        temp_files.append(ass_path)
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

    # Human-readable filename
    out_filename = f"{book_name_clean}_{req.chapter}_{int(clip_duration)}s_{time.strftime('%H%M%S')}.mp4"
    out_path = os.path.join(OUTPUTS_DIR, out_filename)

    video_engine.render_tiktok_video(
        voice_audio=trimmed_voice,
        visual_path=visual,
        music_audio=music,
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
        enable_film_grain=req.enable_film_grain,
        on_progress=on_progress
    )

    # Generate thumbnail for library
    on_progress({"stage": "thumbnail"})
    thumb_filename = os.path.splitext(out_filename)[0] + ".jpg"
    thumb_path = os.path.join(OUTPUTS_THUMBS, thumb_filename)
    subprocess.run([
        "ffmpeg", "-y", "-ss", f"{min(2.0, clip_duration / 2):.1f}", "-i", out_path,
        "-vframes", "1",
        "-vf", "scale=160:284:force_original_aspect_ratio=increase,crop=160:284",
        thumb_path
    ], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)

    return {
        "filename": out_filename,
        "video_url": f"/outputs/{out_filename}",
        "thumb_url": f"/outputs/thumbnails/{thumb_filename}",
        "duration": clip_duration,
        "title": f"{book_info['name_es']} {req.chapter}"
    }

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
def list_videos():
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
