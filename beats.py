"""
Beat tracking for music-synced edit cuts (numpy only, no librosa).

Onset strength comes from log-spectral flux, tempo from the autocorrelation of that
envelope (weighted toward ~110 BPM so half/double-time ambiguity resolves to an
editable pace), and beats are placed with Ellis' dynamic-programming tracker.
Results are cached per music file.
"""
import hashlib
import json
import os
import subprocess

import numpy as np

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
CACHE_DIR = os.path.join(BASE_DIR, "cache", "beats")

SR = 11025
WIN = 1024
HOP = 256
FPS = SR / HOP  # onset envelope frames per second (~43)
TEMPO_CENTER_BPM = 110.0

def _decode(path: str, max_sec: float) -> np.ndarray:
    raw = subprocess.run(
        ["ffmpeg", "-loglevel", "error", "-i", path, "-t", f"{max_sec:.2f}", "-ac", "1", "-ar", str(SR), "-f", "s16le", "-"],
        capture_output=True, check=True).stdout
    return np.frombuffer(raw, dtype=np.int16).astype(np.float32) / 32768.0

def onset_envelope(x: np.ndarray) -> np.ndarray:
    """Half-wave rectified log-spectral flux, locally normalized."""
    if len(x) < WIN * 2:
        return np.zeros(1, dtype=np.float32)
    window = np.hanning(WIN).astype(np.float32)
    n_frames = 1 + (len(x) - WIN) // HOP
    flux = np.zeros(n_frames, dtype=np.float32)
    prev = None
    for chunk_start in range(0, n_frames, 1024):
        idx = np.arange(chunk_start, min(n_frames, chunk_start + 1024))
        frames = np.stack([x[i * HOP:i * HOP + WIN] for i in idx]) * window
        spec = np.log1p(10.0 * np.abs(np.fft.rfft(frames, axis=1))).astype(np.float32)
        if prev is not None:
            spec = np.vstack([prev[None, :], spec])
            diff = np.maximum(0.0, np.diff(spec, axis=0)).sum(axis=1)
            flux[idx] = diff
        else:
            diff = np.maximum(0.0, np.diff(spec, axis=0)).sum(axis=1)
            flux[idx[1:]] = diff
        prev = spec[-1]
    # Remove slow loudness changes, keep the transients
    kernel = np.ones(int(FPS)) / int(FPS)
    flux = np.maximum(0.0, flux - np.convolve(flux, kernel, mode="same"))
    return flux / (flux.std() + 1e-9)

def estimate_tempo(env: np.ndarray) -> float:
    env = env - env.mean()
    max_lag = int(FPS * 60 / 50)
    ac = np.correlate(env, env, mode="full")[len(env) - 1:len(env) - 1 + max_lag]
    lags = np.arange(len(ac))
    valid = lags >= int(FPS * 60 / 180)
    bpm = np.where(lags > 0, 60 * FPS / np.maximum(lags, 1), 0)
    weight = np.exp(-0.5 * (np.log2(np.maximum(bpm, 1e-6) / TEMPO_CENTER_BPM) / 0.9) ** 2)
    score = np.where(valid, ac * weight, -np.inf)
    return float(60 * FPS / int(np.argmax(score)))

def track_beats(env: np.ndarray, bpm: float, tightness: float = 100.0) -> np.ndarray:
    """Ellis (2007) dynamic programming beat tracker; returns beat frame indices."""
    period = 60 * FPS / bpm
    n = len(env)
    score = env.astype(np.float64).copy()
    backlink = -np.ones(n, dtype=np.int64)
    lo, hi = int(round(period / 2)), int(round(period * 2))
    offsets = np.arange(-hi, -lo + 1)
    penalty = -tightness * np.log(-offsets / period) ** 2
    for i in range(hi, n):
        candidates = score[i + offsets] + penalty
        best = int(np.argmax(candidates))
        score[i] = env[i] + candidates[best]
        backlink[i] = i + offsets[best]
    # Start from the strongest beat near the end, then follow the links back
    tail = max(0, n - int(period * 2))
    beat = tail + int(np.argmax(score[tail:]))
    beats = []
    while beat >= 0:
        beats.append(beat)
        beat = int(backlink[beat])
    return np.array(beats[::-1])

def detect_beats(music_path: str, max_sec: float = 600.0) -> dict:
    """{"bpm": float, "beats": [seconds, ...]} for the first max_sec of a music file (cached)."""
    stat = os.stat(music_path)
    key = hashlib.sha1(f"{os.path.abspath(music_path)}|{stat.st_size}|{stat.st_mtime}|{max_sec}".encode()).hexdigest()[:16]
    cache_path = os.path.join(CACHE_DIR, f"{key}.json")
    if os.path.exists(cache_path):
        with open(cache_path, "r", encoding="utf-8") as f:
            return json.load(f)

    env = onset_envelope(_decode(music_path, max_sec))
    if len(env) < FPS * 4:
        result = {"bpm": 0.0, "beats": []}
    else:
        bpm = estimate_tempo(env)
        beats = track_beats(env, bpm)
        result = {"bpm": round(bpm, 1), "beats": [round(b / FPS, 3) for b in beats]}

    os.makedirs(CACHE_DIR, exist_ok=True)
    with open(cache_path, "w", encoding="utf-8") as f:
        json.dump(result, f)
    return result
