"""Helper to generate high-quality demo assets: sample picture, animated GIF sticker, and background music."""
import math
import struct
import wave
from pathlib import Path
from PIL import Image, ImageDraw, ImageFilter
import subprocess

DEMO_DIR = Path(__file__).resolve().parent / "assets" / "demo"
DEMO_DIR.mkdir(parents=True, exist_ok=True)


def generate_demo_image():
    """Generates an aesthetic landscape card image (800x800)."""
    width, height = 800, 800
    img = Image.new("RGBA", (width, height), (0, 0, 0, 0))
    draw = ImageDraw.Draw(img)

    # Sky gradient
    for y in range(height):
        ratio = y / height
        r = int(24 + ratio * (255 - 24))
        g = int(32 + ratio * (154 - 32))
        b = int(72 + ratio * (162 - 72))
        draw.line([(0, y), (width, y)], fill=(r, g, b, 255))

    # Glowing Sun
    sun_x, sun_y, radius = 400, 360, 140
    for r in range(radius, 0, -5):
        alpha = int(255 * (1 - (r / radius) ** 1.5))
        draw.ellipse(
            [sun_x - r, sun_y - r, sun_x + r, sun_y + r],
            fill=(255, 235, 150, alpha)
        )

    # Mountain layers
    pts1 = [(0, 520)]
    for x in range(0, width + 40, 40):
        y = 520 - int(math.sin(x * 0.008) * 80 + math.cos(x * 0.015) * 40)
        pts1.append((x, y))
    pts1.extend([(width, height), (0, height)])
    draw.polygon(pts1, fill=(80, 50, 110, 220))

    pts2 = [(0, 620)]
    for x in range(0, width + 30, 30):
        y = 620 - int(math.cos(x * 0.012) * 90 + math.sin(x * 0.02) * 50)
        pts2.append((x, y))
    pts2.extend([(width, height), (0, height)])
    draw.polygon(pts2, fill=(35, 25, 60, 255))

    mist = Image.new("RGBA", (width, height), (0, 0, 0, 0))
    mist_draw = ImageDraw.Draw(mist)
    mist_draw.rectangle([0, 680, width, height], fill=(255, 255, 255, 40))
    mist = mist.filter(ImageFilter.GaussianBlur(30))
    img = Image.alpha_composite(img, mist)

    out_path = DEMO_DIR / "sample_picture.png"
    img.save(out_path, format="PNG")
    print(f"Generated demo picture: {out_path}")
    return out_path


def generate_demo_gif():
    """Generates an attractive animated glowing pulsing star sticker with transparency (320x320)."""
    frames = []
    num_frames = 20
    size = 320
    cx, cy = size // 2, size // 2

    for f in range(num_frames):
        frame = Image.new("RGBA", (size, size), (0, 0, 0, 0))
        draw = ImageDraw.Draw(frame)
        angle_offset = (f / num_frames) * (2 * math.pi)
        pulse = 1.0 + 0.18 * math.sin(angle_offset)

        points = []
        outer_r = 100 * pulse
        inner_r = 45 * pulse
        for i in range(10):
            r = outer_r if i % 2 == 0 else inner_r
            angle = (i * math.pi / 5) - math.pi / 2 + (angle_offset * 0.25)
            x = cx + r * math.cos(angle)
            y = cy + r * math.sin(angle)
            points.append((x, y))

        for glow_r in range(int(outer_r + 20), int(outer_r), -4):
            glow_alpha = int(40 * (1 - (glow_r - outer_r) / 20))
            draw.ellipse(
                [cx - glow_r, cy - glow_r, cx + glow_r, cy + glow_r],
                fill=(255, 220, 100, glow_alpha)
            )

        draw.polygon(points, fill=(255, 215, 0, 255), outline=(255, 255, 220, 255))
        draw.ellipse([cx - 20, cy - 20, cx + 20, cy + 20], fill=(255, 255, 255, 220))
        frames.append(frame)

    out_path = DEMO_DIR / "sample_sticker.gif"
    frames[0].save(
        out_path,
        save_all=True,
        append_images=frames[1:],
        duration=50,
        loop=0,
        disposal=2
    )
    print(f"Generated demo GIF: {out_path}")
    return out_path


def generate_demo_music():
    """Generates a clear, loud, uplifting stereo melodic lofi/synth track in MP3 format (25s)."""
    wav_path = DEMO_DIR / "sample_music.wav"
    mp3_path = DEMO_DIR / "sample_music.mp3"
    sample_rate = 44100
    duration = 25.0
    num_samples = int(sample_rate * duration)

    bpm = 110
    beat_len = 60.0 / bpm
    bar_len = beat_len * 4

    # Progression: Cmaj7 -> G -> Am7 -> Fmaj7
    chords = [
        [261.63, 329.63, 392.00, 493.88, 523.25],
        [196.00, 246.94, 293.66, 392.00, 587.33],
        [220.00, 261.63, 329.63, 440.00, 659.25],
        [174.61, 220.00, 261.63, 329.63, 523.25]
    ]

    melody_notes = [
        (0.0, 523.25), (0.5, 659.25), (1.0, 783.99), (1.75, 659.25),
        (2.0, 587.33), (2.5, 493.88), (3.0, 392.00), (3.75, 493.88),
        (4.0, 440.00), (4.5, 523.25), (5.0, 659.25), (5.5, 523.25),
        (6.0, 698.46), (6.5, 659.25), (7.0, 587.33), (7.5, 523.25)
    ]

    left_samples = []
    right_samples = []

    for i in range(num_samples):
        t = i / sample_rate
        chord_idx = int((t % (bar_len * 2)) / (bar_len * 2 / len(chords)))
        chord_freqs = chords[chord_idx % len(chords)]

        chord_beat = (t % beat_len) / beat_len
        chord_env = math.exp(-chord_beat * 3.2)
        chord_val_l = 0.0
        chord_val_r = 0.0
        for fi, freq in enumerate(chord_freqs):
            pan = 0.25 * math.sin(fi * 1.5)
            tone = math.sin(2 * math.pi * freq * t) + 0.3 * math.sin(4 * math.pi * freq * t)
            chord_val_l += tone * (0.5 - pan) * chord_env * 0.22
            chord_val_r += tone * (0.5 + pan) * chord_env * 0.22

        bass_freq = chord_freqs[0] / 2.0
        bass_env = math.exp(-chord_beat * 2.0)
        bass_val = (math.sin(2 * math.pi * bass_freq * t) + 0.3 * math.sin(4 * math.pi * bass_freq * t)) * bass_env * 0.35

        mel_t = t % 8.0
        mel_val = 0.0
        for start_t, mfreq in melody_notes:
            if 0 <= mel_t - start_t < 0.6:
                dt = mel_t - start_t
                menv = math.exp(-dt * 4.5)
                mel_val += (math.sin(2 * math.pi * mfreq * t) + 0.45 * math.sin(4 * math.pi * mfreq * t)) * menv * 0.35

        shaker_beat = (t % (beat_len / 2)) / (beat_len / 2)
        shaker_env = math.exp(-shaker_beat * 25.0)
        shaker = math.sin(2 * math.pi * 3200 * t) * shaker_env * 0.12

        # Fast punchy attack (fade in 0.2s, fade out 1.0s)
        master_fade = min(1.0, t / 0.2) * min(1.0, (duration - t) / 1.0)
        out_l = (chord_val_l + bass_val * 0.5 + mel_val * 0.75 + shaker * 0.4) * master_fade
        out_r = (chord_val_r + bass_val * 0.5 + mel_val * 0.75 + shaker * 0.6) * master_fade

        sample_l = int(max(-32767, min(32767, out_l * 28000)))
        sample_r = int(max(-32767, min(32767, out_r * 28000)))
        left_samples.append(sample_l)
        right_samples.append(sample_r)

    stereo_samples = []
    for l, r in zip(left_samples, right_samples):
        stereo_samples.extend([l, r])

    with wave.open(str(wav_path), "wb") as wav_file:
        wav_file.setnchannels(2)
        wav_file.setsampwidth(2)
        wav_file.setframerate(sample_rate)
        raw_data = struct.pack(f"<{len(stereo_samples)}h", *stereo_samples)
        wav_file.writeframes(raw_data)

    subprocess.run([
        "ffmpeg", "-y", "-i", str(wav_path),
        "-codec:a", "libmp3lame", "-b:a", "192k",
        "-ac", "2",
        str(mp3_path)
    ], check=True, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)

    if wav_path.exists():
        wav_path.unlink()

    print(f"Generated loud, clear stereo demo music: {mp3_path}")
    return mp3_path


if __name__ == "__main__":
    generate_demo_image()
    generate_demo_gif()
    generate_demo_music()
