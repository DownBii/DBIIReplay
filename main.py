import json
import os
import sys
from pathlib import Path

from client.menu.window import MainWindow


DEFAULT_CONFIG = {
    "window": {
        "title": "DBII Replay",
        "width": 800,
        "height": 600
    }
}


def ensure_config(path: Path) -> dict:
    """Ensure the config file exists and contains valid JSON.

    If file doesn't exist, create it with DEFAULT_CONFIG. If it exists but
    is invalid JSON, back it up and recreate with defaults.
    Returns the loaded config as a dict.
    """
    if not path.exists():
        path.write_text(json.dumps(DEFAULT_CONFIG, indent=4), encoding="utf-8")
        return DEFAULT_CONFIG

    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except Exception:
        # Backup the bad config and recreate
        backup = path.with_suffix(path.suffix + ".bad")
        path.replace(backup)
        path.write_text(json.dumps(DEFAULT_CONFIG, indent=4), encoding="utf-8")
        return DEFAULT_CONFIG


def main() -> int:
    root = Path(__file__).parent
    config_path = root / "config.json"

    # If config.json doesn't exist at project root, create it.
    config = ensure_config(config_path)

    # Start the Qt application and show the main window.
    try:
        from PyQt6 import QtWidgets
    except Exception as e:
        print("PyQt6 is not installed or failed to import:", e)
        print("Install it with: pip install PyQt6")
        return 1

    app = QtWidgets.QApplication(sys.argv)
    win = MainWindow(config.get("window", {}))
    win.show()
    return app.exec()


if __name__ == "__main__":
    raise SystemExit(main())
