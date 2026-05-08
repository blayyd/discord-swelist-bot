from __future__ import annotations

from typing import Any

from swelist_client import match_locations


def job_matches_notify_target(
    job: dict[str, Any],
    kind: str,
    *,
    job_types: list[str],
    categories: list[str],
    location: str,
) -> bool:
    """Return True if this job should be posted to a notify target with the given filters."""
    allowed = {x.strip().lower() for x in job_types if x and str(x).strip()}
    if allowed and kind not in allowed:
        return False

    if categories:
        want = {c.strip().lower() for c in categories if isinstance(c, str) and c.strip()}
        cat = job.get("category")
        if not isinstance(cat, str) or cat.strip().lower() not in want:
            return False

    loc = (location or "all").strip()
    if not loc or loc.lower() == "all":
        return True

    matched = match_locations([job], loc)
    return len(matched) > 0
