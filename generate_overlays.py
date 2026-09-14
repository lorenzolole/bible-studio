import os
import subprocess
import time
import numpy as np
from PIL import Image, ImageDraw, ImageFilter

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
OVERLAYS_DIR = os.path.join(BASE_DIR, "assets", "overlays")
CACHE_DIR = os.path.join(BASE_DIR, "cache")
os.makedirs(OVERLAYS_DIR, exist_ok=True)
os.makedirs(CACHE_DIR, exist_ok=True)

def generate_celestial_particles(
    output_path: str,
    width: int = 1080,
    height: int = 1920,
    fps: int = 30,
    duration: float = 4.0,
    num_particles: int = 48
) -> str:
    """
    Generate a seamless, dignified loop of floating golden-white celestial dust particles
    with soft bokeh depth and alpha transparency (lossless FFV1 yuva420p: half the decoded
    size of ARGB, which matters inside the 512 MB render container).
    """
    if os.path.exists(output_path):
        return output_path

    print(f"Generating celestial particles overlay ({duration}s @ {fps}fps)...")
    t0 = time.time()
    total_frames = int(duration * fps)
    temp_frames_dir = os.path.join(CACHE_DIR, "particle_frames_gen")
    os.makedirs(temp_frames_dir, exist_ok=True)

    np.random.seed(42)
    particles = []
    for _ in range(num_particles):
        particles.append({
            'x': np.random.uniform(30, width - 30),
            'y': np.random.uniform(0, height),
            'size': np.random.uniform(2.0, 6.5),
            'speed_y': np.random.uniform(-40, -14),  # Gentle upward float
            'drift_amp': np.random.uniform(10, 28),
            'drift_freq': np.random.uniform(0.4, 1.2),
            'phase': np.random.uniform(0, 2 * np.pi),
            'base_alpha': np.random.uniform(85, 215)
        })

    for f in range(total_frames):
        cur_time = f / fps
        img = Image.new("RGBA", (width, height), (0, 0, 0, 0))
        draw = ImageDraw.Draw(img)

        for p in particles:
            y = (p['y'] + p['speed_y'] * cur_time) % height
            x = (p['x'] + p['drift_amp'] * np.sin(2 * np.pi * p['drift_freq'] * cur_time + p['phase'])) % width

            twinkle = 0.75 + 0.25 * np.sin(4 * np.pi * cur_time + p['phase'])
            alpha = int(p['base_alpha'] * twinkle)
            r = p['size']

            # Core particle: soft warm gold/white (RGB: 255, 236, 192)
            draw.ellipse([x - r, y - r, x + r, y + r], fill=(255, 236, 192, alpha))
            # Outer ethereal halo (RGB: 255, 212, 140)
            draw.ellipse([x - r * 2.0, y - r * 2.0, x + r * 2.0, y + r * 2.0], fill=(255, 212, 140, int(alpha * 0.35)))

        img = img.filter(ImageFilter.GaussianBlur(radius=0.9))
        img.save(os.path.join(temp_frames_dir, f"frame_{f:04d}.png"))

    cmd = [
        "ffmpeg", "-y", "-framerate", str(fps), "-i", f"{temp_frames_dir}/frame_%04d.png",
        "-c:v", "ffv1", "-pix_fmt", "yuva420p", output_path
    ]
    subprocess.run(cmd, check=True, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)

    # Clean up frames
    for f in os.listdir(temp_frames_dir):
        os.remove(os.path.join(temp_frames_dir, f))
    os.rmdir(temp_frames_dir)

    print(f"Celestial particles generated in {time.time() - t0:.2f}s -> {output_path}")
    return output_path

def generate_warm_light_leak(
    output_path: str,
    width: int = 1080,
    height: int = 1920,
    fps: int = 30,
    duration: float = 2.5
) -> str:
    """
    Generate an organic warm anamorphic light leak flare entering from top-right corner
    acting as an instant retention hook during the first 2 seconds.
    """
    if os.path.exists(output_path):
        return output_path

    print(f"Generating warm light leak hook ({duration}s @ {fps}fps)...")
    t0 = time.time()
    total_frames = int(duration * fps)
    temp_frames_dir = os.path.join(CACHE_DIR, "leak_frames_gen")
    os.makedirs(temp_frames_dir, exist_ok=True)

    gw, gh = width // 4, height // 4

    for f in range(total_frames):
        t = f / fps
        if t < 0.45:
            intensity = (t / 0.45) ** 1.4
        else:
            decay_progress = (t - 0.45) / (duration - 0.45)
            intensity = max(0.0, (1.0 - decay_progress) ** 2.2)

        if intensity <= 0.005:
            img = Image.new("RGBA", (width, height), (0, 0, 0, 0))
        else:
            gimg = Image.new("RGBA", (gw, gh), (0, 0, 0, 0))
            gdraw = ImageDraw.Draw(gimg)

            center_x = gw + 25 + int(np.sin(t * 1.8) * 12)
            center_y = -35 + int(np.cos(t * 1.4) * 16)
            rx = int(gw * 0.95)
            ry = int(gh * 0.8)

            alpha_core = int(175 * intensity)
            alpha_outer = int(85 * intensity)

            # Outer warm amber flare
            gdraw.ellipse([center_x - rx, center_y - ry, center_x + rx, center_y + ry], fill=(255, 172, 68, alpha_outer))
            # Inner warm gold
            gdraw.ellipse([center_x - int(rx * 0.58), center_y - int(ry * 0.58), center_x + int(rx * 0.58), center_y + int(ry * 0.58)], fill=(255, 222, 138, alpha_core))
            # Hot white-gold center
            gdraw.ellipse([center_x - int(rx * 0.24), center_y - int(ry * 0.24), center_x + int(rx * 0.24), center_y + int(ry * 0.24)], fill=(255, 250, 224, int(alpha_core * 1.25)))

            gimg = gimg.filter(ImageFilter.GaussianBlur(radius=24))
            img = gimg.resize((width, height), Image.Resampling.BILINEAR)

        img.save(os.path.join(temp_frames_dir, f"frame_{f:04d}.png"))

    cmd = [
        "ffmpeg", "-y", "-framerate", str(fps), "-i", f"{temp_frames_dir}/frame_%04d.png",
        "-c:v", "ffv1", "-pix_fmt", "yuva420p", output_path
    ]
    subprocess.run(cmd, check=True, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)

    for f in os.listdir(temp_frames_dir):
        os.remove(os.path.join(temp_frames_dir, f))
    os.rmdir(temp_frames_dir)

    print(f"Warm light leak generated in {time.time() - t0:.2f}s -> {output_path}")
    return output_path

def ensure_overlays() -> tuple[str, str]:
    """Ensure both cinematic overlays exist and return their paths."""
    particles_path = os.path.join(OVERLAYS_DIR, "particles_celestial.mkv")
    light_leak_path = os.path.join(OVERLAYS_DIR, "light_leak_warm.mkv")

    generate_celestial_particles(particles_path)
    generate_warm_light_leak(light_leak_path)

    return particles_path, light_leak_path

if __name__ == "__main__":
    ensure_overlays()
