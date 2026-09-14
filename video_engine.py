import hashlib
import os
import statistics
import subprocess
import json
import logging
import math
import tempfile
import threading
import uuid
from concurrent.futures import ThreadPoolExecutor, as_completed
from PIL import Image, ImageDraw
import audio_engine
import beats
import figures
import generate_overlays

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger("video_engine")

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
OUTPUTS_DIR = os.path.join(BASE_DIR, "outputs")
CACHE_DIR = os.path.join(BASE_DIR, "cache")
ASSETS_DIR = os.path.join(BASE_DIR, "assets")
OVERLAYS_DIR = os.path.join(ASSETS_DIR, "overlays")

os.makedirs(OUTPUTS_DIR, exist_ok=True)
os.makedirs(CACHE_DIR, exist_ok=True)
os.makedirs(OVERLAYS_DIR, exist_ok=True)

FPS = 30
FFMPEG_THREADS = os.environ.get("FFMPEG_THREADS", "2")
FFMPEG_PRESET = os.environ.get("FFMPEG_PRESET", "veryfast")

# FFmpeg sizes decoder, filter and encoder thread pools by the host's core count, and each
# thread holds 1080x1920 frame buffers: ~1 GB peak, an OOM kill in a 512 MB container.
# Every FFmpeg call caps filters here, decoders with "-threads 1" per input and the encoder
# with FFMPEG_THREADS.
THREAD_CAPS = ["-filter_threads", "1", "-filter_complex_threads", "1"]

IMAGE_EXTENSIONS = (".jpg", ".jpeg", ".png", ".webp")
PREVIEW_SIZE = (540, 960)
# Full width so the face sits mid-frame and bottom subtitles land on the robe, not the face
FIGURE_WIDTH = 1080
# Target seconds between cuts in a beat montage; cuts snap to every k-th beat near this pace
MONTAGE_RHYTHMS = {"fast": 0.45, "medium": 0.9, "slow": 1.8}
# Montage segments rendered in parallel (each FFmpeg ~90 MB; Docker sets 1 to stay within 512 MB)
MONTAGE_WORKERS = max(1, int(os.environ.get("MONTAGE_WORKERS", "3")))

# Cancellation for superseded previews: the render thread sets a check that _run_ffmpeg polls
_abort = threading.local()

class RenderCancelled(Exception):
    """A newer request replaced this render, so FFmpeg was stopped."""

def _filter_path(path: str) -> str:
    """Quote a file path for use as a filter option inside -filter_complex."""
    return "'" + path.replace("\\", "/").replace(":", "\\:") + "'"

def _run_ffmpeg(args: list[str], total_frames: int = 0, on_progress=None, stage: str = "encode"):
    """Run `ffmpeg <args>`, reporting {"stage", "percent"} parsed from -progress output.
    Raises RuntimeError (with the stderr tail logged) on failure."""
    cmd = ["ffmpeg", "-nostats", "-progress", "pipe:1"] + args
    with tempfile.TemporaryFile(mode="w+", encoding="utf-8", errors="replace") as err:
        proc = subprocess.Popen(cmd, stdout=subprocess.PIPE, stderr=err, text=True)
        last_percent = -1
        should_abort = getattr(_abort, "check", None)
        for line in proc.stdout:
            # -progress writes a block every 0.5s, so a superseded render stops within a second
            if should_abort and should_abort():
                proc.kill()
                proc.wait()
                raise RenderCancelled()
            if not (on_progress and total_frames and line.startswith("frame=")):
                continue
            try:
                percent = min(99, int(100 * int(line.split("=", 1)[1]) / total_frames))
            except ValueError:
                continue
            if percent != last_percent:
                on_progress({"stage": stage, "percent": percent})
                last_percent = percent
        code = proc.wait()
        if code != 0:
            err.seek(0)
            logger.error(f"FFmpeg failed ({code}) during {stage}: {err.read()[-1500:]}")
            reason = "killed, likely out of memory" if code in (-9, 137) else f"exit code {code}"
            raise RuntimeError(f"FFmpeg failed during {stage} ({reason})")

def get_media_dimensions(file_path: str) -> tuple[int, int]:
    """Get width and height of an image or video file using ffprobe."""
    cmd = [
        "ffprobe", "-v", "error",
        "-select_streams", "v:0",
        "-show_entries", "stream=width,height",
        "-of", "json",
        file_path
    ]
    res = subprocess.run(cmd, capture_output=True, text=True, check=True)
    data = json.loads(res.stdout)
    streams = data.get("streams", [])
    if not streams:
        raise ValueError(f"No video stream found in {file_path}")
    return int(streams[0]["width"]), int(streams[0]["height"])

def generate_rounded_mask(width: int, height: int, radius: int = 42) -> str:
    """Create an antialiased grayscale PNG rounded rectangle mask."""
    mask_file = os.path.join(CACHE_DIR, f"mask_{width}x{height}_r{radius}.png")
    if os.path.exists(mask_file):
        return mask_file

    scale = 2
    sw, sh, sr = width * scale, height * scale, radius * scale

    img = Image.new("L", (sw, sh), 0)
    draw = ImageDraw.Draw(img)
    draw.rounded_rectangle([(0, 0), (sw - 1, sh - 1)], radius=sr, fill=255)

    img = img.resize((width, height), Image.Resampling.LANCZOS)
    img.save(mask_file)
    return mask_file

def calculate_foreground_size(orig_w: int, orig_h: int) -> tuple[int, int]:
    """Calculate optimal foreground box size centered in a 1080x1920 frame."""
    aspect = orig_w / float(orig_h)

    if aspect >= 1.2:
        target_w = 920
        target_h = int(target_w / aspect)
        target_h = target_h if target_h % 2 == 0 else target_h + 1
    elif aspect <= 0.8:
        target_w = 860
        target_h = int(target_w / aspect)
        max_h = 1250
        if target_h > max_h:
            target_h = max_h
            target_w = int(target_h * aspect)
        target_w = target_w if target_w % 2 == 0 else target_w + 1
        target_h = target_h if target_h % 2 == 0 else target_h + 1
    else:
        target_w = 880
        target_h = 880

    return target_w, target_h

def build_camera_motion_expression(
    total_frames: int,
    fps: int = 30,
    whisper_phrases: list[dict] = None,
    enable_dynamic_motion: bool = True
) -> tuple[str, str, str]:
    """
    Construct ultra-smooth, dignified continuous Ken Burns motion with ZERO jitter.
    Maintains exact optical center alignment (eliminates jerky shaking and pixel stutter).
    """
    if not enable_dynamic_motion:
        # Static serene frame
        zoom_expr = "1.0"
        x_expr = "iw/2-(iw/zoom/2)"
        y_expr = "ih/2-(ih/zoom/2)"
        return zoom_expr, x_expr, y_expr

    # Ultra-smooth continuous slow push-in (+4.5% total expansion over duration)
    # Guaranteed continuous progression without sudden jumps, oscillations or shakes
    zoom_expr = f"1.0 + 0.045*(on/{max(1, total_frames)})"
    x_expr = "iw/2-(iw/zoom/2)"
    y_expr = "ih/2-(ih/zoom/2)"

    return zoom_expr, x_expr, y_expr

def prepare_visual_input(
    visual_path: str,
    temp_dir: str = CACHE_DIR,
    duration: float = 10.0,
    framing: str = "pitch_black",
    whisper_phrases: list[dict] = None,
    enable_dynamic_motion: bool = True,
    on_progress=None
) -> tuple[str, bool]:
    """Ensure visual is in video format with organic camera motion and Whisper-reactive zoom."""
    ext = os.path.splitext(visual_path)[1].lower()
    if ext in [".jpg", ".jpeg", ".png", ".webp"]:
        cache_signature = f"v2_{visual_path}_{framing}_{round(duration, 1)}_{enable_dynamic_motion}_{len(whisper_phrases or [])}"
        loop_out = os.path.join(temp_dir, f"img_loop_{abs(hash(cache_signature)) % 1000000}.mp4")

        if not os.path.exists(loop_out):
            logger.info(f"Preparing cinematic visual {visual_path} (framing={framing}, motion={enable_dynamic_motion})...")
            w, h = get_media_dimensions(visual_path)
            num_frames = int(duration * FPS) + FPS

            zoom_expr, x_expr, y_expr = build_camera_motion_expression(
                total_frames=num_frames,
                fps=FPS,
                whisper_phrases=whisper_phrases,
                enable_dynamic_motion=enable_dynamic_motion
            )

            if framing == "fullscreen":
                vf_expr = (
                    "scale=1080:1920:force_original_aspect_ratio=increase,crop=1080:1920,"
                    f"zoompan=z='{zoom_expr}':x='{x_expr}':y='{y_expr}':d={num_frames}:s=1080x1920:fps=30,"
                    "eq=contrast=1.05:brightness=-0.02"
                )
            else:
                # Zoom straight to the composited size, from a source capped at 2x that size: enough
                # oversampling for a jitter-free push-in without decoding 24 MP frames (sunset_mountains.jpg)
                fg_w, fg_h = calculate_foreground_size(w, h)
                src_w, src_h = (2 * fg_w, 2 * fg_h) if w > 2 * fg_w else (w, h)
                vf_expr = (
                    f"scale={src_w}:{src_h},"
                    f"zoompan=z='{zoom_expr}':x='{x_expr}':y='{y_expr}':d={num_frames}:s={fg_w}x{fg_h}:fps=30,"
                    "eq=contrast=1.05:brightness=-0.01"
                )

            # Write to a temp name so a failed or killed encode never leaves a broken cached loop
            # A single decoded frame is enough: zoompan emits d frames per input frame
            partial_out = f"{loop_out}.part.mp4"
            _run_ffmpeg(
                ["-y"] + THREAD_CAPS + ["-threads", "1", "-i", visual_path,
                 "-vf", vf_expr, "-t", f"{duration:.2f}",
                 "-c:v", "libx264", "-preset", "fast", "-threads", FFMPEG_THREADS,
                 "-pix_fmt", "yuv420p", partial_out],
                total_frames=int(duration * FPS), on_progress=on_progress, stage="visual")
            os.replace(partial_out, loop_out)
        return loop_out, True
    else:
        return visual_path, False

def build_slideshow_video(
    image_paths: list[str],
    target_duration: float,
    output_path: str,
    pacing: str = "cinematic",
    framing: str = "pitch_black",
    whisper_phrases: list[dict] = None,
    enable_dynamic_motion: bool = True,
    on_progress=None
) -> str:
    """
    Build a slideshow video with organic crossfades and dignified Ken Burns motions.
    NO jarring transitions (only soft dissolve/fade).
    """
    if len(image_paths) == 1:
        v, _ = prepare_visual_input(
            image_paths[0],
            duration=target_duration,
            framing=framing,
            whisper_phrases=whisper_phrases,
            enable_dynamic_motion=enable_dynamic_motion,
            on_progress=on_progress
        )
        return v

    fade_time = 0.8 if pacing == "cinematic" else 0.5
    target_slide_dur = 4.5 if pacing == "cinematic" else 2.6

    needed_count = max(len(image_paths), int(round(target_duration / target_slide_dur)))

    expanded_paths = []
    while len(expanded_paths) < needed_count:
        expanded_paths.extend(image_paths)
    expanded_paths = expanded_paths[:needed_count]

    n = len(expanded_paths)
    slide_dur = (target_duration + (n - 1) * fade_time) / n
    slide_dur = max(fade_time + 0.8, slide_dur)

    num_frames = int(slide_dur * 30) + 30
    target_w, target_h = (1080, 1920) if framing == "fullscreen" else (1080, 1350)

    inputs = []
    filter_chains = []

    for i, p in enumerate(expanded_paths):
        # One frame per image: zoompan emits num_frames frames per input frame
        inputs.extend(["-threads", "1", "-i", p])
        pattern = i % 2
        if pattern == 0:
            zoom_expr = f"1.0 + 0.04*on/{num_frames}"
        else:
            zoom_expr = f"1.04 - 0.04*on/{num_frames}"

        x_expr = "iw/2-(iw/zoom/2)"
        y_expr = "ih/2-(ih/zoom/2)"

        filter_chains.append(
            f"[{i}:v]scale={target_w}:{target_h}:force_original_aspect_ratio=increase,crop={target_w}:{target_h},"
            f"zoompan=z='{zoom_expr}':x='{x_expr}':y='{y_expr}':d={num_frames}:s={target_w}x{target_h}:fps=30,"
            f"eq=contrast=1.05:brightness=-0.01[v{i}];"
        )

    last_label = "[v0]"
    current_offset = slide_dur - fade_time
    for i in range(1, n):
        out_label = f"[xf{i}]" if i < n - 1 else "[vfinal]"
        filter_chains.append(
            f"{last_label}[v{i}]xfade=transition=dissolve:duration={fade_time:.2f}:offset={current_offset:.2f}{out_label};"
        )
        last_label = out_label
        current_offset += (slide_dur - fade_time)

    filter_complex = "".join(filter_chains).rstrip(";")

    args = ["-y"] + THREAD_CAPS + inputs + [
        "-filter_complex", filter_complex,
        "-map", "[vfinal]",
        "-t", f"{target_duration:.2f}",
        "-c:v", "libx264",
        "-preset", FFMPEG_PRESET,
        "-threads", FFMPEG_THREADS,
        "-pix_fmt", "yuv420p",
        output_path
    ]
    logger.info(f"Rendering dignified {pacing} slideshow ({n} cuts, {target_duration:.1f}s, {fade_time:.2f}s crossfade)...")
    _run_ffmpeg(args, total_frames=int(target_duration * FPS), on_progress=on_progress, stage="visual")
    return output_path

# --- Beat montage: the TikTok "Jesus edit" ---------------------------------------------------

def montage_cut_times(duration: float, music_path: str | None, rhythm: str = "fast") -> tuple[list[float], list[bool], float]:
    """
    Segment start times for a beat montage (always starting at 0), which of them open with a
    white flash, and the detected BPM. Cuts land on every k-th music beat so the pace matches
    the rhythm; without music a steady grid is used.
    """
    target = MONTAGE_RHYTHMS.get(rhythm, MONTAGE_RHYTHMS["fast"])
    grid, bpm = [], 0.0
    if music_path and os.path.exists(music_path):
        # Fixed analysis window so every clip of a track shares one tempo estimate (and cache entry)
        info = beats.detect_beats(music_path, max_sec=max(180.0, duration + 5))
        bpm = info["bpm"]
        beat_times = [b for b in info["beats"] if b < duration + 1]
        if len(beat_times) >= 3:
            ibi = statistics.median(b - a for a, b in zip(beat_times, beat_times[1:]))
            if ibi > target * 1.5:
                # Half-time tempo estimate (or a slow song): split each beat to reach the pace
                parts = int(ibi / target + 0.5)
                beat_times = [b + j * ibi / parts for b in beat_times for j in range(parts)]
            else:
                # int(x + 0.5): Python's round() sends 1.5 to 1 and medium would equal fast
                beat_times = beat_times[::max(1, int(target / ibi + 0.5))]
            grid = [b for b in beat_times if 0 < b < duration]
    if not grid:
        grid = [target * i for i in range(1, int(duration / target) + 1)]
    starts = [0.0]
    for t in grid:
        if t - starts[-1] >= 0.25 and duration - t >= 0.25:
            starts.append(round(t, 3))
    flash_every = {"fast": 4, "medium": 2, "slow": 1}.get(rhythm, 4)
    flashes = [i % flash_every == 0 for i in range(len(starts))]
    return starts, flashes, bpm

def _montage_segment(image_path: str, frames: int, flash: bool, dim: bool) -> str:
    """One cut of the montage: the artwork fills the frame and settles from a 12% punch-in (cached)."""
    signature = f"seg_v1|{os.path.abspath(image_path)}|{os.path.getmtime(image_path)}|{frames}|{flash}|{dim}"
    out = os.path.join(CACHE_DIR, f"montage_seg_{hashlib.sha1(signature.encode()).hexdigest()[:16]}.mp4")
    if os.path.exists(out):
        return out
    zoom = f"1+0.12*pow(1-on/{frames},3)"
    # Behind a figure the art is darker and slightly soft so the figure reads first
    if dim:
        tone = "eq=brightness=-0.14:saturation=0.8:contrast=1.08,boxblur=2:1"
    else:
        tone = "eq=brightness=-0.03:saturation=0.95:contrast=1.08"
    vf = (f"scale=1188:2112:force_original_aspect_ratio=increase,crop=1188:2112,"
          f"zoompan=z='{zoom}':x='iw/2-(iw/zoom/2)':y='ih/2-(ih/zoom/2)':d={frames}:s=1080x1920:fps={FPS},{tone}")
    if flash:
        vf += ",fade=t=in:st=0:d=0.14:color=white"
    # Unique temp name: identical cuts can render at the same time in parallel workers
    partial = f"{out}.{uuid.uuid4().hex[:8]}.part.mp4"
    _run_ffmpeg(["-y"] + THREAD_CAPS + ["-threads", "1", "-i", image_path, "-vf", vf, "-frames:v", str(frames),
                 "-c:v", "libx264", "-preset", "ultrafast", "-crf", "18", "-threads", FFMPEG_THREADS,
                 "-pix_fmt", "yuv420p", partial], stage="visual")
    os.replace(partial, out)
    return out

def build_beat_montage(
    image_paths: list[str],
    duration: float,
    music_path: str | None,
    output_path: str,
    rhythm: str = "fast",
    enable_flash: bool = True,
    dim_background: bool = False,
    on_progress=None
) -> str:
    """Hard cuts between artworks on the music's beats, each with a punch-in. Segments are
    rendered one by one (tiny, cached) and joined without re-encoding."""
    starts, flashes, bpm = montage_cut_times(duration, music_path, rhythm)
    ends = starts[1:] + [duration]
    jobs = []
    for i, (start, end) in enumerate(zip(starts, ends)):
        frames = max(1, round(end * FPS) - round(start * FPS))
        jobs.append((image_paths[i % len(image_paths)], frames, enable_flash and flashes[i], dim_background))

    abort_check = getattr(_abort, "check", None)

    def render_segment(job):
        _abort.check = abort_check  # the cancellation check is thread-local: carry it into the worker
        return _montage_segment(*job)

    segments = [None] * len(jobs)
    with ThreadPoolExecutor(max_workers=MONTAGE_WORKERS) as pool:
        futures = {pool.submit(render_segment, job): index for index, job in enumerate(jobs)}
        for done, future in enumerate(as_completed(futures), 1):
            segments[futures[future]] = future.result()
            if on_progress:
                on_progress({"stage": "visual", "percent": min(99, int(100 * done / len(jobs)))})
    list_path = f"{output_path}.txt"
    with open(list_path, "w", encoding="utf-8") as f:
        f.writelines(f"file '{segment}'\n" for segment in segments)
    try:
        _run_ffmpeg(["-y", "-f", "concat", "-safe", "0", "-i", list_path, "-c", "copy", output_path], stage="visual")
    finally:
        os.remove(list_path)
    logger.info(f"Beat montage: {len(segments)} cuts at {bpm:.0f} BPM ({rhythm}) over {duration:.1f}s")
    return output_path

def render_tiktok_video(*args, should_abort=None, **kwargs) -> str:
    """Render a video (see _render_tiktok_video). should_abort() is polled while FFmpeg runs;
    when it returns True the render stops with RenderCancelled."""
    _abort.check = should_abort
    try:
        return _render_tiktok_video(*args, **kwargs)
    finally:
        _abort.check = None

def _render_tiktok_video(
    voice_audio: str,
    visual_path: str | list[str],
    output_path: str,
    music_audio: str = None,
    subtitle_ass: str = None,
    music_volume: float = 0.16,
    corner_radius: int = 42,
    y_offset: int = -110,
    slideshow_pacing: str = "cinematic",
    framing_mode: str = "pitch_black",
    whisper_phrases: list[dict] = None,
    enable_particles: bool = True,
    enable_light_leak: bool = True,
    enable_dynamic_motion: bool = True,
    enable_film_grain: bool = True,
    edit_template: str = "classic",
    figure_path: str = None,
    cut_rhythm: str = "fast",
    enable_flash: bool = True,
    frame_style: str = "vintage",
    preview: bool = False,
    on_progress=None
) -> str:
    """
    Render a complete 1080x1920 vertical TikTok video with cinematic atmosphere layers.
    framing_mode options:
      - 'pitch_black' (Default): Pure #000000 background with centered high-contrast textured artwork (Ref @nehzro)
      - 'fullscreen': 9:16 vertical full-bleed artwork with subtle top/bottom contrast shade (Ref @nanagoes5)
      - 'ambient': Darkened, desaturated ambient background with soft shadows
    Cinematic FX:
      - enable_particles: Ethereal celestial dust motes loop with alpha overlay
      - enable_light_leak: Warm anamorphic amber/gold flare entry in first 2 seconds (TikTok hook)
      - enable_dynamic_motion: Organic camera breathing & Whisper-synchronized micro-zooms
      - enable_film_grain: 35mm film emulsion grain texture
    """
    os.makedirs(os.path.dirname(os.path.abspath(output_path)), exist_ok=True)

    duration = audio_engine.get_audio_duration(voice_audio)
    logger.info(f"Target video duration: {duration:.2f}s (framing={framing_mode})")

    # 0. Ensure cinematic overlay assets exist
    particles_path = os.path.join(OVERLAYS_DIR, "particles_celestial.mkv")
    light_leak_path = os.path.join(OVERLAYS_DIR, "light_leak_warm.mkv")
    if enable_particles and not os.path.exists(particles_path):
        generate_overlays.generate_celestial_particles(particles_path)
    if enable_light_leak and not os.path.exists(light_leak_path):
        generate_overlays.generate_warm_light_leak(light_leak_path)

    # 1. Audio Mix (voice + optional music with ducking)
    if on_progress:
        on_progress({"stage": "audio"})
    if music_audio and os.path.exists(music_audio):
        mixed_audio = os.path.join(CACHE_DIR, f"mix_{abs(hash(voice_audio + music_audio)) % 1000000}.mp3")
        audio_engine.mix_voice_and_music(
            voice_file=voice_audio,
            music_file=music_audio,
            output_file=mixed_audio,
            music_volume=music_volume,
            fade_in=1.0,
            fade_out=1.8
        )
        final_audio = mixed_audio
    else:
        final_audio = voice_audio

    # 2. Prepare Visual Base
    montage_file = None
    montage_images = [p for p in (visual_path if isinstance(visual_path, list) else [visual_path])
                      if os.path.splitext(p)[1].lower() in IMAGE_EXTENSIONS]
    if edit_template == "beat_montage" and montage_images:
        # Fast cuts on the music's beats (behind the figure, if any); always full-bleed
        montage_file = os.path.join(CACHE_DIR, f"montage_{os.getpid()}_{threading.get_ident()}.mp4")
        video_input = build_beat_montage(
            montage_images,
            duration,
            music_audio,
            montage_file,
            rhythm=cut_rhythm,
            enable_flash=enable_flash,
            dim_background=bool(figure_path),
            on_progress=on_progress
        )
        framing_mode = "fullscreen"
    elif isinstance(visual_path, list) and len(visual_path) > 1:
        cache_key = f"{''.join(visual_path)}_{round(duration, 1)}_{slideshow_pacing}_{framing_mode}_{enable_dynamic_motion}"
        slideshow_file = os.path.join(CACHE_DIR, f"slideshow_{abs(hash(cache_key)) % 1000000}.mp4")
        video_input = build_slideshow_video(
            visual_path,
            duration,
            slideshow_file,
            pacing=slideshow_pacing,
            framing=framing_mode,
            whisper_phrases=whisper_phrases,
            enable_dynamic_motion=enable_dynamic_motion,
            on_progress=on_progress
        )
    else:
        video_input, _ = prepare_visual_input(
            visual_path[0] if isinstance(visual_path, list) else visual_path,
            duration=duration,
            framing=framing_mode,
            whisper_phrases=whisper_phrases,
            enable_dynamic_motion=enable_dynamic_motion,
            on_progress=on_progress
        )

    # Canvas: the phone preview composes directly at 540x960 (4x fewer pixels to filter and
    # encode); every pixel measure below is scaled from the 1080x1920 layout
    canvas_w, canvas_h = PREVIEW_SIZE if preview else (1080, 1920)
    scale = canvas_w / 1080

    def even(value: float) -> int:
        return max(2, int(round(value * scale / 2)) * 2)

    y_offset = int(round(y_offset * scale))
    orig_w, orig_h = get_media_dimensions(video_input)
    fg_w, fg_h = calculate_foreground_size(orig_w, orig_h)
    fg_w, fg_h = even(fg_w), even(fg_h)
    radius = max(2, int(round(corner_radius * scale)))
    mask_path = generate_rounded_mask(fg_w, fg_h, radius=radius)

    # 3. Sources. Video comes from movie= filters inside the graph, which decode on demand;
    # -i inputs are decoded eagerly and their 1080x1920 frames pile up waiting for the slower
    # main chain (measured peak: 788 MB with -i inputs, 409 MB with movie= sources).
    use_particles = enable_particles and os.path.exists(particles_path)
    use_leak = enable_light_leak and os.path.exists(light_leak_path)
    sources = [f"movie={_filter_path(video_input)}:loop=0,setpts=N/(FRAME_RATE*TB)[visual_src];"]
    if framing_mode != "fullscreen":
        sources.append(f"movie={_filter_path(mask_path)},loop=loop=-1:size=1,setpts=N/({FPS}*TB)[mask_src];")
    if use_particles:
        sources.append(f"movie={_filter_path(particles_path)}:loop=0,setpts=N/(FRAME_RATE*TB)[particles_src];")
    if use_leak:
        sources.append(f"movie={_filter_path(light_leak_path)},setpts=N/(FRAME_RATE*TB)[leak_src];")

    inputs = ["-threads", "1", "-i", final_audio]
    audio_idx = 0

    # 4. Filtergraph Assembly
    # Every source runs at FPS: color= and looped images default to 25 fps, and an overlay fed
    # at mismatched rates queues unconsumed 1080x1920 frames (hundreds of MB over a clip).
    filter_parts = []

    if framing_mode == "fullscreen":
        # Full-bleed 9:16 art with a soft top/bottom gradient for text contrast
        sources.append(f"movie={_filter_path(figures.fullscreen_vignette(canvas_w, canvas_h))},loop=loop=-1:size=1,setpts=N/({FPS}*TB)[vignette_src];")
        filter_parts.append(
            f"[visual_src]fps={FPS},scale={canvas_w}:{canvas_h}:force_original_aspect_ratio=increase,crop={canvas_w}:{canvas_h},eq=contrast=1.04:brightness=-0.02[art];"
            "[art][vignette_src]overlay=0:0:format=auto[comp_base];"
        )
    elif framing_mode == "ambient":
        # Deeply darkened and desaturated ambient background
        filter_parts.append(
            f"[visual_src]fps={FPS},split=2[src_bg][src_fg];"
            f"[src_bg]scale={canvas_w}:{canvas_h}:force_original_aspect_ratio=increase,crop={canvas_w}:{canvas_h},boxblur={max(2, int(26 * scale))}:5,eq=brightness=-0.65:contrast=1.1:saturation=0.5[bg];"
            f"[src_fg]scale={fg_w}:{fg_h},eq=contrast=1.06:brightness=-0.01,format=yuva420p[fg];"
        )
    else:
        # Default: Pure Pitch Black #000000 (Minimalist Viral Ref @nehzro)
        filter_parts.append(
            f"color=c=black:s={canvas_w}x{canvas_h}:r={FPS}:d={duration:.2f}[bg];"
            f"[visual_src]fps={FPS},scale={fg_w}:{fg_h},eq=contrast=1.06:brightness=-0.01,format=yuva420p[fg];"
        )

    if framing_mode != "fullscreen":
        # Rounded artwork over the background, with its frame finish: glow under it, gold ring over it
        center = f"(W-w)/2:(H-h)/2{'+' if y_offset >= 0 else ''}{y_offset}"
        decoration = figures.frame_decoration(fg_w, fg_h, radius, frame_style, scale=scale)
        base = "[bg]"
        if decoration:
            sources.append(f"movie={_filter_path(decoration)},loop=loop=-1:size=1,setpts=N/({FPS}*TB)[deco_src];")
        if decoration and frame_style == "glow":
            filter_parts.append(f"[bg][deco_src]overlay={center}:format=auto[bg_glow];")
            base = "[bg_glow]"
        filter_parts.append(
            f"[mask_src]scale={fg_w}:{fg_h}[mask_scaled];"
            "[fg][mask_scaled]alphamerge[fg_rounded];"
            f"{base}[fg_rounded]overlay={center}:shortest=1[comp_fg];"
        )
        if decoration and frame_style == "vintage":
            filter_parts.append(f"[comp_fg][deco_src]overlay={center}:format=auto[comp_base];")
        else:
            filter_parts.append("[comp_fg]null[comp_base];")

    current_layer = "[comp_base]"

    # Layer: foreground figure (beat montage edits), its warm glow baked into the cached PNG
    if figure_path and os.path.exists(figure_path):
        figure_png = figures.figure_layer(figure_path, even(FIGURE_WIDTH))
        sources.append(f"movie={_filter_path(figure_png)},loop=loop=-1:size=1,setpts=N/({FPS}*TB)[figure_src];")
        filter_parts.append(f"{current_layer}[figure_src]overlay=(W-w)/2:H-h:format=auto[comp_figure];")
        current_layer = "[comp_figure]"

    # Layer: Celestial Dust Particles (Overlay with native alpha)
    if use_particles:
        # Overlay assets are 1080x1920; the preview canvas scales them down
        fit = "" if scale == 1 else f",scale={canvas_w}:{canvas_h}"
        filter_parts.append(f"[particles_src]fps={FPS}{fit}[particles];{current_layer}[particles]overlay=0:0:format=auto[comp_particles];")
        current_layer = "[comp_particles]"

    # Layer: Warm Anamorphic Light Leak Hook (0-2s)
    if use_leak:
        fit = "" if scale == 1 else f",scale={canvas_w}:{canvas_h}"
        filter_parts.append(f"[leak_src]fps={FPS}{fit}[leak];{current_layer}[leak]overlay=0:0:format=auto:eof_action=pass[comp_leak];")
        current_layer = "[comp_leak]"

    # Layer: 35mm Film Grain & Tone Curve
    if enable_film_grain:
        filter_parts.append(f"{current_layer}noise=c1s=3:c1f=t+u,eq=contrast=1.02:brightness=-0.01[comp_grained];")
        current_layer = "[comp_grained]"

    # Layer: Subtitles & Watermark Burn-in
    if subtitle_ass and os.path.exists(subtitle_ass):
        filter_parts.append(f"{current_layer}subtitles={_filter_path(subtitle_ass)}[final_v];")
        final_v_label = "[final_v]"
    else:
        final_v_label = current_layer

    filter_complex = "".join(sources + filter_parts).rstrip(";")

    args = ["-y"] + THREAD_CAPS + inputs + [
        "-filter_complex", filter_complex,
        "-map", final_v_label,
        "-map", f"{audio_idx}:a",
        "-t", f"{duration:.2f}",
        "-c:v", "libx264",
        "-preset", "ultrafast" if preview else FFMPEG_PRESET,
        "-crf", "28" if preview else "22",
        "-threads", FFMPEG_THREADS,
        "-pix_fmt", "yuv420p",
        "-c:a", "aac",
        "-b:a", "192k",
        "-shortest",
        output_path
    ]

    logger.info(f"Rendering TikTok video ({framing_mode}, particles={enable_particles}, leak={enable_light_leak}, motion={enable_dynamic_motion}) -> {output_path}...")
    try:
        _run_ffmpeg(args, total_frames=int(duration * FPS), on_progress=on_progress, stage="encode")
    finally:
        for temp in (final_audio if final_audio != voice_audio else None, montage_file):
            if temp and os.path.exists(temp):
                os.remove(temp)

    logger.info(f"Render complete: {output_path}")
    return output_path
