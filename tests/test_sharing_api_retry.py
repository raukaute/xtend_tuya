"""Self-check for the sharing API's retry predicate.

Standalone (no Home Assistant import) — mirrors is_retryable_error in
multi_manager/managers/tuya_sharing/xt_tuya_sharing_api.py.

Tuya packs unrelated failures into the single code -9999999. The transient
ones are worth another attempt; "sign invalid" never is. Retrying it was what
turned an expired session into a config entry that hung in SETUP_IN_PROGRESS
until Home Assistant cancelled it (observed 2026-08-10 on the farm install,
both on the official Tuya entry and later on ours).

Run: `python tests/test_sharing_api_retry.py`
"""

NON_RETRYABLE_MESSAGES: tuple[str, ...] = ("sign invalid",)


def is_retryable_error(response):
    """Mirror of xt_tuya_sharing_api.is_retryable_error."""
    if response.get("code", 0) != "-9999999":
        return False
    message = str(response.get("msg", "")).lower()
    return not any(entry in message for entry in NON_RETRYABLE_MESSAGES)


# Response bodies copied from home-assistant.log, 2026-08-10.
SIGN_INVALID = {
    "code": "-9999999",
    "msg": "sign invalid",
    "t": 1786336835051,
    "success": False,
}
SERVER_ERROR = {
    "code": "-9999999",
    "msg": "network error:(SYSTEM_ERROR) Server Error",
    "t": 1786336801900,
    "success": False,
}


def test_sign_invalid_is_not_retried():
    assert is_retryable_error(SIGN_INVALID) is False


def test_transient_server_error_is_retried():
    assert is_retryable_error(SERVER_ERROR) is True


def test_message_match_is_case_insensitive():
    assert is_retryable_error({"code": "-9999999", "msg": "Sign Invalid"}) is False


def test_other_codes_are_not_retried():
    # Only -9999999 was ever retried; keep it that way.
    assert is_retryable_error({"code": "1010", "msg": "token invalid"}) is False
    assert is_retryable_error({}) is False


def test_missing_message_still_retries():
    # A bare -9999999 with no msg keeps the old behaviour.
    assert is_retryable_error({"code": "-9999999"}) is True


if __name__ == "__main__":
    for name, test in sorted(globals().items()):
        if name.startswith("test_") and callable(test):
            test()
            print(f"ok  {name}")
    print("all passed")
