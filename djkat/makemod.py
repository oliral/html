import math
import struct

# -------- ProTracker MOD constants --------
SONG_NAME = b"KATTENGEJ"  # 20 bytes, will pad with spaces
SONG_LENGTH_IN_PATTERNS = 32  # order table length (number of patterns to play)
CHANNELS = 4
PATTERN_ROWS = 64
INSTRUMENTS = 31  # classic ProTracker limit

SAMPLE_RATE = 8363  # standard Amiga playback rate; we're just making raw sample bytes
SAMPLE_LENGTH = 64   # bytes per sample (short, keeps file small)
VOLUME = 64

# -------- Helpers --------
def pad20(s: bytes) -> bytes:
    return s[:20].ljust(20, b" ")

def word(x):  # big-endian
    return struct.pack(">H", x)

def make_instrument(name, length_words, finetune=0, volume=VOLUME, loop_start=0, loop_len_words=0):
    # ProTracker instrument header is 30 bytes:
    # 22-byte name, 2 bytes: length (in words), 1 byte finetune, 1 byte volume,
    # 2 bytes: loop start (in words), 2 bytes loop length (in words)
    name = name.encode("ascii", "replace")[:22].ljust(22, b" ")
    length_bytes = length_words * 2
    return (
        name +
        word(length_words) +
        struct.pack("b", finetune)[:1] +  # finetune is signed nibble in spec; we keep it simple
        struct.pack("B", volume) +
        word(loop_start) +
        word(loop_len_words)
    )

def clamp_u8(x):
    return max(0, min(255, x))

def generate_sample_bytes(kind="sine", length_bytes=128, freq=110.0):
    # 8-bit unsigned PCM in MOD files (0..255) where 128 is "zero"
    # We'll generate a short tone-like sample; loop fields are mostly unused here.
    out = bytearray()
    for i in range(length_bytes):
        t = i / SAMPLE_RATE
        if kind == "sine":
            y = math.sin(2 * math.pi * freq * t)
        elif kind == "square":
            y = 1.0 if math.sin(2 * math.pi * freq * t) >= 0 else -1.0
        elif kind == "noise":
            y = (math.sin(1234.567 * (i+1)) + math.sin(987.654 * (i+3))) * 0.5
        else:
            y = 0.0
        # mild "kick" envelope
        env = math.exp(-i / (length_bytes * 0.35))
        amp = 40 * env  # keep it small to avoid harsh clipping in the raw sample
        v = int(128 + y * amp)
        out.append(clamp_u8(v))
    return bytes(out)

def note_to_period(note_num):
    # note_num: 1..36 in classic MOD numbering (C-1..B-3-ish).
    # Use standard ProTracker period table.
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
    # 4 bytes per channel row:
    # byte0: sample hi 4 bits + period high 4 bits
    # byte1: period low 8 bits
    # byte2: sample low 8 bits
    # byte3: effect + effect_param
    # Actually ProTracker encoding:
    # - sample number: 0..31 (4 bits high in first word, 8 bits low in third byte)
    # - period: 12-bit (split)
    smp_hi = (sample >> 4) & 0xF
    smp_lo = sample & 0xF
    per = period & 0xFFF
    b0 = (smp_hi << 4) | ((per >> 8) & 0xF)
    b1 = per & 0xFF
    b2 = (smp_lo << 4)  # lower 4 bits are always 0 in this simplified packing
    b3 = ((effect & 0xF) << 4) | (effect_param & 0xF)
    return bytes([b0, b1, b2, b3])

# -------- Song structure --------
# Order table: list of pattern numbers in play order
song_length = SONG_LENGTH_IN_PATTERNS
order = list(range(song_length))
# Restart marker at end is not present in MOD; it's implicit.

# Create instruments
instrument_names = [
    "Kick", "Snre", "Hat ", "Bass", "Lead", "S1", "S2", "S3", "S4", "S5",
] + [f"I{str(i).zfill(2)}" for i in range(11, INSTRUMENTS+1)]

# 31 instruments => 31*30 bytes headers + sample data
# We'll set all instruments to have SAMPLE_LENGTH bytes each (rounded to words)
length_bytes = 256
length_words = length_bytes // 2
sample_bytes = []

instr_headers = b""
for idx in range(INSTRUMENTS):
    name = instrument_names[idx] if idx < len(instrument_names) else f"I{idx}"
    # Simple palette: different sample "kinds" by instrument index
    kind = ["sine", "square", "noise", "sine", "sine"][idx % 5]
    freq = 55.0 * (2 ** ((idx % 12) / 12))  # varying
    data = generate_sample_bytes(kind=kind, length_bytes=length_bytes, freq=freq)
    sample_bytes.append(data)
    # No loops
    instr_headers += make_instrument(name, length_words=length_words, finetune=0, volume=64, loop_start=0, loop_len_words=0)

# -------- Pattern creation --------
num_patterns = song_length

def make_pattern(pat_index):
    # Pattern data is PATTERN_ROWS * CHANNELS * 4 bytes
    data = bytearray()
    # We'll craft a repeating groove:
    # - kick on row 0, 16, 32, 48 (and some extras)
    # - snare on row 8, 24, 40, 56
    # - hats on many off-rows
    # - bass/lead alternating notes
    for row in range(PATTERN_ROWS):
        for ch in range(CHANNELS):
            # Channel mapping:
            # 0: Kick/Bass
            # 1: Snare/Lead
            # 2: Hats
            # 3: Bass/Lead second voice
            sample = 0
            period = 0
            effect = 0
            effect_param = 0

            # Decide musical row positions
            # 64 rows per pattern; treat 16th grid ~ every 4 rows
            sixteenth = row % 4 == 0
            eighth = row % 8 == 0
            beat = row // 16  # 0..3

            if ch == 0:
                if row % 16 == 0:
                    sample = 1  # Kick
                    period = note_to_period(24)  # around C-2-ish
                    effect = 0x0  # none
                    effect_param = 0
                elif row % 8 == 4 and (row % 16 != 0):
                    sample = 4  # Bass-ish
                    period = note_to_period(28)
                elif row % 16 == 8:
                    sample = 1
                    period = note_to_period(21)

            elif ch == 1:
                if row % 16 == 8:
                    sample = 2  # Snre
                    period = note_to_period(20)
                elif row % 16 == 4 and (pat_index % 2 == 0):
                    sample = 5  # Lead
                    period = note_to_period(24)
                    effect = 0x0
                    effect_param = 0
                elif row % 32 == 30 and (pat_index % 2 == 1):
                    sample = 5
                    period = note_to_period(27)

            elif ch == 2:
                # Hats
                if sixteenth:
                    sample = 3
                    period = note_to_period(36)  # high hat
                elif eighth and (row // 8) % 2 == 1:
                    sample = 3
                    period = note_to_period(33)

            elif ch == 3:
                # Bass line: repeating minor-ish steps
                if row % 4 == 2:
                    sample = 4
                    # vary note by pattern and row
                    base = [22, 24, 26, 27][(row // 4 + pat_index) % 4]
                    period = note_to_period(base)

            # Sample numbers in MOD are 1..31. We'll keep 0 if silent.
            if sample == 0 or period == 0:
                data += b"\x00\x00\x00\x00"
            else:
                # effect simplified: no portamento/tremolo here
                data += build_note(period=period, sample=sample-1, effect=effect, effect_param=effect_param)

    return bytes(data)

patterns = b"".join(make_pattern(p) for p in range(num_patterns))

# -------- Write final MOD --------
# Header:
# 20 bytes song name
# 31*30 bytes instrument headers
# 2 bytes song length
# 1 byte restart position
# 128 bytes order list (ProTracker uses 128 max)
# 'M.K.' etc identifies 4 channels; for 4 channels it's 4 bytes marker.
# Then patterns and sample data follow.
# Marker 'M.K.' expects 4 channels.

header = bytearray()
header += pad20(SONG_NAME)
header += instr_headers
header += bytes([song_length])  # song length byte
header += b"\x00"               # restart position
order_bytes = bytes(order + [0]*(128-len(order)))
header += order_bytes
header += b"M.K."  # 4 channels marker

# Sample data: each sample's bytes, sequential. Lengths in instrument headers determine playback.
smp_data = b"".join(sample_bytes)

mod_bytes = header + patterns + smp_data

with open("kattengejank_protracker.mod", "wb") as f:
    f.write(mod_bytes)

print("Wrote kattengejank_protracker.mod")
