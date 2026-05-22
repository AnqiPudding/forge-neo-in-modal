from __future__ import annotations

import argparse
import time

import modal


def main() -> None:
    parser = argparse.ArgumentParser(description="Periodically commit a mounted Modal Volume.")
    parser.add_argument("--volume-name", required=True)
    parser.add_argument("--interval", type=int, default=120)
    args = parser.parse_args()

    volume = modal.Volume.from_name(args.volume_name)
    while True:
        time.sleep(max(10, args.interval))
        try:
            volume.commit()
            print(f"Committed Modal Volume {args.volume_name}.", flush=True)
        except Exception as exc:
            print(f"Volume commit failed: {exc}", flush=True)


if __name__ == "__main__":
    main()
