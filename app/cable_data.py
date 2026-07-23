"""AS/NZS 3008.1.1 reference data for the cable-sizing calculator.

============================================================================
⚠  DRAFT VALUES — VERIFY EVERY NUMBER against your licensed copy of
   AS/NZS 3008.1.1 before relying on ANY result from this calculator.
============================================================================
Cable sizing is safety-critical: a single wrong value here can undersize a
cable and create a fire or shock risk. These figures are transcribed/estimated
as a working STARTING POINT for VoltPro's own internal use — they are NOT an
authoritative reproduction of the Standard, and they cover only a limited set
of common cases. The calculator is a GUIDE ONLY; a licensed electrician must
confirm the final design against AS/NZS 3008.

Where an installation method or conductor has no data loaded below, the
calculator says so and does NOT guess — those cells still need to be entered
from AS/NZS 3008 (the table each method maps to is noted in METHOD_TABLE_REF).

Cable sizes (mm²) covered: 1.5 – 300.
"""

SIZES = [1.5, 2.5, 4, 6, 10, 16, 25, 35, 50, 70, 95, 120, 150, 185, 240, 300]

# Selectable nominal voltages (single-phase 230/240, three-phase 400/415).
VOLTAGES = [230, 240, 400, 415]

CONDUCTORS = [("cu", "Copper"), ("al", "Aluminium")]

INSULATIONS = [
    ("V-90", "V-90 (PVC, 90°C)"),
    ("V-75", "V-75 (Traditional PVC, 75°C)"),
    ("X-90", "X-90 (XLPE, 90°C)"),
]

# Installation methods — the standard AS/NZS 3008 categories. METHOD_TABLE_REF
# notes which tables each maps to, so any "data not loaded" method is easy to fill.
INSTALL_METHODS = [
    ("conduit_wall", "Enclosed in conduit / in a wall"),
    ("conduit_air", "Enclosed in conduit, in air / on a surface"),
    ("clipped", "Unenclosed, clipped to a surface (touching)"),
    ("spaced", "Unenclosed, spaced from surface / in free air"),
    ("tray", "On a perforated cable tray (touching)"),
    ("buried", "Buried direct in the ground"),
    ("underground_conduit", "Underground, in a buried conduit / duct"),
]

METHOD_TABLE_REF = {
    "conduit_wall": "AS/NZS 3008.1.1 Tables 4–9 (enclosed)",
    "conduit_air": "AS/NZS 3008.1.1 Tables 4–9 (enclosed, in air)",
    "clipped": "AS/NZS 3008.1.1 Tables 4–9 (unenclosed, touching)",
    "spaced": "AS/NZS 3008.1.1 Tables 10–13 (spaced / free air)",
    "tray": "AS/NZS 3008.1.1 Tables 10–13 (cable tray)",
    "buried": "AS/NZS 3008.1.1 Tables 5 & 13 (buried direct)",
    "underground_conduit": "AS/NZS 3008.1.1 Tables 5 & 13 (underground conduit)",
}

# ---------------------------------------------------------------------------
# CURRENT-CARRYING CAPACITY  (amps)  — AS/NZS 3008.1.1:2017 Tables 4–15
# Base ambient: 40 °C air / 25 °C soil. Copper conductors. Keyed by
# (conductor, insulation, install_method) -> {size_mm²: amps}.
# DRAFT — populated for the common methods only; verify every value.
# ---------------------------------------------------------------------------
CURRENT_RATINGS = {
    ("cu", "V-90", "conduit_wall"): {
        1.5: 15, 2.5: 21, 4: 28, 6: 36, 10: 50, 16: 66, 25: 88, 35: 109,
        50: 131, 70: 167, 95: 202, 120: 233, 150: 268, 185: 306, 240: 360, 300: 415,
    },
    ("cu", "V-90", "clipped"): {
        1.5: 19, 2.5: 26, 4: 35, 6: 45, 10: 62, 16: 83, 25: 110, 35: 137,
        50: 167, 70: 213, 95: 258, 120: 299, 150: 344, 185: 392, 240: 461, 300: 530,
    },
    ("cu", "V-90", "buried"): {
        1.5: 27, 2.5: 36, 4: 46, 6: 57, 10: 76, 16: 98, 25: 127, 35: 153,
        50: 182, 70: 223, 95: 265, 120: 300, 150: 338, 185: 379, 240: 435, 300: 487,
    },
    ("cu", "X-90", "conduit_wall"): {
        1.5: 18, 2.5: 25, 4: 33, 6: 42, 10: 58, 16: 77, 25: 102, 35: 126,
        50: 153, 70: 194, 95: 234, 120: 271, 150: 311, 185: 354, 240: 417, 300: 481,
    },
    ("cu", "X-90", "clipped"): {
        1.5: 23, 2.5: 31, 4: 42, 6: 54, 10: 75, 16: 100, 25: 133, 35: 164,
        50: 200, 70: 254, 95: 308, 120: 357, 150: 411, 185: 469, 240: 552, 300: 634,
    },
    ("cu", "X-90", "buried"): {
        1.5: 31, 2.5: 41, 4: 53, 6: 66, 10: 87, 16: 113, 25: 146, 35: 176,
        50: 209, 70: 256, 95: 305, 120: 346, 150: 390, 185: 438, 240: 503, 300: 564,
    },
}

# V-75 (traditional 75°C PVC): DRAFT estimate = 0.85 × the V-90 rating, from the
# temperature-rise ratio (75°C vs 90°C conductor limit over a 40°C ambient).
# This is a DERIVED starting point, NOT a transcribed AS/NZS 3008 table — VERIFY.
_V75_FACTOR = 0.85
for (_cond, _ins, _meth), _tbl in list(CURRENT_RATINGS.items()):
    if _ins == "V-90":
        CURRENT_RATINGS[(_cond, "V-75", _meth)] = {s: round(a * _V75_FACTOR) for s, a in _tbl.items()}

# ---------------------------------------------------------------------------
# VOLTAGE DROP  (mV per amp per metre)  — AS/NZS 3008.1.1:2017 Tables 40–42
# a.c. values at 75 °C. {conductor: {size: {"single": 1φ, "three": 3φ}}}.
# ---------------------------------------------------------------------------
VOLTAGE_DROP_MVAM = {
    "cu": {
        1.5: {"single": 30.0, "three": 26.0},
        2.5: {"single": 18.5, "three": 16.0},
        4:   {"single": 11.5, "three": 9.9},
        6:   {"single": 7.7,  "three": 6.7},
        10:  {"single": 4.6,  "three": 4.0},
        16:  {"single": 2.9,  "three": 2.5},
        25:  {"single": 1.85, "three": 1.60},
        35:  {"single": 1.35, "three": 1.15},
        50:  {"single": 1.00, "three": 0.87},
        70:  {"single": 0.70, "three": 0.61},
        95:  {"single": 0.53, "three": 0.46},
        120: {"single": 0.43, "three": 0.37},
        150: {"single": 0.36, "three": 0.31},
        185: {"single": 0.30, "three": 0.26},
        240: {"single": 0.24, "three": 0.21},
        300: {"single": 0.21, "three": 0.18},
    },
    "al": {
        16:  {"single": 4.7,  "three": 4.1},
        25:  {"single": 3.0,  "three": 2.6},
        35:  {"single": 2.2,  "three": 1.9},
        50:  {"single": 1.6,  "three": 1.4},
        70:  {"single": 1.15, "three": 1.00},
        95:  {"single": 0.85, "three": 0.74},
        120: {"single": 0.68, "three": 0.59},
        150: {"single": 0.56, "three": 0.48},
        185: {"single": 0.46, "three": 0.40},
        240: {"single": 0.37, "three": 0.32},
        300: {"single": 0.31, "three": 0.27},
    },
}

# ---------------------------------------------------------------------------
# GROUPING / BUNCHING DERATING  — AS/NZS 3008.1.1:2017 Tables 22–25
# Multiplier for the number of circuits grouped together (touching).
# ---------------------------------------------------------------------------
GROUP_DERATING = {1: 1.00, 2: 0.80, 3: 0.70, 4: 0.65, 5: 0.60, 6: 0.57, 7: 0.54, 8: 0.52, 9: 0.50}


def group_factor(circuits):
    if circuits <= 1:
        return 1.0
    keys = sorted(GROUP_DERATING.keys())
    if circuits >= keys[-1]:
        return GROUP_DERATING[keys[-1]]
    return GROUP_DERATING[circuits]


def has_current_data(conductor, insulation, method):
    return (conductor, insulation, method) in CURRENT_RATINGS
