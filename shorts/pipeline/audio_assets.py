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


def ensure(name):
    """Synthesize a named asset on demand (keeps big wavs out of git)."""
    p = OUT / name
    if not p.exists():
        np.random.seed(7)
        fn = {"music_pop.wav": pop_beat, "music_lofi.wav": lofi}.get(name)
        if fn is None:
            raise FileNotFoundError(name)
        save(name, fn())
    return p


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


def _onepole(x, cutoff):
    """Vectorised-ish one-pole low-pass (recursive, but cheap enough for a 20s bed)."""
    a = min(1.0, cutoff / SR * 2 * math.pi)
    y = np.empty_like(x); acc = 0.0
    for i in range(len(x)):
        acc += a * (x[i] - acc); y[i] = acc
    return y


def pop_beat(bars=8, bpm=108):
    """Upbeat, clean K-beauty style bed: four-on-the-floor kick, clap on 2/4, swung hats,
    sub bass, plucky arpeggio and a side-chained pad. C-G-Am-F, 2 bars per chord, loopable."""
    beat = 60 / bpm
    n = int(SR * beat * 4 * bars); t = np.arange(n) / SR
    out = np.zeros(n)
    chords = [[261.6, 329.6, 392.0, 523.3], [196.0, 246.9, 293.7, 392.0],
              [220.0, 261.6, 329.6, 440.0], [174.6, 220.0, 261.6, 349.2]]
    roots = [130.8, 98.0, 110.0, 87.3]
    pad = np.zeros(n); pluck = np.zeros(n); bass = np.zeros(n)
    for ci, ch in enumerate(chords):
        s0 = int(ci * 2 * 4 * beat * SR); s1 = min(n, int((ci + 1) * 2 * 4 * beat * SR))
        tt = np.arange(s1 - s0) / SR
        pad[s0:s1] += sum(np.sin(2 * np.pi * f * tt) + 0.3 * np.sin(2 * np.pi * f * 2 * tt + 0.5) for f in ch) * 0.06
        # plucky 8th-note arpeggio
        for k in range(16):
            ps = s0 + int(k * beat / 2 * SR)
            if ps >= s1:
                break
            m = int(SR * 0.22); tt2 = np.arange(m) / SR
            f = ch[k % 4] * (2 if k % 8 >= 4 else 1)
            note = (np.sin(2 * np.pi * f * tt2) + 0.5 * np.sin(2 * np.pi * 2 * f * tt2)) * np.exp(-tt2 * 14) * 0.22
            e = min(m, n - ps); pluck[ps:ps + e] += note[:e]
        # bass: root on 1 and the "and" of 2 and 4
        for b in range(8):
            for off in (0.0, 0.5):
                bs = s0 + int((b + off) * beat * SR)
                if off == 0.5 and b % 2 == 0:
                    continue
                m = int(SR * 0.3); tt2 = np.arange(m) / SR
                nb = np.sin(2 * np.pi * roots[ci] * tt2) * np.exp(-tt2 * 7) * 0.5
                e = min(m, max(0, n - bs)); bass[bs:bs + e] += nb[:e]
    def kick():
        m = int(SR * 0.22); tt = np.arange(m) / SR
        return np.sin(2 * np.pi * (150 * np.exp(-tt * 22) + 48) * tt) * np.exp(-tt * 11) * 1.0
    def clap():
        m = int(SR * 0.16); tt = np.arange(m) / SR
        x = np.random.randn(m) * np.exp(-tt * 28)
        return _onepole(x, 1800) * 2.2 * 0.5
    def hat(open_=False):
        m = int(SR * (0.16 if open_ else 0.05)); x = np.random.randn(m) * np.exp(-np.arange(m) / SR * (18 if open_ else 80))
        return (x - _onepole(x, 6000)) * 0.35
    drums = np.zeros(n); sc = np.ones(n)
    for b in range(bars * 4):
        pos = int(b * beat * SR)
        k = kick(); e = min(len(k), n - pos); drums[pos:pos + e] += k[:e]
        m = int(SR * 0.25); env = np.linspace(0.25, 1.0, m); e2 = min(m, n - pos); sc[pos:pos + e2] *= env[:e2]
        if b % 2 == 1:
            c = clap(); e = min(len(c), n - pos); drums[pos:pos + e] += c[:e]
        for h in range(2):
            hp = pos + int((h * 0.5 + (0.06 if h else 0)) * beat * SR)
            if hp < n:
                hh = hat(open_=(h == 1 and b % 2 == 1)); e = min(len(hh), n - hp); drums[hp:hp + e] += hh[:e]
    mix = _onepole(pad, 1400) * sc + pluck * 0.9 + bass + drums * 0.8
    # gentle soft-clip "glue"
    mix = np.tanh(mix * 1.4) / np.tanh(1.4)
    return mix / (np.abs(mix).max() + 1e-9) * 0.85


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


if __name__ == "__main__":
    np.random.seed(7)
    for name, fn in (("sfx_whoosh.wav", whoosh), ("sfx_pop.wav", pop), ("sfx_ding.wav", ding),
                     ("sfx_click.wav", click), ("music_lofi.wav", lofi), ("sfx_cash.wav", cash),
                     ("sfx_beep.wav", beep), ("sfx_thud.wav", thud), ("sfx_riser.wav", riser),
                     ("sfx_chime.wav", chime), ("music_pop.wav", pop_beat)):
        save(name, fn())
        print("wrote", name)
