#!/usr/bin/env python3
"""
Bible Studio CLI Generator
Usage:
    python3 create_clip.py --book "Salmos" --chapter 23 --start 0 --end 15 --citation "PSALM 23:1-3"
"""
import argparse
import os
import subprocess
import time
import downloader
import audio_engine
import subtitles
import transcripts
import video_engine

def main():
    parser = argparse.ArgumentParser(description="Generador de videos de TikTok con la voz de David Suchet")
    parser.add_argument("--book", default="Salmos", help="Nombre del libro en español o inglés (ej. Salmos, Juan, Romanos)")
    parser.add_argument("--chapter", type=int, default=23, help="Número de capítulo (ej. 23, 1, 8)")
    parser.add_argument("--start", type=float, default=0.0, help="Segundo de inicio del recorte")
    parser.add_argument("--end", type=float, default=15.0, help="Segundo de fin del recorte")
    parser.add_argument("--citation", default="", help="Cita bíblica que se muestra en pantalla (ej: PSALM 23:1-3)")
    parser.add_argument("--text", default="", help="Texto personalizado para los subtítulos (opcional, por defecto se sincroniza con la narración)")
    parser.add_argument("--visual", default="assets/visuals/loop_good_shepherd.mp4", help="Ruta al video, gif o imagen de fondo")
    parser.add_argument("--music", default="assets/music/Emile_Mosseri_Jacob_And_The_Stone.mp3", help="Ruta a la pista de música")
    parser.add_argument("--music-volume", type=float, default=0.16, help="Volumen de la música (0.0 a 0.5)")
    parser.add_argument("--no-music", action="store_true", help="Generar sin música de fondo (voz pura)")
    parser.add_argument("--style", default="typewriter", choices=["typewriter", "spokenbyhim", "classicserif", "modern_bold", "none"], help="Estilo de subtítulo")
    parser.add_argument("--no-subtitles", action="store_true", help="Generar sin subtítulos quemados")
    parser.add_argument("--mode", default="pitch_black", choices=["pitch_black", "fullscreen", "ambient"], help="Modo de lienzo y encuadre")
    parser.add_argument("--no-particles", action="store_true", help="Desactivar overlay de partículas celestiales")
    parser.add_argument("--no-leaks", action="store_true", help="Desactivar fuga de luz cálida de entrada")
    parser.add_argument("--no-motion", action="store_true", help="Desactivar cámara viva y micro-zooms reactivos")
    parser.add_argument("--no-grain", action="store_true", help="Desactivar grano fílmico 35mm")
    parser.add_argument("--radius", type=int, default=42, help="Radio de curvatura de las esquinas del marco")
    parser.add_argument("--pacing", default="cinematic", choices=["cinematic", "dynamic"], help="Ritmo de presentación: cinematic (~4.5s) o dynamic (~2.4s)")
    parser.add_argument("--output", default="", help="Ruta del video final de salida")

    args = parser.parse_args()
    if args.end <= args.start:
        parser.error("--end tiene que ser mayor que --start")

    print(f"✝ Descargando/obteniendo audio de David Suchet para {args.book} {args.chapter}...")
    audio_info = downloader.download_audio_chapter(args.book, args.chapter)
    osis = audio_info["osis"]
    book_name = audio_info["book"]["name_en"]

    citation = downloader.normalize_citation_english(args.citation or f"{book_name} {args.chapter}")

    timestamp = int(time.time())
    base_dir = os.path.dirname(os.path.abspath(__file__))
    cache_dir = os.path.join(base_dir, "cache")
    trimmed_audio = os.path.join(cache_dir, f"cli_voice_{osis}_{timestamp}.mp3")

    print(f"🎙️ Recortando audio de {args.start}s a {args.end}s con realce de voz...")
    audio_engine.trim_speech_audio(audio_info["local_path"], trimmed_audio, args.start, args.end)

    clip_dur = args.end - args.start
    ass_path = None
    timed = None
    if not args.no_subtitles and args.style != "none":
        if args.text:
            timed = subtitles.generate_timed_subtitles(args.text, clip_dur)
        else:
            print("📝 Sincronizando subtítulos con la narración...")
            timed, source = transcripts.get_clip_phrases(osis, args.chapter, args.start, args.end)
            print(f"   {len(timed)} frases ({source})")
        ass_path = os.path.join(cache_dir, f"cli_sub_{osis}_{timestamp}.ass")
        subtitles.create_ass_subtitles(timed, ass_path, style_name=args.style, citation=citation, citation_duration=clip_dur)
    elif citation:
        ass_path = os.path.join(cache_dir, f"cli_cit_{osis}_{timestamp}.ass")
        subtitles.create_ass_subtitles([], ass_path, style_name="classicserif", citation=citation, citation_duration=clip_dur)

    out_file = args.output or os.path.join(base_dir, "outputs", f"tiktok_{osis}_{args.chapter}_{timestamp}.mp4")

    print(f"🎬 Renderizando video 9:16 con FFmpeg en {out_file}...")
    try:
        video_engine.render_tiktok_video(
            voice_audio=trimmed_audio,
            visual_path=os.path.abspath(args.visual),
            music_audio=None if args.no_music else os.path.abspath(args.music),
            subtitle_ass=ass_path,
            output_path=out_file,
            music_volume=args.music_volume,
            corner_radius=args.radius,
            slideshow_pacing=args.pacing,
            framing_mode=args.mode,
            whisper_phrases=timed or None,
            enable_particles=not args.no_particles,
            enable_light_leak=not args.no_leaks,
            enable_dynamic_motion=not args.no_motion,
            enable_film_grain=not args.no_grain
        )
    finally:
        for path in (trimmed_audio, ass_path):
            if path and os.path.exists(path):
                os.remove(path)

    # Generate thumbnail for library
    thumb_filename = os.path.splitext(os.path.basename(out_file))[0] + ".jpg"
    thumb_path = os.path.join(base_dir, "outputs", "thumbnails", thumb_filename)
    os.makedirs(os.path.dirname(thumb_path), exist_ok=True)
    subprocess.run([
        "ffmpeg", "-y", "-ss", f"{min(2.0, clip_dur / 2):.1f}", "-i", out_file,
        "-vframes", "1",
        "-vf", "scale=160:284:force_original_aspect_ratio=increase,crop=160:284",
        thumb_path
    ], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)

    print(f"✅ ¡Video generado con éxito!: {out_file}")

if __name__ == "__main__":
    main()
