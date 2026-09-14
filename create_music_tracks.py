import numpy as np
import wave
import subprocess
import os

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
MUSIC_DIR = os.path.join(BASE_DIR, "assets", "music")
os.makedirs(MUSIC_DIR, exist_ok=True)

sr = 44100
duration = 60
t = np.linspace(0, duration, sr * duration, False)

def make_track_2():
    # Celestial Meditation: Ethereal bells and calm harmonic drone
    # Key: D major / B minor
    chords = [
        [146.83, 220.00, 277.18, 369.99, 440.00, 554.37], # Dmaj7
        [123.47, 185.00, 220.00, 293.66, 369.99, 440.00], # Bm7
        [98.00, 146.83, 220.00, 293.66, 369.99, 440.00],  # Gmaj9
        [110.00, 164.81, 220.00, 277.18, 329.63, 440.00]  # A6
    ]
    chord_len = 15.0
    signal = np.zeros(len(t))
    for i, chord in enumerate(chords):
        c_start = i * chord_len
        c_end = (i + 1) * chord_len
        mask = (t >= c_start - 2) & (t <= c_end + 2)
        t_sub = t[mask]
        
        rel_t = t_sub - c_start
        env = np.ones(len(t_sub))
        attack = 3.5
        release = 3.5
        for idx, rt in enumerate(rel_t):
            if rt < attack:
                env[idx] = 0.5 * (1 - np.cos(np.pi * max(0, rt) / attack))
            elif rt > chord_len - release:
                env[idx] = 0.5 * (1 + np.cos(np.pi * (rt - (chord_len - release)) / release))
                
        chord_sig = np.zeros(len(t_sub))
        for freq in chord:
            detune = 1.0 + 0.0015 * np.sin(2 * np.pi * 0.25 * t_sub)
            chord_sig += 0.35 * np.sin(2 * np.pi * freq * detune * t_sub)
            chord_sig += 0.15 * np.sin(2 * np.pi * (freq * 2) * t_sub)
            chord_sig += 0.05 * np.sin(2 * np.pi * (freq * 3) * t_sub)
        signal[mask] += chord_sig * env

    signal = signal / (np.max(np.abs(signal)) + 1e-6) * 0.85
    pcm = (signal * 32767).astype(np.int16)
    wav_path = os.path.join(MUSIC_DIR, "Celestial_Meditation.wav")
    mp3_path = os.path.join(MUSIC_DIR, "Celestial_Meditation.mp3")
    with wave.open(wav_path, 'w') as wf:
        wf.setnchannels(1)
        wf.setsampwidth(2)
        wf.setframerate(sr)
        wf.writeframes(pcm.tobytes())
    subprocess.run([
        'ffmpeg', '-y', '-i', wav_path,
        '-af', 'aecho=0.8:0.9:1200|2000:0.35|0.2,lowpass=f=2500,volume=1.2',
        '-c:a', 'libmp3lame', '-q:a', '2', mp3_path
    ], check=True, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    if os.path.exists(wav_path):
        os.remove(wav_path)
    print("Generated", mp3_path)

def make_track_3():
    # Deep Sanctuary Piano: Soft gentle arpeggiated piano-like tones
    notes = [
        # Measure 1: C - G - E - B
        (0.0, 261.63), (2.0, 392.00), (4.0, 329.63), (6.0, 493.88), (8.0, 523.25), (11.0, 392.00),
        # Measure 2: Am - E - C - G
        (15.0, 220.00), (17.0, 329.63), (19.0, 261.63), (21.0, 392.00), (23.0, 440.00), (26.0, 329.63),
        # Measure 3: F - C - A - E
        (30.0, 174.61), (32.0, 261.63), (34.0, 220.00), (36.0, 329.63), (38.0, 349.23), (41.0, 261.63),
        # Measure 4: G - D - B - F#
        (45.0, 196.00), (47.0, 293.66), (49.0, 246.94), (51.0, 369.99), (53.0, 392.00), (56.0, 293.66)
    ]
    signal = np.zeros(len(t))
    for start_t, freq in notes:
        mask = (t >= start_t) & (t < start_t + 7.0)
        dt = t[mask] - start_t
        env = np.exp(-dt * 0.7) # Gentle piano decay
        note_sig = (
            0.6 * np.sin(2 * np.pi * freq * dt) +
            0.25 * np.sin(2 * np.pi * freq * 2 * dt) * np.exp(-dt * 1.5) +
            0.1 * np.sin(2 * np.pi * freq * 3 * dt) * np.exp(-dt * 2.5) +
            0.05 * np.sin(2 * np.pi * freq * 4 * dt) * np.exp(-dt * 4.0)
        )
        signal[mask] += note_sig * env

    signal = signal / (np.max(np.abs(signal)) + 1e-6) * 0.85
    pcm = (signal * 32767).astype(np.int16)
    wav_path = os.path.join(MUSIC_DIR, "Deep_Sanctuary_Piano.wav")
    mp3_path = os.path.join(MUSIC_DIR, "Deep_Sanctuary_Piano.mp3")
    with wave.open(wav_path, 'w') as wf:
        wf.setnchannels(1)
        wf.setsampwidth(2)
        wf.setframerate(sr)
        wf.writeframes(pcm.tobytes())
    subprocess.run([
        'ffmpeg', '-y', '-i', wav_path,
        '-af', 'aecho=0.8:0.88:800|1400:0.4|0.25,lowpass=f=3200,volume=1.3',
        '-c:a', 'libmp3lame', '-q:a', '2', mp3_path
    ], check=True, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    if os.path.exists(wav_path):
        os.remove(wav_path)
    print("Generated", mp3_path)

if __name__ == "__main__":
    make_track_2()
    make_track_3()
