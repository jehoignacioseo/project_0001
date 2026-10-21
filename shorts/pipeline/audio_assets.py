#!/usr/bin/env python3
"""Procedurally generate royalty-free audio assets with numpy (no downloads):
  sfx_whoosh/pop/ding/click/cash/beep/thud/riser/chime.wav, music_lofi.wav (looping bed)
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


def cash(dur=0.7):
    """Register 'ka-ching': metallic click + bell."""
    n = int(SR * dur); t = np.arange(n) / SR
    click_ = np.random.randn(n) * np.exp(-t * 90) * 0.8
    bell = (np.sin(2 * np.pi * 2093 * t) + 0.6 * np.sin(2 * np.pi * 3136 * t) + 0.3 * np.sin(2 * np.pi * 4186 * t))
    bell = bell * np.exp(-np.maximum(t - 0.06, 0) * 6) * (t > 0.06)
    return (click_ + bell * 0.5) / 1.8


def beep(dur=0.45):
    """Barcode scanner: two short 1.2 kHz beeps."""
    n = int(SR * dur); t = np.arange(n) / SR
    x = np.sin(2 * np.pi * 1245 * t)
    g = ((t < 0.09) | ((t > 0.2) & (t < 0.29))).astype(float)
    return x * g * 0.6


def thud(dur=0.5):
    """Low impact for shouted captions."""
    n = int(SR * dur); t = np.arange(n) / SR
    f = 140 * np.exp(-t * 18) + 45
    x = np.sin(2 * np.pi * np.cumsum(f) / SR) * np.exp(-t * 9)
    x += np.random.randn(n) * np.exp(-t * 60) * 0.25
    return x / (np.abs(x).max() + 1e-9) * 0.9


def riser(dur=0.9):
    """Noise sweep rising into the score card."""
    n = int(SR * dur); t = np.arange(n) / SR
    noise = np.random.randn(n)
    f = 300 + 5000 * (t / dur) ** 2
    out = np.zeros(n); y = 0.0
    for i in range(n):
        a = min(1.0, f[i] / SR * 2 * math.pi)
        y += a * (noise[i] - y)
        out[i] = y
    out = out / (np.abs(out).max() + 1e-9)
    return out * (t / dur) ** 1.5 * 0.7


def chime(dur=1.1):
    """Two-note 'ta-da' for the score reveal (C6 -> G6)."""
    n = int(SR * dur); t = np.arange(n) / SR
    def tone(f, t0):
        tt = np.maximum(t - t0, 0)
        return (np.sin(2 * np.pi * f * tt) + 0.4 * np.sin(2 * np.pi * 2 * f * tt)) * np.exp(-tt * 3.5) * (t >= t0)
    return (tone(1046.5, 0.0) + tone(1568.0, 0.14)) * 0.4


def upbeat(bars=8, bpm=112):
    """Brighter, bouncier bed for food Shorts: major chords, plucked arpeggio, light kick, shaker."""
    beat = 60 / bpm
    n = int(SR * beat * 4 * bars)
    out = np.zeros(n)
    chords = [[261.6, 329.6, 392.0, 493.9], [220.0, 261.6, 329.6, 392.0],
              [174.6, 220.0, 261.6, 349.2], [196.0, 246.9, 293.7, 392.0]]   # C - Am - F - G
    for ci, ch in enumerate(chords):
        s0 = int(ci * 2 * 4 * beat * SR); s1 = min(n, int((ci + 1) * 2 * 4 * beat * SR))
        tt = np.arange(s1 - s0) / SR
        pad = sum(np.sin(2 * np.pi * f * tt) * (0.7 ** k) for k, f in enumerate(ch)) * 0.05
        out[s0:s1] += pad
        # plucked 16th-note arpeggio
        step = beat / 4; m = int(step * SR)
        for j in range(int((s1 - s0) / m)):
            f = ch[j % 4] * (2 if j % 8 >= 4 else 1)
            k = np.arange(min(m * 2, s1 - s0 - j * m)) / SR
            pl = np.sin(2 * np.pi * f * k) * np.exp(-k * 14) * 0.16
            out[s0 + j * m:s0 + j * m + len(pl)] += pl
    def kick():
        m = int(SR * 0.2); tt = np.arange(m) / SR
        return np.sin(2 * np.pi * (110 * np.exp(-tt * 22) + 45) * tt) * np.exp(-tt * 16) * 0.6
    def clap():
        m = int(SR * 0.12); return np.random.randn(m) * np.exp(-np.arange(m) / SR * 40) * 0.22
    def shaker():
        m = int(SR * 0.04); return np.random.randn(m) * np.exp(-np.arange(m) / SR * 150) * 0.09
    for b in range(bars * 4):
        pos = int(b * beat * SR)
        k = kick(); out[pos:pos + len(k)] += k[:max(0, min(len(k), n - pos))]
        if b % 2 == 1:
            c = clap(); out[pos:pos + len(c)] += c[:max(0, min(len(c), n - pos))]
        for h in range(4):
            hp = pos + int(h * 0.25 * beat * SR)
            if hp < n:
                s = shaker() * (1.0 if h % 2 == 0 else 0.6); out[hp:hp + len(s)] += s[:max(0, min(len(s), n - hp))]
    y = np.zeros(n); acc = 0.0; a = 0.2
    for i in range(n):
        acc += a * (out[i] - acc); y[i] = acc
    return y / (np.abs(y).max() + 1e-9) * 0.8


def sizzle(dur=0.9):
    """Grill crackle for fish / meat shots."""
    n = int(SR * dur); t = np.arange(n) / SR
    x = np.random.randn(n) * (np.random.rand(n) > 0.6)       # sparse crackles
    x += np.random.randn(n) * 0.3
    y = np.zeros(n); acc = 0.0; a = 0.5
    for i in range(n):
        acc += a * (x[i] - acc); y[i] = x[i] - acc              # high-pass-ish
    y = y / (np.abs(y).max() + 1e-9)
    return y * env(n, a=0.05, d=0.2, s=0.7, r=0.3) * 0.5


def pour(dur=1.1):
    """Water pouring into a pot: low rumble + bubbling noise rising in pitch."""
    n = int(SR * dur); t = np.arange(n) / SR
    noise = np.random.randn(n)
    f = 250 + 900 * (t / dur)
    out = np.zeros(n); y = 0.0
    for i in range(n):
        a = min(1.0, f[i] / SR * 2 * math.pi)
        y += a * (noise[i] - y); out[i] = y
    bub = np.sin(2 * np.pi * (300 + 400 * np.sin(2 * np.pi * 7 * t)) * t) * 0.15
    out = out / (np.abs(out).max() + 1e-9) + bub
    return out * env(n, a=0.08, d=0.2, s=0.8, r=0.25) * 0.55


def clink(dur=0.5):
    """Metal lid / bowl clink: short inharmonic ping."""
    n = int(SR * dur); t = np.arange(n) / SR
    x = sum(np.sin(2 * np.pi * f * t) * g for f, g in ((2400, 1.0), (3730, 0.6), (5200, 0.35), (1180, 0.3)))
    x *= np.exp(-t * 14)
    x += np.random.randn(n) * np.exp(-t * 200) * 0.4
    return x / (np.abs(x).max() + 1e-9) * 0.6


def tick(dur=0.06):
    """Soft UI tick: the quiet default for ordinary captions."""
    n = int(SR * dur); t = np.arange(n) / SR
    x = np.sin(2 * np.pi * 1800 * t) * np.exp(-t * 90) + np.random.randn(n) * np.exp(-t * 300) * 0.3
    return x / (np.abs(x).max() + 1e-9) * 0.5


if __name__ == "__main__":
    np.random.seed(7)
    for name, fn in (("sfx_whoosh.wav", whoosh), ("sfx_pop.wav", pop), ("sfx_ding.wav", ding),
                     ("sfx_click.wav", click), ("music_lofi.wav", lofi), ("sfx_cash.wav", cash),
                     ("sfx_beep.wav", beep), ("sfx_thud.wav", thud), ("sfx_riser.wav", riser),
                     ("sfx_chime.wav", chime), ("music_upbeat.wav", upbeat),
                     ("sfx_sizzle.wav", sizzle), ("sfx_pour.wav", pour), ("sfx_clink.wav", clink), ("sfx_tick.wav", tick)):
        save(name, fn())
        print("wrote", name)
