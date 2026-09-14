import subprocess
import os
import json
import logging

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger("audio_engine")

def get_audio_duration(file_path: str) -> float:
    """Get the duration of an audio or video file in seconds using ffprobe."""
    if not os.path.exists(file_path):
        raise FileNotFoundError(f"File not found: {file_path}")
        
    cmd = [
        "ffprobe", "-v", "error",
        "-show_entries", "format=duration",
        "-of", "json",
        file_path
    ]
    res = subprocess.run(cmd, capture_output=True, text=True, check=True)
    data = json.loads(res.stdout)
    return float(data["format"]["duration"])

def trim_speech_audio(
    input_file: str,
    output_file: str,
    start_sec: float,
    end_sec: float,
    enhance_voice: bool = True
) -> str:
    """
    Trim speech audio segment with optional voice enhancement
    (clean low-end rumble and light vocal presence compressor).
    """
    duration = max(0.5, end_sec - start_sec)
    os.makedirs(os.path.dirname(os.path.abspath(output_file)), exist_ok=True)
    
    af_filters = []
    if enhance_voice:
        # Highpass at 75Hz to remove mud, gentle compand to give broadcast presence
        af_filters.append("highpass=f=75")
        af_filters.append("compand=attacks=0.05:decays=0.2:points=-80/-80|-40/-28|-20/-14|0/-10")
        af_filters.append("volume=1.2")
    else:
        af_filters.append("volume=1.0")
        
    filter_str = ",".join(af_filters)
    
    cmd = [
        "ffmpeg", "-y",
        "-ss", f"{start_sec:.2f}",
        "-t", f"{duration:.2f}",
        "-i", input_file,
        "-af", filter_str,
        "-c:a", "libmp3lame", "-q:a", "2",
        output_file
    ]
    logger.info(f"Trimming audio from {start_sec}s to {end_sec}s (duration {duration}s)")
    subprocess.run(cmd, check=True, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    return output_file

def mix_voice_and_music(
    voice_file: str,
    music_file: str,
    output_file: str,
    music_volume: float = 0.15,
    fade_in: float = 1.0,
    fade_out: float = 2.0
) -> str:
    """
    Mix narration voice with background music track.
    Applies volume ducking to music and smooth fade in/out transitions.
    """
    voice_dur = get_audio_duration(voice_file)
    fade_in = min(fade_in, voice_dur / 3.0)
    fade_out = min(fade_out, voice_dur / 3.0)
    fade_out_start = max(0.0, voice_dur - fade_out)
    
    os.makedirs(os.path.dirname(os.path.abspath(output_file)), exist_ok=True)
    
    filter_complex = (
        f"[0:a]afade=t=in:ss=0:d={fade_in:.2f},"
        f"afade=t=out:st={fade_out_start:.2f}:d={fade_out:.2f},volume=1.0[voice];"
        f"[1:a]volume={music_volume:.2f},"
        f"afade=t=in:ss=0:d={fade_in:.2f},"
        f"afade=t=out:st={fade_out_start:.2f}:d={fade_out:.2f}[bgm];"
        f"[voice][bgm]amix=inputs=2:duration=first:dropout_transition=2[aout]"
    )
    
    cmd = [
        "ffmpeg", "-y",
        "-i", voice_file,
        "-stream_loop", "-1",
        "-i", music_file,
        "-filter_complex", filter_complex,
        "-map", "[aout]",
        "-t", f"{voice_dur:.2f}",
        "-c:a", "libmp3lame", "-q:a", "2",
        output_file
    ]
    logger.info(f"Mixing voice ({voice_file}) and music ({music_file}, vol {music_volume}) -> {output_file}")
    subprocess.run(cmd, check=True, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    return output_file

if __name__ == "__main__":
    # Quick self-test
    input_voice = "cache/audio/Ps_23.mp3"
    trimmed_voice = "cache/audio/test_trimmed.mp3"
    mixed_audio = "cache/audio/test_mixed.mp3"
    bgm = "assets/music/Peaceful_Worship_Pad.mp3"
    
    if os.path.exists(input_voice):
        print(f"Total duration of Ps 23: {get_audio_duration(input_voice):.2f}s")
        # Trim first 20 seconds
        trim_speech_audio(input_voice, trimmed_voice, 0.0, 20.0)
        print(f"Trimmed duration: {get_audio_duration(trimmed_voice):.2f}s")
        mix_voice_and_music(trimmed_voice, bgm, mixed_audio, music_volume=0.18)
        print(f"Mixed audio duration: {get_audio_duration(mixed_audio):.2f}s")
