#!/usr/bin/env python3
"""Send a command to a Tuya device via the Cloud API.

Usage: python3 tuya_send_command.py <client_id> <client_secret> <device_id> <code> <value>

Handles HMAC-SHA256 signing required by Tuya's API.
"""
import hashlib
import hmac
import json
import sys
import time
import urllib.request


def main():
    if len(sys.argv) != 6:
        print("Usage: tuya_send_command.py <client_id> <client_secret> <device_id> <code> <value>")
        sys.exit(1)

    client_id, client_secret, device_id, code, value = sys.argv[1:6]
    base_url = "https://openapi.tuyaeu.com"

    # Get access token
    t = str(int(time.time() * 1000))
    content_sha256 = hashlib.sha256(b"").hexdigest()
    url = "/v1.0/token?grant_type=1"
    string_to_sign = f"GET\n{content_sha256}\n\n{url}"
    sign_str = client_id + t + string_to_sign
    sign = hmac.new(
        client_secret.encode(), sign_str.encode(), hashlib.sha256
    ).hexdigest().upper()

    req = urllib.request.Request(
        f"{base_url}{url}",
        headers={
            "client_id": client_id,
            "sign": sign,
            "t": t,
            "sign_method": "HMAC-SHA256",
        },
    )
    resp = urllib.request.urlopen(req)
    token_data = json.loads(resp.read())
    if not token_data.get("success"):
        print(json.dumps(token_data))
        sys.exit(1)
    access_token = token_data["result"]["access_token"]

    # Send command
    cmd_path = f"/v1.0/devices/{device_id}/commands"
    body = json.dumps({"commands": [{"code": code, "value": value}]})
    t2 = str(int(time.time() * 1000))
    body_sha256 = hashlib.sha256(body.encode()).hexdigest()
    string_to_sign2 = f"POST\n{body_sha256}\n\n{cmd_path}"
    sign_str2 = client_id + access_token + t2 + string_to_sign2
    sign2 = hmac.new(
        client_secret.encode(), sign_str2.encode(), hashlib.sha256
    ).hexdigest().upper()

    req2 = urllib.request.Request(
        f"{base_url}{cmd_path}",
        data=body.encode(),
        method="POST",
        headers={
            "client_id": client_id,
            "access_token": access_token,
            "sign": sign2,
            "t": t2,
            "sign_method": "HMAC-SHA256",
            "Content-Type": "application/json",
        },
    )
    resp2 = urllib.request.urlopen(req2)
    result = json.loads(resp2.read())
    print(json.dumps(result))
    sys.exit(0 if result.get("success") else 1)


if __name__ == "__main__":
    main()
