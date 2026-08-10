"""Self-check for cross-entry device ownership arbitration.

Standalone (no Home Assistant import) — mirrors MultiManager.claim_device and
MultiManager.release_devices in multi_manager/multi_manager.py.

The case that matters: one physical valve reaches two config entries at once,
entry A through an OpenAPI project and entry B through the SmartLife sharing
account it was shared into. Observed 2026-08-10 with RT Veggies 2 (708),
device bf423dd3ea314df3bfjkdk, held by both the solar-valves and
simon.stuertz hubs. Without arbitration both entries build entities with the
same `tuya.<device_id><dpcode>` unique IDs, and Home Assistant logs an error
and drops a copy for each one — ~1600 per setup attempt, on every retry.

Run: `python tests/test_device_ownership.py`
"""

VALVE = "bf423dd3ea314df3bfjkdk"


class FakeManager:
    """Mirror of the claim/release logic, with a fake entry registry."""

    device_owner: dict = {}

    def __init__(self, entry_id, live_entries):
        self.entry_id = entry_id
        self.live_entries = live_entries  # set of entry_ids still configured

    def claim_device(self, device_id):
        owner = FakeManager.device_owner.get(device_id)
        if owner is not None and owner != self.entry_id:
            if owner in self.live_entries:
                return False
        FakeManager.device_owner[device_id] = self.entry_id
        return True

    def release_devices(self):
        for device_id in [
            d for d, o in FakeManager.device_owner.items() if o == self.entry_id
        ]:
            del FakeManager.device_owner[device_id]


def setup():
    FakeManager.device_owner = {}
    live = {"solar", "simon"}
    return FakeManager("solar", live), FakeManager("simon", live), live


def test_first_entry_claims_second_is_refused():
    solar, simon, _ = setup()
    assert solar.claim_device(VALVE) is True
    assert simon.claim_device(VALVE) is False


def test_owner_may_reclaim_its_own_device():
    solar, _, _ = setup()
    assert solar.claim_device(VALVE) is True
    # A reload re-runs update_master_device_map; the owner must not lock itself out.
    assert solar.claim_device(VALVE) is True


def test_release_frees_the_device_for_the_other_entry():
    solar, simon, _ = setup()
    solar.claim_device(VALVE)
    solar.release_devices()
    assert simon.claim_device(VALVE) is True


def test_claim_of_a_removed_entry_is_not_honoured():
    solar, simon, live = setup()
    solar.claim_device(VALVE)
    # Entry deleted without unloading cleanly — its claim must not strand the device.
    live.discard("solar")
    assert simon.claim_device(VALVE) is True
    assert FakeManager.device_owner[VALVE] == "simon"


def test_release_only_touches_own_claims():
    solar, simon, _ = setup()
    solar.claim_device("device-a")
    simon.claim_device("device-b")
    solar.release_devices()
    assert "device-a" not in FakeManager.device_owner
    assert FakeManager.device_owner["device-b"] == "simon"


def test_unrelated_devices_are_unaffected():
    solar, simon, _ = setup()
    assert solar.claim_device("only-in-solar") is True
    assert simon.claim_device("only-in-simon") is True


if __name__ == "__main__":
    for name, test in sorted(globals().items()):
        if name.startswith("test_") and callable(test):
            test()
            print(f"ok  {name}")
    print("all passed")
