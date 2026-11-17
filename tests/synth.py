"""Makes small test recordings with known answers (also handy as a demo):

    python3 -m tests.synth OUTDIR

screen.mp4  640x360, 6 s: a button at 100,100 (80x80) turns green at 2.00 s; a knob in
            the square 400,80 (160x160) sweeps with a green pointer. No audio.
plugin.mp4  the same knob 0.90 s later (as if heard over Wi-Fi), and audio: silence,
            then from 2.90 s a tone whose brightness follows that knob.
"""
import math
import os
import subprocess
import sys

import numpy as np
from PIL import Image, ImageDraw

FPS, SECONDS, W, H = 30, 6.0, 640, 360
LAG = 0.90          # plugin behind the screen
PRESS = 2.00        # the button lights
SOUND = PRESS + LAG  # the sound starts
KNOB = (400, 80, 160, 160)
BUTTON = (100, 100, 80, 80)


def knob_angle(t):
    """Degrees clockwise from 12 o'clock: a slow sweep that isn't periodic over the clip."""
    return 120 * math.sin(2 * math.pi * 0.23 * t) * math.cos(2 * math.pi * 0.07 * t)


def frame(t, lag=0.0, button=True):
    im = Image.new('RGB', (W, H), (40, 44, 48))
    d = ImageDraw.Draw(im)
    if button:
        x, y, w, h = BUTTON
        d.rectangle([x, y, x + w, y + h], fill=(40, 210, 80) if t >= PRESS else (200, 200, 200))
    x, y, w, h = KNOB
    cx, cy, r = x + w / 2, y + h / 2, w / 2 - 6
    d.ellipse([cx - r, cy - r, cx + r, cy + r], fill=(10, 10, 10), outline=(30, 70, 40), width=3)
    a = math.radians(knob_angle(max(0.0, t - lag)))
    d.line([cx + 0.35 * r * math.sin(a), cy - 0.35 * r * math.cos(a), cx + 0.95 * r * math.sin(a),
            cy - 0.95 * r * math.cos(a)], fill=(40, 220, 90), width=9)
    return im


def write_video(path, lag, button, audio=None):
    cmd = ['ffmpeg', '-y', '-v', 'error', '-f', 'rawvideo', '-pix_fmt', 'rgb24', '-s', f'{W}x{H}', '-r', str(FPS),
           '-i', '-']
    wav = None
    if audio is not None:
        import wave
        wav = path + '.wav'
        pcm = (np.clip(audio, -1, 1) * 32767).astype('<i2')
        with wave.open(wav, 'wb') as f:
            f.setnchannels(1); f.setsampwidth(2); f.setframerate(48000); f.writeframes(pcm.tobytes())
        cmd += ['-i', wav, '-c:a', 'aac', '-b:a', '192k', '-shortest']
    else:
        cmd += ['-an']
    cmd += ['-c:v', 'libx264', '-pix_fmt', 'yuv420p', '-crf', '18', path]
    p = subprocess.Popen(cmd, stdin=subprocess.PIPE)
    for i in range(int(SECONDS * FPS)):
        p.stdin.write(frame(i / FPS, lag, button).tobytes())
    p.stdin.close(); p.wait()
    if wav:
        os.remove(wav)


def plugin_audio():
    sr = 48000
    t = np.arange(int(SECONDS * sr)) / sr
    # Harmonics fade in with the knob: brightness follows the knob's angle (delayed with it).
    ang = np.array([knob_angle(max(0.0, x - LAG)) for x in t[::480]])
    ang = np.repeat(ang, 480)[: len(t)]
    bright = (ang + 150) / 300  # 0..1
    out = np.zeros_like(t)
    for k in range(1, 25):
        gain = np.clip(bright * 24 - (k - 1), 0, 1) / k
        out += gain * np.sin(2 * np.pi * 110 * k * t)
    out *= 0.25
    out[t < SOUND] = 0
    return out


def make(outdir):
    os.makedirs(outdir, exist_ok=True)
    screen, plugin = os.path.join(outdir, 'screen.mp4'), os.path.join(outdir, 'plugin.mp4')
    write_video(screen, 0.0, True)
    write_video(plugin, LAG, False, plugin_audio())
    return screen, plugin


if __name__ == '__main__':
    print(make(sys.argv[1] if len(sys.argv) > 1 else 'demo-media'))
