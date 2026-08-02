import math
import struct

# -------- ProTracker MOD constants --------
SONG_NAME = b"KATTENGEJ"  # 20 bytes, will pad with spaces
SONG_LENGTH_IN_PATTERNS = 32  # order table length (number of patterns to play)
CHANNELS = 4
PATTERN_ROWS = 64
INSTRUMENTS = 31  # classic ProTracker limit

SAMPLE_RATE = 8363  # standard Amiga playback rate; used for synthetic sample generation
SAMPLE_LENGTH = 64   # unused (kept from earlier version)
VOLUME = 64

# -------- Helpers --------
def pad20(s: bytes) -> bytes:
    return s[:20].ljust(20, b" ")

def word(x):  # big-endian
    return struct.pack(">H", x)

def make_instrument(name, length_words, finetune=0, volume=VOLUME, loop_start=0, loop_len_words=0):
    # ProTracker instrument header is 30 bytes:
    # 22-byte name, 2 bytes length (in words), 1 byte finetune, 1 byte volume,
    # 2 bytes loop start (in words), 2 bytes loop length (in words)
    name = name.encode("ascii", "replace")[:22].ljust(22, b" ")
    return (
        name +
        word(length_words) +
        struct.pack("b", finetune)[:1] +  # keep as signed byte
        struct.pack("B", volume) +
        word(loop_start) +
        word(loop_len_words)
    )

def clamp_u8(x):
    return max(0, min(255, x))

def generate_sample_bytes(kind="piano", length_bytes=512, freq=110.0):
    """
    Generate 8-bit unsigned PCM sample data for MOD:
    - value range 0..255
    - 128 is nominal zero
    """
    out = bytearray()

    for i in range(length_bytes):
        t = i / SAMPLE_RATE

        if kind == "bass":
            # more harmonic + quick decay + gentle saturation
            base = math.sin(2 * math.pi * freq * t)
            second = math.sin(2 * math.pi * (freq * 2.0) * t) * 0.40
            third = math.sin(2 * math.pi * (freq * 3.0) * t) * 0.22
            fifth = math.sin(2 * math.pi * (freq * 5.0) * t) * 0.12
            env = math.exp(-t * 7.0)  # fast decay
            y = (base + second + third + fifth) * env
            y = math.tanh(2.2 * y) * 0.95

        elif kind == "harp":
            # plucked-string-ish: fast attack, metallic body, faster decay
            attack = 1.0 - math.exp(-t * 120.0)
            env = math.exp(-t * 14.0)

            # “string body” partials
            p1 = math.sin(2 * math.pi * freq * t) * 0.70
            p2 = math.sin(2 * math.pi * (freq * 2.01) * t) * 0.22
            p3 = math.sin(2 * math.pi * (freq * 3.97) * t) * 0.10

            # pseudo-noise excitation
            n = math.sin((i + 1) * 12.9898) * 43758.5453
            noise = (n - math.floor(n)) * 2.0 - 1.0

            early = math.exp(-t * 220.0)  # noise mostly at start
            y = (p1 + p2 + p3) * env
            y += noise * early * 0.35
            y = math.tanh(2.0 * y) * 0.90

        elif kind == "piano":
            # piano-ish: hammer noise early + inharmonic-ish partials + slower decay
            hammer_env = math.exp(-t * 220.0)  # very short
            body_env = math.exp(-t * 6.8)
            attack_env = 1.0 - math.exp(-t * 380.0)

            # slightly inharmonic partials
            p1 = math.sin(2 * math.pi * freq * t) * 0.60
            p2 = math.sin(2 * math.pi * (freq * 2.03) * t) * 0.28
            p3 = math.sin(2 * math.pi * (freq * 4.01) * t) * 0.14

            # strike noise (brief)
            n = math.sin((i + 3) * 78.233) * 19341.167
            noise = (n - math.floor(n)) * 2.0 - 1.0

            y = (p1 + p2 + p3) * body_env * attack_env
            y += noise * hammer_env * 0.55
            y = math.tanh(2.3 * y) * 0.92

        else:
            # fallback
            y = math.sin(2 * math.pi * freq * t) * math.exp(-t * 6.0)

        # convert [-1..1] to unsigned 8-bit where 128 is zero
        amp = 42
        v = int(128 + y * amp)
        v = clamp_u8(v)
        out.append(v)

    return bytes(out)

def note_to_period(note_num):
    """
    Convert MOD note number (1..36 in classic ProTracker numbering) to period
    using the classic ProTracker period table.
    """
    period_table = [
        0,  # 0 unused
        1712, 1616, 1524, 1440, 1356, 1280, 1208, 1140, 1076, 1016, 960, 907,
        856, 808, 762, 720, 678, 640, 604, 570, 538, 508, 480, 453,
        428, 404, 381, 360, 339, 320, 302, 285, 269, 254, 240, 226,
        214, 202, 190
    ]
    if note_num < 1 or note_num >= len(period_table):
        return 0
    return period_table[note_num]

def build_note(period, sample, effect=0, effect_param=0):
    """
    Build 4 bytes for a ProTracker MOD row:
    byte0: sample high 4 bits + period high 4 bits
    byte1: period low 8 bits
    byte2: sample low 4 bits shifted to high nibble
    byte3: effect + effect_param
    Note: This is the same simplified packing style as your original script.
    """
    smp_hi = (sample >> 4) & 0xF
    smp_lo = sample & 0xF
    per = period & 0xFFF

    b0 = (smp_hi << 4) | ((per >> 8) & 0xF)
    b1 = per & 0xFF
    b2 = (smp_lo << 4)  # lower 4 bits always 0 in this simplified packing
    b3 = ((effect & 0xF) << 4) | (effect_param & 0xF)
    return bytes([b0, b1, b2, b3])

# -------- Song structure --------
song_length = SONG_LENGTH_IN_PATTERNS
order = list(range(song_length))

# Create instruments
instrument_names = [
    "Kick", "Snre", "Hat ", "Bass", "Lead", "S1", "S2", "S3", "S4", "S5",
] + [f"I{str(i).zfill(2)}" for i in range(11, INSTRUMENTS + 1)]

# More realistic tails: make samples longer
length_bytes = 512
length_words = length_bytes // 2

sample_bytes = []
instr_headers = b""

# Instrument-to-kind mapping
kinds = {
    0: "bass",    # Kick instrument sample body
    1: "piano",   # Snare-ish: tonal strike
    2: "harp",    # Hat/pluck-ish
    3: "bass",    # Bass
    4: "piano",   # Lead
    5: "harp",
    6: "piano",
    7: "bass",
    8: "harp",
    9: "piano",
}

for idx in range(INSTRUMENTS):
    name = instrument_names[idx] if idx < len(instrument_names) else f"I{idx}"
    kind = kinds.get(idx, "piano")
    freq = 55.0 * (2 ** ((idx % 12) / 12))  # vary per instrument

    data = generate_sample_bytes(kind=kind, length_bytes=length_bytes, freq=freq)
    sample_bytes.append(data)

    # No loops (loop fields left zero)
    instr_headers += make_instrument(
        name,
        length_words=length_words,
        finetune=0,
        volume=64,
        loop_start=0,
        loop_len_words=0
    )

# -------- Pattern creation --------
num_patterns = song_length

def make_pattern(pat_index):
    data = bytearray()

    for row in range(PATTERN_ROWS):
        for ch in range(CHANNELS):
            sample = 0
            period = 0
            effect = 0
            effect_param = 0

            sixteenth = row % 4 == 0
            eighth = row % 8 == 0

            if ch == 0:
                if row % 16 == 0:
                    sample = 1  # Kick instrument number 1
                    period = note_to_period(24)  # low tone
                elif row % 8 == 4 and (row % 16 != 0):
                    sample = 4  # Bass-ish instrument number 4
                    period = note_to_period(28)
                elif row % 16 == 8:
                    sample = 1
                    period = note_to_period(21)

            elif ch == 1:
                if row % 16 == 8:
                    sample = 2  # Snare/strike instrument number 2
                    period = note_to_period(20)
                elif row % 16 == 4 and (pat_index % 2 == 0):
                    sample = 5  # Lead instrument number 5
                    period = note_to_period(24)
                elif row % 32 == 30 and (pat_index % 2 == 1):
                    sample = 5
                    period = note_to_period(27)

            elif ch == 2:
                if sixteenth:
                    sample = 3  # Hat/pluck instrument number 3
                    period = note_to_period(36)
                elif eighth and (row // 8) % 2 == 1:
                    sample = 3
                    period = note_to_period(33)

            elif ch == 3:
                if row % 4 == 2:
                    sample = 4  # Bass/low voice instrument number 4
                    base = [22, 24, 26, 27][(row // 4 + pat_index) % 4]
                    period = note_to_period(base)

            if sample == 0 or period == 0:
                data += b"\x00\x00\x00\x00"
            else:
                # sample in MOD rows is 1..31, so pass sample-1 into our simplified packer
                data += build_note(period=period, sample=sample - 1, effect=effect, effect_param=effect_param)

    return bytes(data)

patterns = b"".join(make_pattern(p) for p in range(num_patterns))

# -------- Write final MOD --------
header = bytearray()
header += pad20(SONG_NAME)
header += instr_headers
header += bytes([song_length])  # song length byte
header += b"\x00"               # restart position (0)
order_bytes = bytes(order + [0] * (128 - len(order)))
header += order_bytes
header += b"M.K."  # 4 channels marker

smp_data = b"".join(sample_bytes)
mod_bytes = header + patterns + smp_data

with open("kattengejank_protracker.mod", "wb") as f:
    f.write(mod_bytes)

print("Wrote kattengejank_protracker.mod")
