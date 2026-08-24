"""Self-check for the DP-collapse watchdog trip logic.

Standalone (no Home Assistant import) — mirrors _register_dp_collapse_watchdog
in __init__.py.

Aug 2026 incident series: a sharing-SDK refresh mid-run rebuilt device objects
with the bare 2-DP sharing strategy, collapsing rich OpenAPI DPs fleet-wide
(meter/battery data gone) with no error logged; only an entry reload
recovered. The watchdog baselines devices with rich status (>=8 DPs) at setup
and reloads the entry when >=30% of them (min 3) drop to <=3 DPs.

Run: `python tests/test_dp_collapse_watchdog.py`
"""

COOLDOWN = 3600.0


def baseline_ids(device_map):
    return [dev_id for dev_id, st in device_map.items() if len(st) >= 8]


def should_reload(baseline, device_map, last_reload, now):
    degraded = [
        dev_id
        for dev_id in baseline
        if dev_id in device_map and len(device_map[dev_id]) <= 3
    ]
    if len(degraded) < max(3, int(len(baseline) * 0.3)):
        return False
    if now - last_reload < COOLDOWN:
        return False
    return True


def rich(n):
    return {f"dp{i}": 0 for i in range(n)}


def demo():
    fleet = {f"v{i}": rich(31) for i in range(100)}
    fleet["ghost"] = rich(0)
    fleet["t3"] = rich(4)
    base = baseline_ids(fleet)
    assert len(base) == 100, "thin devices must not enter the baseline"

    # Healthy fleet: no reload.
    assert not should_reload(base, fleet, last_reload=-COOLDOWN, now=0)

    # A couple of flaky devices: no reload.
    partial = dict(fleet)
    for i in range(2):
        partial[f"v{i}"] = rich(2)
    assert not should_reload(base, partial, last_reload=-COOLDOWN, now=0)

    # Fleet-wide 2-DP collapse (the Aug 2026 signature): reload.
    collapsed = {k: rich(2) for k in fleet}
    assert should_reload(base, collapsed, last_reload=-COOLDOWN, now=0)

    # Cooldown suppresses a second reload within the hour...
    assert not should_reload(base, collapsed, last_reload=0, now=1800)
    # ...but not after it.
    assert should_reload(base, collapsed, last_reload=0, now=COOLDOWN + 1)

    # Devices that vanished from the map entirely don't count as degraded.
    gone = {k: v for k, v in fleet.items() if k not in base[:40]}
    assert not should_reload(base, gone, last_reload=-COOLDOWN, now=0)

    # Tiny fleets (< 3 rich devices) never trip: baseline gate.
    tiny = {"a": rich(31), "b": rich(31)}
    assert len(baseline_ids(tiny)) < 3

    print("ok")


if __name__ == "__main__":
    demo()
