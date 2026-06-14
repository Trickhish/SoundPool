"""
Deezer "Smart Login" (TV / QR pairing) — server-side, no developer app needed.

Reverse-engineered from the Deezer Android TV app. Lets a user connect their
Deezer account (incl. Google / Apple / email) by visiting deezer.com/link and
entering a short code, exactly like logging a TV into Deezer.

Flow:
    1. anonymous JWT      POST auth.deezer.com/login/anonymous
    2. mobile_auth        -> opaque hex TOKEN
    3. derive auth_token  (custom AES, see deezer_gw_crypto)
    4. api_checkToken     -> session id (sid)
    5. smartLogin_requestCode(sid)        -> {code, journeyUrl, ttl, pollingInterval}
    6. user opens deezer.com/link, enters code, logs in
    7. smartLogin_checkCode(sid, code)    -> arlToken   (poll until ready)
    8. login/arl {"arl": arlToken}        -> persistent arl cookie

Everything runs over plain HTTPS; no Playwright, no browser, no dev app.
"""

import json
import httpx

import deezer_gw_crypto as _crypto

API_KEY = "4VCYIJUCDLOUELGD1V8WBVYBNVDYOXEWSLLZDONGBBDFVXTZJRXPR29JRLQFO6ZE"
GW = "https://api.deezer.com/1.0/gateway.php"
AUTH = "https://auth.deezer.com"
UA = "Deezer/7.1.200 (Android; 12; Tv; SHIELD Android TV)"
_HDRS = {"User-Agent": UA, "Content-Type": "application/json"}


class SmartLoginError(RuntimeError):
    pass


def _gw(client: httpx.Client, jwt: str, method: str, *, sid: str | None = None,
        body: dict | None = None, extra: dict | None = None) -> dict:
    params = {"api_key": API_KEY, "output": "3", "network": "wifi", "method": method}
    if method.startswith("smartLogin_"):
        params["input"] = "3"
    if sid:
        params["sid"] = sid
    if extra:
        params.update(extra)
    r = client.post(GW, params=params, headers={**_HDRS, "Authorization": f"Bearer {jwt}"},
                    content=json.dumps(body or {}))
    r.raise_for_status()
    return r.json()


def open_session(client: httpx.Client) -> tuple[str, str]:
    """Steps 1-4. Returns (jwt, sid) for an anonymous TV session."""
    jwt = client.post(f"{AUTH}/login/anonymous", params={"jo": "p", "rto": "c", "i": "c"},
                      headers=_HDRS, content="{}").json()["jwt"]

    ma = _gw(client, jwt, "mobile_auth", extra={
        "version": "7.1.200", "lang": "en", "buildId": "android_tv",
        "screenWidth": "1920", "screenHeight": "1080", "uniq_id": "0" * 32,
    })
    token = ma.get("results", {}).get("TOKEN")
    if not token:
        raise SmartLoginError(f"mobile_auth failed: {ma.get('error')}")

    auth_token = _crypto.derive_auth_token(token)
    ct = _gw(client, jwt, "api_checkToken", extra={"auth_token": auth_token})
    sid = ct.get("results")
    if not isinstance(sid, str):
        raise SmartLoginError(f"api_checkToken failed: {ct.get('error')}")
    return jwt, sid


def request_code(client: httpx.Client, jwt: str, sid: str) -> dict:
    """Step 5. Returns {smartLoginCode, journeyUrl, ttl, pollingInterval, QRCodeImageHash}."""
    r = _gw(client, jwt, "smartLogin_requestCode", sid=sid)
    res = r.get("results")
    if not res:
        raise SmartLoginError(f"requestCode failed: {r.get('error')}")
    return res


def check_code(client: httpx.Client, jwt: str, sid: str, code: str) -> str | None:
    """Step 7. Returns arlToken once the user has logged in, else None (still pending)."""
    r = _gw(client, jwt, "smartLogin_checkCode", sid=sid, body={"CODE": code})
    err = r.get("error")
    if err:
        # user_not_logged_in -> still waiting; anything else is fatal
        if isinstance(err, dict) and err.get("DATA_ERROR") == "user_not_logged_in":
            return None
        raise SmartLoginError(f"checkCode failed: {err}")
    return r.get("results", {}).get("arlToken")


def validate_arl(arl: str) -> dict | None:
    """Return basic Deezer account info if `arl` is a working ARL cookie, else None."""
    r = httpx.post("https://www.deezer.com/ajax/gw-light.php",
                   params={"method": "deezer.getUserData", "input": "3",
                           "api_version": "1.0", "api_token": ""},
                   headers={"User-Agent": UA}, cookies={"arl": arl},
                   content="{}", timeout=20).json()
    user = r.get("results", {}).get("USER", {})
    uid = user.get("USER_ID")
    return {"user_id": uid, "name": user.get("BLOG_NAME") or user.get("FIRSTNAME", "")} if uid else None


def start() -> dict:
    """Begin a smart-login. Returns the info needed to show the user a code/QR,
    plus the opaque (jwt, sid) to resume polling."""
    client = httpx.Client(timeout=20)
    jwt, sid = open_session(client)
    info = request_code(client, jwt, sid)
    client.close()
    return {
        "code": info["smartLoginCode"],
        "journey_url": info.get("journeyUrl", "https://www.deezer.com/link"),
        "ttl": info.get("ttl", 900),
        "poll_interval": info.get("pollingInterval", 2),
        "qr_hash": info.get("QRCodeImageHash"),
        "jwt": jwt,
        "sid": sid,
    }


def poll(jwt: str, sid: str, code: str) -> str | None:
    """One poll. Returns the ARL (a 192-char cookie) once logged in, else None.
    The smart-login `arlToken` is itself a ready-to-use ARL."""
    client = httpx.Client(timeout=20)
    try:
        return check_code(client, jwt, sid, code)
    finally:
        client.close()


if __name__ == "__main__":
    import time
    s = start()
    print(f"\n  Go to {s['journey_url']} and enter code:  {s['code']}\n")
    print(f"  (valid {s['ttl']}s, polling every {s['poll_interval']}s)\n")
    deadline = time.time() + s["ttl"]
    while time.time() < deadline:
        arl = poll(s["jwt"], s["sid"], s["code"])
        if arl:
            print("ARL:", arl)
            break
        time.sleep(s["poll_interval"])
    else:
        print("Timed out.")
