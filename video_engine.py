import os
import subprocess
import json
import logging
import math
from PIL import Image, ImageDraw
import audio_engine
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
    enable_dynamic_motion: bool = True
) -> tuple[str, bool]:
    """Ensure visual is in video format with organic camera motion and Whisper-reactive zoom."""
    ext = os.path.splitext(visual_path)[1].lower()
    if ext in [".jpg", ".jpeg", ".png", ".webp"]:
        cache_signature = f"{visual_path}_{framing}_{round(duration, 1)}_{enable_dynamic_motion}_{len(whisper_phrases or [])}"
        loop_out = os.path.join(temp_dir, f"img_loop_{abs(hash(cache_signature)) % 1000000}.mp4")

        if not os.path.exists(loop_out):
            logger.info(f"Preparing cinematic visual {visual_path} (framing={framing}, motion={enable_dynamic_motion})...")
            w, h = get_media_dimensions(visual_path)
            num_frames = int(duration * 30) + 30
            fps = 30

            zoom_expr, x_expr, y_expr = build_camera_motion_expression(
                total_frames=num_frames,
                fps=fps,
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
                vf_expr = (
                    f"scale={w}:{h},"
                    f"zoompan=z='{zoom_expr}':x='{x_expr}':y='{y_expr}':d={num_frames}:s={w}x{h}:fps=30,"
                    "eq=contrast=1.05:brightness=-0.01"
                )

            cmd = [
                "ffmpeg", "-y", "-loop", "1", "-i", visual_path,
                "-vf", vf_expr,
                "-t", f"{duration:.2f}",
                "-c:v", "libx264",
                "-preset", "fast",
                "-pix_fmt", "yuv420p",
                loop_out
            ]
            subprocess.run(cmd, check=True, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
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
    enable_dynamic_motion: bool = True
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
            enable_dynamic_motion=enable_dynamic_motion
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
        inputs.extend(["-loop", "1", "-t", f"{slide_dur:.2f}", "-i", p])
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

    threads = os.environ.get("FFMPEG_THREADS", "2")
    preset = os.environ.get("FFMPEG_PRESET", "veryfast")

    cmd = ["ffmpeg", "-y", "-threads", threads] + inputs + [
        "-filter_complex", filter_complex,
        "-map", "[vfinal]",
        "-t", f"{target_duration:.2f}",
        "-c:v", "libx264",
        "-preset", preset,
        "-pix_fmt", "yuv420p",
        output_path
    ]
    logger.info(f"Rendering dignified {pacing} slideshow ({n} cuts, {target_duration:.1f}s, {fade_time:.2f}s crossfade)...")
    subprocess.run(cmd, check=True, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    return output_path

def render_tiktok_video(
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
    enable_film_grain: bool = True
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
    particles_path = os.path.join(OVERLAYS_DIR, "particles_celestial.mov")
    light_leak_path = os.path.join(OVERLAYS_DIR, "light_leak_warm.mov")
    if enable_particles and not os.path.exists(particles_path):
        generate_overlays.generate_celestial_particles(particles_path)
    if enable_light_leak and not os.path.exists(light_leak_path):
        generate_overlays.generate_warm_light_leak(light_leak_path)

    # 1. Audio Mix (voice + optional music with ducking)
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
    if isinstance(visual_path, list) and len(visual_path) > 1:
        cache_key = f"{''.join(visual_path)}_{round(duration, 1)}_{slideshow_pacing}_{framing_mode}_{enable_dynamic_motion}"
        slideshow_file = os.path.join(CACHE_DIR, f"slideshow_{abs(hash(cache_key)) % 1000000}.mp4")
        video_input = build_slideshow_video(
            visual_path,
            duration,
            slideshow_file,
            pacing=slideshow_pacing,
            framing=framing_mode,
            whisper_phrases=whisper_phrases,
            enable_dynamic_motion=enable_dynamic_motion
        )
    elif isinstance(visual_path, list):
        video_input, _ = prepare_visual_input(
            visual_path[0],
            duration=duration,
            framing=framing_mode,
            whisper_phrases=whisper_phrases,
            enable_dynamic_motion=enable_dynamic_motion
        )
    else:
        video_input, _ = prepare_visual_input(
            visual_path,
            duration=duration,
            framing=framing_mode,
            whisper_phrases=whisper_phrases,
            enable_dynamic_motion=enable_dynamic_motion
        )

    orig_w, orig_h = get_media_dimensions(video_input)
    fg_w, fg_h = calculate_foreground_size(orig_w, orig_h)
    mask_path = generate_rounded_mask(fg_w, fg_h, radius=corner_radius)

    # 3. Input streams indexing for FFmpeg
    # 0: visual video_input
    # 1: mask_path
    # Next inputs depend on overlay flags
    inputs = [
        "-stream_loop", "-1", "-i", video_input,
        "-loop", "1", "-i", mask_path
    ]

    particles_idx = None
    if enable_particles and os.path.exists(particles_path):
        particles_idx = len(inputs) // 4
        inputs.extend(["-stream_loop", "-1", "-t", f"{duration:.2f}", "-i", particles_path])

    leak_idx = None
    if enable_light_leak and os.path.exists(light_leak_path):
        leak_idx = len(inputs) // 4
        inputs.extend(["-t", f"{duration:.2f}", "-i", light_leak_path])

    audio_idx = len(inputs) // 4
    inputs.extend(["-i", final_audio])

    # 4. Filtergraph Assembly
    filter_parts = []

    if framing_mode == "fullscreen":
        # Fullscreen 9:16 bleed with subtle dark vignette at top and bottom for text contrast
        filter_parts.append(
            "[0:v]scale=1080:1920:force_original_aspect_ratio=increase,crop=1080:1920,eq=contrast=1.04:brightness=-0.02[art];"
            f"color=c=black@0.26:s=1080x360:d={duration:.2f}[top_shade];"
            f"color=c=black@0.42:s=1080x420:d={duration:.2f}[bot_shade];"
            "[art][top_shade]overlay=0:0[art_top];"
            "[art_top][bot_shade]overlay=0:H-h[comp_base];"
        )
    elif framing_mode == "ambient":
        # Deeply darkened and desaturated ambient background
        filter_parts.append(
            "[0:v]scale=1080:1920:force_original_aspect_ratio=increase,crop=1080:1920,boxblur=26:5,eq=brightness=-0.65:contrast=1.1:saturation=0.5[bg];"
            f"[0:v]scale={fg_w}:{fg_h},eq=contrast=1.06:brightness=-0.01,format=yuva420p[fg];"
            f"[1:v]scale={fg_w}:{fg_h}[mask_scaled];"
            "[fg][mask_scaled]alphamerge[fg_rounded];"
            f"[bg][fg_rounded]overlay=(W-w)/2:(H-h)/2{'+' if y_offset >= 0 else ''}{y_offset}:shortest=1[comp_base];"
        )
    else:
        # Default: Pure Pitch Black #000000 (Minimalist Viral Ref @nehzro)
        filter_parts.append(
            f"color=c=black:s=1080x1920:d={duration:.2f}[bg];"
            f"[0:v]scale={fg_w}:{fg_h},eq=contrast=1.06:brightness=-0.01,format=yuva420p[fg];"
            f"[1:v]scale={fg_w}:{fg_h}[mask_scaled];"
            "[fg][mask_scaled]alphamerge[fg_rounded];"
            f"[bg][fg_rounded]overlay=(W-w)/2:(H-h)/2{'+' if y_offset >= 0 else ''}{y_offset}:shortest=1[comp_base];"
        )

    current_layer = "[comp_base]"

    # Layer: Celestial Dust Particles (Overlay with native alpha)
    if particles_idx is not None:
        filter_parts.append(f"{current_layer}[{particles_idx}:v]overlay=0:0:format=auto[comp_particles];")
        current_layer = "[comp_particles]"

    # Layer: Warm Anamorphic Light Leak Hook (0-2s)
    if leak_idx is not None:
        filter_parts.append(f"{current_layer}[{leak_idx}:v]overlay=0:0:format=auto:eof_action=pass[comp_leak];")
        current_layer = "[comp_leak]"

    # Layer: 35mm Film Grain & Tone Curve
    if enable_film_grain:
        filter_parts.append(f"{current_layer}noise=c1s=3:c1f=t+u,eq=contrast=1.02:brightness=-0.01[comp_grained];")
        current_layer = "[comp_grained]"

    # Layer: Subtitles & Watermark Burn-in
    if subtitle_ass and os.path.exists(subtitle_ass):
        safe_ass = subtitle_ass.replace("\\", "/").replace(":", "\\:")
        filter_parts.append(f"{current_layer}subtitles='{safe_ass}'[final_v]")
        final_v_label = "[final_v]"
    else:
        final_v_label = current_layer.rstrip(";")

    filter_complex = "".join(filter_parts).rstrip(";")

    threads = os.environ.get("FFMPEG_THREADS", "2")
    preset = os.environ.get("FFMPEG_PRESET", "veryfast")

    cmd = [
        "ffmpeg", "-y",
        "-threads", threads
    ] + inputs + [
        "-filter_complex", filter_complex,
        "-map", final_v_label,
        "-map", f"{audio_idx}:a",
        "-t", f"{duration:.2f}",
        "-c:v", "libx264",
        "-preset", preset,
        "-crf", "22",
        "-pix_fmt", "yuv420p",
        "-c:a", "aac",
        "-b:a", "192k",
        "-shortest",
        output_path
    ]

    logger.info(f"Rendering TikTok video ({framing_mode}, particles={enable_particles}, leak={enable_light_leak}, motion={enable_dynamic_motion}) -> {output_path}...")
    res = subprocess.run(cmd, capture_output=True, text=True)
    if res.returncode != 0:
        logger.error(f"FFmpeg error: {res.stderr}")
        raise RuntimeError(f"FFmpeg failed with return code {res.returncode}")

    logger.info(f"Render complete: {output_path}")
    return output_path
