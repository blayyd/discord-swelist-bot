from __future__ import annotations

import sys
from pathlib import Path

# When using a `src/` layout, the package isn't importable unless `src/` is on sys.path.
sys.path.insert(0, str(Path(__file__).parent / "src"))

from discord_swelist_bot.bot import main


if __name__ == "__main__":
    main()

