#!/usr/bin/env python3
"""Procedurally generate royalty-free audio assets with numpy (no downloads):
  sfx_whoosh.wav, sfx_pop.wav, sfx_ding.wav, sfx_click.wav, music_lofi.wav (looping bed)
All synthesized here -> no copyright exposure."""
import math
import wave
from pathlib import Path

import numpy as np

SR = 48000
OUT = Path(__file__).resolve().parent / "assets"


def save(name, x):
    OUT.mkdir(exist_ok=True)
    x = np.clip(x, -1, 1)
    st = np.stack([x, x], axis=1) if x.ndim == 1 else x
    data = (st * 32767).astype(np.int16)
    with wave.open(str(OUT / name), "wb") as w:
        w.setnchannels(2); w.setsampwidth(2); w.setframerate(SR)
        w.writeframes(data.tobytes())
    return OUT / name


def env(n, a=0.005, d=0.1, s=0.0, r=0.1, hold=0.0):
    t = np.arange(n) / SR
    total = n / SR
    e = np.ones(n)
    e = np.where(t < a, t / a, e)
    e = np.where((t >= a) & (t < a + d), 1 - (1 - s) * (t - a) / d, e)
    e = np.where((t >= a + d) & (t < total - r), s if s > 0 else e, e)
    e = np.where(t >= total - r, np.maximum(0, (total - t) / r) * (s if s > 0 else 1), e)
    return e


def whoosh(dur=0.35):
    n = int(SR * dur)
    noise = np.random.randn(n)
    # band-pass sweep via simple one-pole filters on a sweeping frequency
    t = np.arange(n) / SR
    f = 400 + 3000 * (t / dur) ** 0.5
    out = np.zeros(n); y = 0.0
    for i in range(n):
        a = min(1.0, f[i] / SR * 2 * math.pi)
        y += a * (noise[i] - y)
        out[i] = y
    out = out / (np.abs(out).max() + 1e-9)
    return out * env(n, a=0.02, d=0.1, s=0.6, r=0.15) * 0.6


def pop(dur=0.12):
    n = int(SR * dur); t = np.arange(n) / SR
    f = 900 * np.exp(-t * 40) + 150
    x = np.sin(2 * np.pi * np.cumsum(f) / SR)
    return x * env(n, a=0.002, d=0.08, r=0.03) * 0.7


def ding(dur=0.9):
    n = int(SR * dur); t = np.arange(n) / SR
    x = (np.sin(2 * np.pi * 1760 * t) + 0.5 * np.sin(2 * np.pi * 2637 * t) + 0.3 * np.sin(2 * np.pi * 3520 * t))
    return x * np.exp(-t * 4) * 0.5


def click(dur=0.05):
    n = int(SR * dur)
    x = np.random.randn(n) * np.exp(-np.arange(n) / SR * 120)
    return x / (np.abs(x).max() + 1e-9) * 0.5


def lofi(bars=8, bpm=84):
    """Minimal lo-fi bed: kick/snare/hat + soft chord pad, swing, loopable."""
    beat = 60 / bpm
    n = int(SR * beat * 4 * bars)
    t = np.arange(n) / SR
    out = np.zeros(n)
    # chords (Fmaj7 - Am7 - Dm7 - Gm7 feel), two bars each
    chords = [[174.6, 220.0, 261.6, 329.6], [220.0, 261.6, 329.6, 392.0],
              [146.8, 174.6, 220.0, 261.6], [196.0, 233.1, 293.7, 349.2]]
    for ci, ch in enumerate(chords):
        s0 = int(ci * 2 * 4 * beat * SR); s1 = min(n, int((ci + 1) * 2 * 4 * beat * SR))
        tt = np.arange(s1 - s0) / SR
        pad = sum(np.sin(2 * np.pi * f * tt) * (0.8 ** k) for k, f in enumerate(ch))
        pad *= (0.5 + 0.5 * np.sin(2 * np.pi * 0.25 * tt)) * 0.12  # slow swell
        out[s0:s1] += pad
    # drums
    def kick(): 
        m = int(SR * 0.25); tt = np.arange(m) / SR
        return np.sin(2 * np.pi * (120 * np.exp(-tt * 18) + 40) * tt) * np.exp(-tt * 12) * 0.9
    def snare():
        m = int(SR * 0.18); tt = np.arange(m) / SR
        return (np.random.randn(m) * 0.5 + np.sin(2 * np.pi * 190 * tt)) * np.exp(-tt * 25) * 0.35
    def hat():
        m = int(SR * 0.05); return np.random.randn(m) * np.exp(-np.arange(m) / SR * 90) * 0.12
    for b in range(bars * 4):
        pos = int(b * beat * SR)
        if b % 4 in (0, 2):
            k = kick(); out[pos:pos + len(k)] += k[:max(0, min(len(k), n - pos))]
        if b % 4 in (1, 3):
            s = snare(); out[pos:pos + len(s)] += s[:max(0, min(len(s), n - pos))]
        for h in range(2):   # swung 8ths
            hp = pos + int((h * 0.5 + (0.08 if h else 0)) * beat * SR)
            if hp < n:
                hh = hat(); out[hp:hp + len(hh)] += hh[:max(0, min(len(hh), n - hp))]
    # gentle low-pass for warmth
    y = np.zeros(n); acc = 0.0; a = 0.12
    for i in range(n):
        acc += a * (out[i] - acc); y[i] = acc
    y = y / (np.abs(y).max() + 1e-9) * 0.8
    return y


if __name__ == "__main__":
    np.random.seed(7)
    for name, fn in [("sfx_whoosh.wav", whoosh), ("sfx_pop.wav", pop), ("sfx_ding.wav", ding),
                     ("sfx_click.wav", click), ("music_lofi.wav", lofi)]:
        p = save(name, fn()); print(p)
