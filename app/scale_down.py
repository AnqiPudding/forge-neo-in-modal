from __future__ import annotations

import os

import modal


APP_NAME = os.environ.get("MODAL_APP_NAME", "forge-neo-modal-l40s")
FUNCTION_NAME = os.environ.get("MODAL_FORGE_FUNCTION_NAME", "forge_neo")
ENVIRONMENT_NAME = os.environ.get("MODAL_ENVIRONMENT") or None
MIN_CONTAINERS = int(os.environ.get("MODAL_AUTOSCALER_MIN_CONTAINERS", "0"))
BUFFER_CONTAINERS = int(os.environ.get("MODAL_AUTOSCALER_BUFFER_CONTAINERS", "0"))
SCALEDOWN_WINDOW = int(os.environ.get("MODAL_AUTOSCALER_SCALEDOWN_WINDOW", "2"))
ACTION_LABEL = os.environ.get("MODAL_AUTOSCALER_ACTION_LABEL", "Set")


def main() -> None:
    function = modal.Function.from_name(
        APP_NAME,
        FUNCTION_NAME,
        environment_name=ENVIRONMENT_NAME,
    )
    function.update_autoscaler(
        min_containers=MIN_CONTAINERS,
        buffer_containers=BUFFER_CONTAINERS,
        scaledown_window=SCALEDOWN_WINDOW,
    )
    print(
        f"{ACTION_LABEL} {APP_NAME}/{FUNCTION_NAME} autoscaler to "
        f"min_containers={MIN_CONTAINERS}, buffer_containers={BUFFER_CONTAINERS}, "
        f"scaledown_window={SCALEDOWN_WINDOW}."
    )
    if SCALEDOWN_WINDOW <= 2:
        print("Close the Forge Neo browser tab if it is still connected; active requests keep a container alive.")


if __name__ == "__main__":
    main()
