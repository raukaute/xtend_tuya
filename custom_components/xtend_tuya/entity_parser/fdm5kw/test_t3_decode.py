"""Self-check for the QT-08W-T3 DP decoders (sensor.py).

Standalone (no HA import) — mirrors the byte math in the DPCodeSat0*/
DPCodeFlowStaVolume/DPCodeCounterCustom wrappers and asserts it against the
REAL payloads captured live 2026-07-15 (see irrigation-t3-dp-decode.md). Fails
if anyone shifts a byte offset. Run: `python test_t3_decode.py`.
"""
import base64


def battery(b):          # DPCodeSat0BatteryWrapper
    return b[3] & 0x7F if len(b) >= 4 else None


def next_run(b):         # DPCodeSat0NextRunWrapper
    if len(b) < 12:
        return None
    y, mo, d, h, mi = b[7], b[8], b[9], b[10], b[11]
    if y == 0xFF or mo == 0 or mo > 12 or d == 0 or d > 31:
        return None
    return f"20{y:02d}-{mo:02d}-{d:02d} {h:02d}:{mi:02d}:00"


def flow_volume(b):      # DPCodeFlowStaVolumeWrapper
    return int.from_bytes(b[1:5], "big") if len(b) >= 5 else None


def counter_volume(csv):  # DPCodeCounterCustomVolumeWrapper
    p = csv.split(",")
    if len(p) < 5 or int(p[2]) == 65534:
        return None
    return int(p[3])


def demo():
    d = base64.b64decode
    # sat_0 (701): battery 100%, next 2026-07-15 16:00
    sat = d("AAEAZAABABoHDxAAAA==")
    assert battery(sat) == 100, battery(sat)
    assert next_run(sat) == "2026-07-15 16:00:00", next_run(sat)
    # sat_0 charge-flag frame (byte3=0xE4) still = 100%
    assert battery(d("AAEA5AABABoHDg4tAA==")) == 100
    # sat_0 idle frame (ff schedule) -> no next run
    assert next_run(d("AAEAZAEBAP///////w==")) is None
    # flow_sta_0 (701): final frame volume 113 L
    assert flow_volume(d("AAAAAHEAAAJY//////////8A")) == 113
    # flow_sta_0 mid-run frame: 90 L
    assert flow_volume(d("AAAAAFoAAAAADhAAAA4QCgAA")) == 90
    # counter_custom: last run 113 L; aborted (65534) -> None
    assert counter_volume("0,1,600,113,20260714161000") == 113
    assert counter_volume("0,1,65534,9,20260714155958") is None
    print("T3 decode self-check OK")


if __name__ == "__main__":
    demo()
