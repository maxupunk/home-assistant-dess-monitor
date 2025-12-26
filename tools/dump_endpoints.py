"""Dump DESS Monitor endpoints to JSON files.

Usage examples:

1) Using a full URL (already signed):
   python tools/dump_endpoints.py --url "https://web.dessmonitor.com/public/?..." --outdir endpoint_dumps

2) Using explicit payload pieces (already signed):
   python tools/dump_endpoints.py --base-url https://web.dessmonitor.com --path public \
     --token ... --salt 123 --sign ... \
     --param action=queryDeviceDataOneDayPaging --param source=1 ...

3) Compute signature (requires secret):
   python tools/dump_endpoints.py --base-url https://web.dessmonitor.com --path public \
     --token ... --secret ... --param action=queryDeviceFields --param source=1 ...

Notes:
- This script writes sensitive data (token/sign) into dump metadata. Keep `endpoint_dumps/` out of git.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import time
import urllib.parse
import urllib.error
import urllib.request
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Dict, Iterable, List, Optional, Tuple

DEFAULT_UA = (
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
    "AppleWebKit/537.36 (KHTML, like Gecko) "
    "Chrome/133.0.0.0 Safari/537.36"
)


@dataclass
class RequestPlan:
    url: str
    action: str
    payload: Dict[str, Any]
    path: str


def _parse_kv_pairs(pairs: Iterable[str]) -> Dict[str, str]:
    out: Dict[str, str] = {}
    for item in pairs:
        if "=" not in item:
            raise ValueError(f"Invalid --param '{item}', expected key=value")
        k, v = item.split("=", 1)
        k = k.strip()
        if not k:
            raise ValueError(f"Invalid --param '{item}', empty key")
        out[k] = v
    return out


def _sha1_hex(text: str) -> str:
    return hashlib.sha1(text.encode("utf-8")).hexdigest()


def _urlencode(params: Dict[str, Any]) -> str:
    # Match integration behavior: doseq=False, safe='@'
    return urllib.parse.urlencode(params, doseq=False, safe="@")


def _compute_sign(*, salt: int, secret: str, token: str, params: Dict[str, Any]) -> str:
    qs = _urlencode(params)
    return _sha1_hex(f"{salt}{secret}{token}&{qs}")


def build_request_plan(
    *,
    base_url: str,
    path: str,
    token: Optional[str],
    secret: Optional[str],
    salt: Optional[int],
    sign: Optional[str],
    params: Dict[str, Any],
    full_url: Optional[str],
) -> RequestPlan:
    if full_url:
        # Best effort parse action for naming
        parsed = urllib.parse.urlsplit(full_url)
        q = urllib.parse.parse_qs(parsed.query, keep_blank_values=True)
        action = (q.get("action", ["unknown"])[0]) or "unknown"
        payload: Dict[str, Any] = {k: (v[0] if v else "") for k, v in q.items()}
        return RequestPlan(url=full_url, action=action, payload=payload, path=parsed.path)

    if not token:
        raise ValueError("Missing --token (or provide --url)")

    if "action" not in params or not str(params["action"]).strip():
        raise ValueError("Missing action: pass --param action=...")

    action = str(params["action"]).strip()

    computed_salt = int(time.time()) if salt is None else int(salt)

    computed_sign = sign
    if computed_sign is None:
        if not secret:
            raise ValueError("Missing --sign; to compute it you must provide --secret")
        computed_sign = _compute_sign(salt=computed_salt, secret=secret, token=token, params=params)

    payload: Dict[str, Any] = {
        "sign": computed_sign,
        "salt": computed_salt,
        "token": token,
        **params,
    }

    path = path.strip("/")
    if path not in {"public", "remote"}:
        raise ValueError("--path must be 'public' or 'remote'")

    url = f"{base_url.rstrip('/')}/{path}/?{_urlencode(payload)}"
    return RequestPlan(url=url, action=action, payload=payload, path=f"/{path}/")


def fetch_json(url: str, *, user_agent: str, timeout_s: int = 30) -> Tuple[int, Dict[str, Any] | List[Any] | str]:
    req = urllib.request.Request(
        url,
        method="GET",
        headers={
            "User-Agent": user_agent,
            "Accept": "application/json,text/plain,*/*",
        },
    )
    try:
        with urllib.request.urlopen(req, timeout=timeout_s) as resp:
            status = getattr(resp, "status", 200)
            raw = resp.read()
            text = raw.decode("utf-8", errors="replace")
    except urllib.error.HTTPError as e:
        status = int(getattr(e, "code", 0) or 0)
        raw = e.read() if hasattr(e, "read") else b""
        text = raw.decode("utf-8", errors="replace")
    except Exception as e:
        return 0, f"REQUEST_FAILED: {type(e).__name__}: {e}"

    try:
        return status, json.loads(text)
    except Exception:
        return status, text


def write_dump(outdir: Path, plan: RequestPlan, status: int, data: Any) -> Path:
    outdir.mkdir(parents=True, exist_ok=True)
    ts = int(time.time() * 1000)
    safe_action = "".join(ch if ch.isalnum() or ch in "-_." else "_" for ch in plan.action)[:80]
    base = outdir / f"{ts}__{safe_action}"

    meta_path = base.with_suffix(".meta.json")
    data_path = base.with_suffix(".json")

    meta = {
        "timestamp_ms": ts,
        "action": plan.action,
        "url": plan.url,
        "http_status": status,
        "path": plan.path,
        "payload": plan.payload,
    }

    meta_path.write_text(json.dumps(meta, ensure_ascii=False, indent=2), encoding="utf-8")

    if isinstance(data, (dict, list)):
        data_path.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")
    else:
        # Store non-JSON response for inspection
        data_path.write_text(str(data), encoding="utf-8")

    return data_path


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--outdir", default="endpoint_dumps", help="Output directory")

    parser.add_argument("--url", default=None, help="Full URL to fetch (already signed)")

    parser.add_argument("--base-url", default="https://web.dessmonitor.com")
    parser.add_argument("--path", default="public", help="public|remote")

    parser.add_argument("--token", default=None)
    parser.add_argument("--secret", default=None, help="If provided and --sign missing, compute sign")
    parser.add_argument("--salt", type=int, default=None)
    parser.add_argument("--sign", default=None)

    parser.add_argument(
        "--param",
        action="append",
        default=[],
        help="Query param in key=value form (repeatable). Example: --param action=queryDeviceFields",
    )

    parser.add_argument("--user-agent", default=DEFAULT_UA)
    parser.add_argument("--timeout", type=int, default=30)

    args = parser.parse_args()

    params = _parse_kv_pairs(args.param)

    try:
        plan = build_request_plan(
            base_url=args.base_url,
            path=args.path,
            token=args.token,
            secret=args.secret,
            salt=args.salt,
            sign=args.sign,
            params=params,
            full_url=args.url,
        )
    except Exception as e:
        print(f"ERROR: {e}")
        return 2

    status, data = fetch_json(plan.url, user_agent=args.user_agent, timeout_s=args.timeout)
    out_path = write_dump(Path(args.outdir), plan, status, data)

    print(f"Saved: {out_path}")
    print(f"HTTP status: {status}")
    if isinstance(data, dict) and "err" in data:
        print(f"API err: {data.get('err')} desc: {data.get('desc')}")

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
