"""Sampler must capture the main thread's stack while it burns CPU.

Standalone: python3 tests/test_stall_sampler.py
Exercises _run directly (short interval, tmp file) — no HA needed.
"""

import os
import sys
import tempfile
import threading
import time

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

try:
    from custom_components.xtend_tuya.multi_manager.shared.debug import (
        stall_sampler,
    )
except ImportError as exc:
    print(f"SKIP: needs an env with homeassistant installed ({exc})")
    sys.exit(0)

stall_sampler.SAMPLE_INTERVAL = 0.05
stall_sampler.MAX_RUNTIME = 2.0

path = tempfile.mktemp(suffix=".log")
main_id = threading.get_ident()
t = threading.Thread(target=stall_sampler._run, args=(path, main_id), daemon=True)
t.start()


def burn_marker_function():
    end = time.time() + 1.0
    x = 0
    while time.time() < end:
        x += 1
    return x


burn_marker_function()
t.join(timeout=5)

text = open(path).read()
os.unlink(path)

assert "sampler start" in text, text[:200]
assert "burn_marker_function" in text, "burn stack not captured:\n" + text[:2000]
assert "sampler done" in text
print("ok: sampler captured burn_marker_function stack")
