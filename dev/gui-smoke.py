"""Exercise the Tkinter convert button without manual clicking."""

from __future__ import annotations

import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from bl2flp.gui import App


def main() -> int:
    app = App()
    app.revision.set(str(ROOT / "dev" / "fixtures" / "demo" / "revision.json"))
    app.assets.set(str(ROOT / "dev" / "fixtures" / "demo" / "assets"))
    app.output.set(str(ROOT / "dev" / "fixtures" / "demo" / "gui.flp"))
    app.template.set(r"C:\Program Files\Image-Line\FL Studio 2026\Data\System\Empty.flp")

    deadline = time.time() + 60
    app._convert()

    while time.time() < deadline:
        app.update()
        if app.run_button["state"] == "normal" and app.log.get("1.0", "end").strip():
            break
        time.sleep(0.05)

    text = app.log.get("1.0", "end").strip()
    print(text)
    ok = "Done:" in text and "error:" not in text
    app.destroy()
    return 0 if ok else 1


if __name__ == "__main__":
    raise SystemExit(main())
