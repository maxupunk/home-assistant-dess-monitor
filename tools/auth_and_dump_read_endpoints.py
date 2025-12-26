"""Authenticate (authSource) and dump READ endpoints to JSON files.

Security:
- Do NOT pass password on the command line.
- Provide credentials via environment variables:

  - DESS_EMAIL
  - DESS_PASSWORD

Example (PowerShell):
  $env:DESS_EMAIL="you@example.com"
  $env:DESS_PASSWORD="your_password"
  D:/Projetos/python/home-assistant-dess-monitor/.venv/Scripts/python.exe tools/auth_and_dump_read_endpoints.py \
    --pn Q0048062245666 --devcode 2376 --devaddr 1 --sn Q0048062245666094801 --date 2025-12-26

This script intentionally only calls read-only-ish actions by default.
Control endpoints like `ctrlDevice` and `sendCmdToDevice` are excluded.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import getpass
import sys
import time
import urllib.parse
import urllib.request
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Dict, List, Tuple

# Allow running this script from the repository root without PYTHONPATH tweaks.
_TOOLS_DIR = Path(__file__).resolve().parent
if str(_TOOLS_DIR) not in sys.path:
    sys.path.insert(0, str(_TOOLS_DIR))

from dump_endpoints import DEFAULT_UA, build_request_plan, fetch_json, write_dump

BASE_URL = "https://web.dessmonitor.com"


@dataclass
class AuthResult:
    token: str
    secret: str
    uid: str | None
    usr: str | None


def _sha1_hex(text: str) -> str:
    return hashlib.sha1(text.encode("utf-8")).hexdigest()


def _urlencode(params: Dict[str, Any]) -> str:
    return urllib.parse.urlencode(params, doseq=False, safe="@")


def auth_source(*, email: str, password: str, user_agent: str, timeout_s: int = 30) -> AuthResult:
    password_hash = _sha1_hex(password)

    params = {
        "action": "authSource",
        "usr": email,
        "source": "1",
        "company-key": "bnrl_frRFjEz8Mkn",
    }

    qs = _urlencode(params)
    salt = int(time.time())
    sign = _sha1_hex(f"{salt}{password_hash}&{qs}")

    payload = {"sign": sign, "salt": salt, **params}
    url = f"{BASE_URL}/public/?{_urlencode(payload)}"

    req = urllib.request.Request(
        url,
        method="GET",
        headers={
            "User-Agent": user_agent,
            "Accept": "application/json,text/plain,*/*",
            "Referer": "https://www.dessmonitor.com/",
            "Origin": "web.dessmonitor.com",
            "Host": "web.dessmonitor.com",
        },
    )

    with urllib.request.urlopen(req, timeout=timeout_s) as resp:
        raw = resp.read()

    data = json.loads(raw.decode("utf-8", errors="replace"))
    if data.get("err") != 0:
        raise RuntimeError(f"authSource failed: err={data.get('err')} desc={data.get('desc')}")

    dat = data.get("dat") or {}
    token = dat.get("token")
    secret = dat.get("secret")
    if not token or not secret:
        raise RuntimeError("authSource response missing token/secret")

    return AuthResult(token=token, secret=secret, uid=dat.get("uid"), usr=dat.get("usr"))


READ_ACTIONS: List[str] = [
    "webQueryDeviceEs",
    "webQueryDeviceEnergyFlowEs",
    "querySPDeviceLastData",
    "queryDeviceParsEs",
    "queryDeviceCtrlField",
    "queryDeviceFields",
    "queryDeviceDataOneDayPaging",
    "webQueryCollectorsEs",
]


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--outdir", default="endpoint_dumps")
    parser.add_argument("--user-agent", default=DEFAULT_UA)
    parser.add_argument("--timeout", type=int, default=30)

    parser.add_argument("--i18n", default="en_US")
    parser.add_argument("--source", default="1")

    # Device identity
    parser.add_argument("--pn", required=True)
    parser.add_argument("--devcode", required=True)
    parser.add_argument("--devaddr", required=True)
    parser.add_argument("--sn", required=True)

    # For paging endpoints
    parser.add_argument("--page", default="0")
    parser.add_argument("--pagesize", default="15")
    parser.add_argument("--date", default=None, help="YYYY-MM-DD (used by queryDeviceDataOneDayPaging)")

    args = parser.parse_args()

    email = os.environ.get("DESS_EMAIL", "").strip()
    password = os.environ.get("DESS_PASSWORD", "")

    # Fallback to interactive prompts (safer than putting secrets on CLI)
    if not email:
        email = input("DESS email: ").strip()
    if not password:
        password = getpass.getpass("DESS password: ")

    if not email or not password:
        print("ERROR: Missing credentials (DESS_EMAIL/DESS_PASSWORD or interactive input).")
        return 2

    try:
        auth = auth_source(email=email, password=password, user_agent=args.user_agent, timeout_s=args.timeout)
    except Exception as e:
        print(f"ERROR: {e}")
        return 3

    outdir = Path(args.outdir)

    common_device = {
        "pn": args.pn,
        "devcode": args.devcode,
        "devaddr": args.devaddr,
        "sn": args.sn,
    }

    ok = 0
    for action in READ_ACTIONS:
        params: Dict[str, Any] = {"action": action}

        # Common i18n/source used by most device endpoints
        if action not in {"webQueryCollectorsEs", "webQueryDeviceEs"}:
            params.update({"i18n": args.i18n, "source": args.source})
            params.update(common_device)

        if action == "webQueryDeviceEs":
            params.update({"i18n": args.i18n, "source": args.source, "page": args.page, "pagesize": args.pagesize})

        if action == "queryDeviceDataOneDayPaging":
            if not args.date:
                print("Skipping queryDeviceDataOneDayPaging (missing --date)")
                continue
            params.update({"page": args.page, "pagesize": args.pagesize, "date": args.date})

        if action == "webQueryCollectorsEs":
            params.update({"source": args.source, "devtype": "2304", "page": args.page, "pagesize": args.pagesize})

        plan = build_request_plan(
            base_url=BASE_URL,
            path="public",
            token=auth.token,
            secret=auth.secret,
            salt=None,
            sign=None,
            params=params,
            full_url=None,
        )

        status, data = fetch_json(plan.url, user_agent=args.user_agent, timeout_s=args.timeout)
        out_path = write_dump(outdir, plan, status, data)
        print(f"Saved: {out_path} (HTTP {status})")
        ok += 1

    print(f"Done. Dumps: {ok}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
