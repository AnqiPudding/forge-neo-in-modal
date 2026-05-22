from __future__ import annotations

import argparse
import sys
import time
import urllib.error
import urllib.request


def normalize_url(url: str) -> str:
    url = url.strip()
    if not url:
        raise ValueError("Forge Neo URL is empty.")
    if not url.startswith(("http://", "https://")):
        raise ValueError(f"Forge Neo URL must start with http:// or https://, got: {url!r}")
    return url.rstrip("/")


def check_ready(base_url: str, request_timeout: int) -> tuple[bool, str]:
    request = urllib.request.Request(
        f"{base_url}/sdapi/v1/options",
        headers={
            "Cache-Control": "no-cache",
            "User-Agent": "forge-neo-modal-start-wait",
        },
    )
    try:
        with urllib.request.urlopen(request, timeout=request_timeout) as response:
            response.read(4096)
            if response.status == 200:
                return True, "HTTP 200 from /sdapi/v1/options"
            return False, f"HTTP {response.status} from /sdapi/v1/options"
    except urllib.error.HTTPError as exc:
        return False, f"HTTP {exc.code} from /sdapi/v1/options"
    except Exception as exc:
        return False, f"{type(exc).__name__}: {exc}"


def main() -> int:
    parser = argparse.ArgumentParser(description="Wait until the deployed Forge Neo endpoint is ready.")
    parser.add_argument("url", help="Base Forge Neo URL, such as https://workspace--forge-neo.modal.run")
    parser.add_argument("--timeout", type=int, default=1200, help="Maximum seconds to wait.")
    parser.add_argument("--interval", type=int, default=5, help="Seconds between probes.")
    parser.add_argument("--request-timeout", type=int, default=45, help="Seconds before one HTTP probe times out.")
    args = parser.parse_args()

    try:
        base_url = normalize_url(args.url)
    except ValueError as exc:
        print(exc, file=sys.stderr)
        return 2

    print(f"Waking Forge Neo and waiting for API readiness: {base_url}")
    print("This can take a few minutes after stop-server.bat or a fresh deploy.")

    deadline = time.monotonic() + args.timeout
    started = time.monotonic()
    next_notice = started
    last_status = "not checked yet"

    while time.monotonic() < deadline:
        ready, last_status = check_ready(base_url, args.request_timeout)
        elapsed = int(time.monotonic() - started)
        if ready:
            print(f"Forge Neo is ready after {elapsed}s ({last_status}).")
            return 0

        now = time.monotonic()
        if now >= next_notice:
            print(f"Still starting after {elapsed}s ({last_status}).")
            next_notice = now + 15

        time.sleep(max(1, args.interval))

    print(f"Timed out waiting for Forge Neo after {args.timeout}s ({last_status}).", file=sys.stderr)
    return 1


if __name__ == "__main__":
    raise SystemExit(main())
