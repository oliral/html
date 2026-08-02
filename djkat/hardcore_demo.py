import numpy as np
from scipy.io.wavfile import write

# -------- parameters --------
sr = 44100
seconds = 20
bpm = 178
beat = 60.0 / bpm

n = int(sr * seconds)
t = np.arange(n) / sr
audio = np.zeros(n, dtype=np.float32)

def env(a, d, s, i):
    # simple exponential-ish envelope sampled on indices i (0..len-1)
    x = i / s
    return (1.0 - x) * np.exp(-3.5 * x)

def add_sine(freq, start_s, dur_s, gain, detune_cents=0.0):
    start = int(start_s * sr)
    dur = int(dur_s * sr)
    if start + dur > n:
        dur = n - start
    if dur <= 0:
        return
    tt = np.arange(dur) / sr
    det = 2 ** (detune_cents / 1200)
    f = freq * det
    # short attack/release
    attack = int(0.005 * sr)
    release = int(0.03 * sr)
    envw = np.ones(dur, dtype=np.float32)
    if attack > 0:
        aenv = np.linspace(0, 1, min(attack, dur))
        envw[:len(aenv)] = aenv
    if release > 0:
        r = min(release, dur)
        renv = np.linspace(1, 0, r)
        envw[-r:] *= renv
    wave = np.sin(2*np.pi*f*tt) * envw
    audio[start:start+dur] += gain * wave.astype(np.float32)

def soft_clip(x, drive=1.8):
    y = np.tanh(drive * x) / np.tanh(drive)
    return y

# -------- rhythm grid --------
# 16th notes: 4 per beat
step = beat / 4
num_steps = int(seconds / step)

# base musical bits
key_root = 110.0  # A2-ish
# a hardcore-ish minor-ish progression
modes = [0, 3, 5, 7, 10]  # mixolydian-ish steps (in semitones)
scale = [m for m in modes]

def note_freq(scale_degree, octv=0):
    semis = scale[scale_degree % len(scale)] + 12*octv
    return key_root * (2 ** (semis / 12))

# -------- drums --------
# Kick: thump with pitch drop
kick_shape_len = int(0.09 * sr)
def add_kick(kick_time_s, gain=0.9):
    start = int(kick_time_s * sr)
    if start + kick_shape_len > n:
        return
    tt = np.arange(kick_shape_len) / sr
    # pitch drop
    f0, f1 = 140, 55
    kf = f1 + (f0 - f1) * np.exp(-tt * 18.0)
    # click-ish transient
    transient = np.exp(-tt * 40.0)
    body = np.sin(2*np.pi*kf*tt) * np.exp(-tt * 12.0)
    wave = (0.65 * transient + 0.35 * body) * gain
    audio[start:start+kick_shape_len] += wave.astype(np.float32)

# Snare/Clap-ish: noise burst
sn_len = int(0.06 * sr)
def add_clap(time_s, gain=0.6):
    start = int(time_s * sr)
    if start + sn_len > n:
        return
    tt = np.arange(sn_len) / sr
    # shaped noise
    rng = np.random.RandomState(int(time_s * 1000) + 7)
    noise = rng.uniform(-1, 1, sn_len).astype(np.float32)
    envn = np.exp(-tt * 30.0)
    # slight highpass-ish weighting
    wave = noise * envn
    audio[start:start+sn_len] += gain * wave

# Hi-hats: short metallic noise + very short tone
hat_len = int(0.018 * sr)
def add_hat(time_s, gain=0.25, open_=False):
    start = int(time_s * sr)
    if start + hat_len > n:
        return
    dur = hat_len
    tt = np.arange(dur) / sr
    rng = np.random.RandomState(int(time_s * 1000) + 123)
    noise = rng.uniform(-1, 1, dur).astype(np.float32)
    envh = np.exp(-tt * (60.0 if not open_ else 30.0))
    tone_f = 6000 if not open_ else 4500
    tone = np.sin(2*np.pi*tone_f*tt).astype(np.float32)
    wave = (0.6*noise + 0.4*tone) * envh
    audio[start:start+dur] += gain * wave

# -------- lead/bass --------
lead_gain = 0.18
bass_gain = 0.22

# main loops
phrase_len_steps = 64  # 16 beats = 4 bars in 4/4 at 16th grid
for s in range(num_steps):
    time_s = s * step
    beat_idx = (s // 4)  # beats
    step_in_beat = s % 4

    # Kick pattern (classic hardcore feel)
    # 1) strong on beat 1 and 3-ish, plus extra hits
    if step_in_beat == 0:
        if (beat_idx % 4) == 0:
            add_kick(time_s, 1.0)
        elif (beat_idx % 4) == 2:
            add_kick(time_s, 0.85)
    # extra kicks on 8ths
    if step_in_beat == 2 and (beat_idx % 2 == 1):
        add_kick(time_s, 0.65)

    # Clap/snare on 2 and 4 (and occasional fills)
    if step_in_beat == 0 and (beat_idx % 4) in [1, 3]:
        add_clap(time_s, 0.55)
    if step_in_beat == 3 and (beat_idx % 4) == 2 and (s % 16) == 11:
        add_clap(time_s, 0.35)

    # Hats: 16ths with occasional open hats
    if step_in_beat in [0, 1, 2, 3]:
        open_ = (step_in_beat == 3 and (beat_idx % 4) == 1 and (s % 32) == 27)
        add_hat(time_s, gain=0.22 if not open_ else 0.32, open_=open_)

    # Bass: punchy off-beat stabs
    if step_in_beat == 1 or step_in_beat == 3:
        deg = (beat_idx // 2) % 5
        f = note_freq(deg, octv=-1) * (2 ** (0))  # keep it in a tight low range
        add_sine(f, time_s, dur_s=step*0.9, gain=bass_gain)

    # Lead: fast repeated notes
    if step_in_beat == 0 and (beat_idx % 4) == 0:
        deg = (beat_idx // 4) % 5
        f = note_freq(deg, octv=0) * 2  # higher
        # two quick blips
        add_sine(f, time_s, dur_s=step*0.45, gain=lead_gain, detune_cents=-6)
        add_sine(f*1.0, time_s+step*0.2, dur_s=step*0.45, gain=lead_gain*0.9, detune_cents=+6)

# -------- mix + cleanup --------
audio = soft_clip(audio, drive=1.8)

# normalize to avoid clipping
maxv = np.max(np.abs(audio))
if maxv > 0:
    audio = audio / maxv * 0.98

write("kattengejank_demo.wav", sr, (audio * 32767).astype(np.int16))
print("Klaar: kattengejank_demo.wav")
