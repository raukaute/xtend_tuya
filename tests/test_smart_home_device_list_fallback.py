"""Self-check for the smart-home device list fallback.

Standalone (no Home Assistant import) — mirrors _fetch_smart_home_device_list
in multi_manager/managers/tuya_iot/xt_tuya_iot_manager.py.

/v1.0/users/<uid>/devices started answering 1106 "permission deny" fleet-wide
in Aug 2026 (verified on three separate projects on 2026-08-18), which
silently emptied the OpenAPI device map and dropped every valve to the 2-DP
sharing subset. The fallback walks /v1.0/iot-01/associated-users/devices,
paged by last_row_key.

Run: `python tests/test_smart_home_device_list_fallback.py`
"""


def fetch_smart_home_device_list(api):
    """Mirror of XTIOTDeviceManager._fetch_smart_home_device_list."""
    response = api.get("/v1.0/users/uid/devices")
    if response.get("success"):
        return response["result"]
    devices = []
    last_row_key = ""
    while True:
        params = {"size": 100}
        if last_row_key:
            params["last_row_key"] = last_row_key
        response = api.get("/v1.0/iot-01/associated-users/devices", params)
        if not response.get("success"):
            break
        result = response["result"]
        devices.extend(result.get("devices") or [])
        last_row_key = result.get("last_row_key") or ""
        if not result.get("has_more") or not last_row_key:
            break
    return devices


PERMISSION_DENY = {"code": 1106, "msg": "permission deny", "success": False}


class StubApi:
    def __init__(self, responses):
        self.responses = list(responses)
        self.calls = []

    def get(self, path, params=None):
        self.calls.append((path, params))
        return self.responses.pop(0)


def page(ids, has_more, last_row_key=""):
    return {
        "success": True,
        "result": {
            "devices": [{"id": i} for i in ids],
            "has_more": has_more,
            "last_row_key": last_row_key,
            "total": 105,
        },
    }


def test_old_endpoint_still_works():
    api = StubApi([{"success": True, "result": [{"id": "a"}]}])
    assert fetch_smart_home_device_list(api) == [{"id": "a"}]
    assert len(api.calls) == 1


def test_fallback_pages_until_done():
    api = StubApi(
        [
            PERMISSION_DENY,
            page(["a", "b"], has_more=True, last_row_key="K1"),
            page(["c"], has_more=False),
        ]
    )
    devices = fetch_smart_home_device_list(api)
    assert [d["id"] for d in devices] == ["a", "b", "c"]
    # first fallback page carries no last_row_key, second carries the cursor
    assert api.calls[1] == ("/v1.0/iot-01/associated-users/devices", {"size": 100})
    assert api.calls[2] == (
        "/v1.0/iot-01/associated-users/devices",
        {"size": 100, "last_row_key": "K1"},
    )


def test_fallback_failure_returns_what_it_got():
    api = StubApi(
        [
            PERMISSION_DENY,
            page(["a"], has_more=True, last_row_key="K1"),
            {"code": 1004, "msg": "sign invalid", "success": False},
        ]
    )
    assert [d["id"] for d in fetch_smart_home_device_list(api)] == ["a"]


def test_missing_last_row_key_stops_the_loop():
    api = StubApi([PERMISSION_DENY, page(["a"], has_more=True, last_row_key="")])
    assert [d["id"] for d in fetch_smart_home_device_list(api)] == ["a"]


if __name__ == "__main__":
    test_old_endpoint_still_works()
    test_fallback_pages_until_done()
    test_fallback_failure_returns_what_it_got()
    test_missing_last_row_key_stops_the_loop()
    print("ok")
