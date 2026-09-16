#!/usr/bin/env python3
"""
One-off: synthesize a short, upbeat instrumental loop for the podcast's
background bed -- something like the energetic synth beat under a BBC
Newsbeat bulletin. Everything here is generated from scratch with numpy
(sine/saw oscillators + envelopes), so it's 100% original and free to use;
no royalty-free-sample-site licensing to worry about.

Run once: uv run python make_music.py
Writes assets/background.wav, which generate_podcast.py tiles and mixes
under the narration every day.
"""

from pathlib import Path

import numpy as np
from scipy.io import wavfile

SR = 44100
BPM = 128
BEAT = 60.0 / BPM
BAR = BEAT * 4
BARS = 8  # one loop = 8 bars (~15s at 128 BPM), tiled to fit each episode
OUT = Path(__file__).parent / "assets" / "background.wav"


def env_exp(n, decay):
    """Exponential decay envelope, n samples long."""
    t = np.arange(n) / SR
    return np.exp(-t * decay)


def sine(freq, n, phase=0.0):
    t = np.arange(n) / SR
    return np.sin(2 * np.pi * freq * t + phase)


def saw(freq, n):
    t = np.arange(n) / SR
    return 2 * (t * freq - np.floor(0.5 + t * freq))


def kick(n_total, pos_sec, amp=0.9):
    dur = 0.18
    n = int(dur * SR)
    t = np.arange(n) / SR
    freq = 150 * np.exp(-t * 28) + 45  # pitch sweep down, classic synth kick
    click = np.sin(2 * np.pi * freq * t)
    body = click * np.exp(-t * 18)
    out = np.zeros(n_total)
    start = int(pos_sec * SR)
    end = min(start + n, n_total)
    out[start:end] += (amp * body[: end - start])
    return out


def hihat(n_total, pos_sec, amp=0.18):
    dur = 0.05
    n = int(dur * SR)
    noise = np.random.default_rng(int(pos_sec * 1000)).standard_normal(n)
    # crude high-pass: difference the signal to remove low-frequency rumble
    noise = np.diff(noise, prepend=0)
    body = noise * np.exp(-np.arange(n) / SR * 90)
    out = np.zeros(n_total)
    start = int(pos_sec * SR)
    end = min(start + n, n_total)
    out[start:end] += (amp * body[: end - start])
    return out


def pluck_note(freq, dur, amp=0.22):
    n = int(dur * SR)
    tone = 0.7 * sine(freq, n) + 0.3 * sine(freq * 2, n)
    return amp * tone * env_exp(n, 9)


def bass_note(freq, dur, amp=0.32):
    n = int(dur * SR)
    tone = saw(freq, n)
    # soft low-pass-ish smoothing via a short moving average
    kernel = np.ones(6) / 6
    tone = np.convolve(tone, kernel, mode="same")
    return amp * tone * env_exp(n, 6)


def pad_chord(freqs, dur, amp=0.10):
    """Soft, continuously-held chord -- fills the gaps between the percussive
    hits so the loop reads as a bed of music rather than sparse clicks."""
    n = int(dur * SR)
    tone = sum(sine(f, n) for f in freqs) / len(freqs)
    attack = min(int(0.35 * SR), n // 3)
    release = min(int(0.5 * SR), n // 3)
    env = np.ones(n)
    env[:attack] = np.linspace(0, 1, attack)
    env[-release:] = np.linspace(1, 0, release)
    return amp * tone * env


def place(buf, sound, pos_sec):
    start = int(pos_sec * SR)
    end = min(start + len(sound), len(buf))
    if end > start:
        buf[start:end] += sound[: end - start]


def main():
    n_total = int(BARS * BAR * SR) + SR  # a little tail room
    buf = np.zeros(n_total)

    # Bright C-major progression: C - G - Am - F, two bars each (8 bars total)
    chords = [
        (261.63, 329.63, 392.00),  # C major
        (196.00, 246.94, 392.00),  # G major (voiced under C for a lift)
        (220.00, 261.63, 329.63),  # A minor
        (174.61, 220.00, 261.63),  # F major
    ]
    bass_roots = [130.81, 98.00, 110.00, 87.31]  # C2/G2/A2/F2-ish

    for bar in range(BARS):
        bar_start = bar * BAR
        chord = chords[(bar // 2) % len(chords)]
        root = bass_roots[(bar // 2) % len(bass_roots)]

        # Soft sustained pad, one hold per bar, so there's always some tone
        # under the percussion instead of silence between transients.
        place(buf, pad_chord(chord, BAR), bar_start)

        # Four-on-the-floor kick on every beat.
        for b in range(4):
            place(buf, kick(n_total, bar_start + b * BEAT), 0)

        # Off-beat hi-hats (the "and" of each beat) for a driving feel.
        for b in range(4):
            place(buf, hihat(n_total, bar_start + b * BEAT + BEAT / 2), 0)

        # Syncopated bass pulse: root - root - fifth-up - root.
        bass_pattern = [0, 0.75, 1.5, 2.5]
        for off in bass_pattern:
            place(buf, bass_note(root, BEAT * 0.7), bar_start + off * BEAT)

        # Bright plucked 8th-note arpeggio over the chord tones.
        arp_notes = list(chord) + [chord[0] * 2]
        for i in range(8):
            freq = arp_notes[i % len(arp_notes)]
            place(buf, pluck_note(freq, BEAT * 0.45), bar_start + i * (BEAT / 2))

    # Normalize to a sensible peak so mixing later has headroom.
    peak = np.max(np.abs(buf)) or 1.0
    buf = buf / peak * 0.85

    # Short fade in/out so the loop tiles without a click at the seam.
    fade_n = int(0.01 * SR)
    fade = np.linspace(0, 1, fade_n)
    buf[:fade_n] *= fade
    buf[-fade_n:] *= fade[::-1]

    # Trim to an exact whole-bar length for seamless looping.
    loop_len = int(BARS * BAR * SR)
    buf = buf[:loop_len]

    stereo = np.stack([buf, buf], axis=1)
    pcm = np.clip(stereo * 32767, -32768, 32767).astype(np.int16)

    OUT.parent.mkdir(parents=True, exist_ok=True)
    wavfile.write(OUT, SR, pcm)
    print(f"Wrote {OUT} ({loop_len / SR:.1f}s loop @ {BPM} BPM)")


if __name__ == "__main__":
    main()
