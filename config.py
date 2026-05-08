from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from swelist_client import DEFAULT_INTERNSHIP_LISTINGS_URL, DEFAULT_NEWGRAD_LISTINGS_URL


@dataclass(frozen=True)
class NotifyChannel:
    channel_id: int
    job_types: tuple[str, ...]
    categories: tuple[str, ...]
    location: str


@dataclass(frozen=True)
class BotConfig:
    """Primary channel id for status/legacy; when using notify_channels-only config, defaults to first target."""
    channel_id: int
    poll_minutes: int
    include_newgrad: bool
    internship_listings_url: str
    newgrad_listings_url: str
    category_roles: dict[str, int]
    location_roles: dict[str, int]
    notify_channels: tuple[NotifyChannel, ...]


def _listing_url(raw: dict[str, Any], key: str, default: str) -> str:
    v = raw.get(key)
    if v is None:
        return default
    if not isinstance(v, str) or not v.strip():
        raise ValueError(f"{key} must be a non-empty string if provided")
    u = v.strip()
    lower = u.lower()
    if not (lower.startswith("http://") or lower.startswith("https://")):
        raise ValueError(f"{key} must start with http:// or https://")
    return u


def _as_int_map(obj: Any, *, field_name: str) -> dict[str, int]:
    if not isinstance(obj, dict):
        raise ValueError(f"{field_name} must be an object mapping string -> role_id")
    out: dict[str, int] = {}
    for k, v in obj.items():
        if not isinstance(k, str) or not k.strip():
            raise ValueError(f"{field_name} keys must be non-empty strings")
        if not isinstance(v, int):
            raise ValueError(f"{field_name}[{k!r}] must be an integer role id")
        out[k] = v
    return out


def _parse_notify_channels(
    raw: dict[str, Any],
    *,
    include_newgrad: bool,
    legacy_channel_id: int | None,
) -> tuple[NotifyChannel, ...]:
    arr = raw.get("notify_channels")
    if arr is None or arr == []:
        if legacy_channel_id is None:
            raise ValueError("channel_id is required when notify_channels is omitted or empty")
        jt: list[str] = ["internship"]
        if include_newgrad:
            jt.append("newgrad")
        return (
            NotifyChannel(
                channel_id=legacy_channel_id,
                job_types=tuple(jt),
                categories=(),
                location="all",
            ),
        )

    if not isinstance(arr, list):
        raise ValueError("notify_channels must be a list")

    out: list[NotifyChannel] = []
    for i, item in enumerate(arr):
        if not isinstance(item, dict):
            raise ValueError(f"notify_channels[{i}] must be an object")
        cid = item.get("channel_id")
        if not isinstance(cid, int):
            raise ValueError(f"notify_channels[{i}].channel_id must be an integer")

        jt_raw = item.get("job_types")
        if jt_raw is None:
            jt_list = ["internship"]
            if include_newgrad:
                jt_list.append("newgrad")
        elif isinstance(jt_raw, list):
            jt_list = [str(x).strip().lower() for x in jt_raw if x is not None and str(x).strip()]
        else:
            raise ValueError(f"notify_channels[{i}].job_types must be a list of strings")

        for j in jt_list:
            if j not in ("internship", "newgrad"):
                raise ValueError(f"notify_channels[{i}].job_types: invalid {j!r} (use internship, newgrad)")

        cats_raw = item.get("categories")
        if cats_raw is None:
            cats: tuple[str, ...] = ()
        elif isinstance(cats_raw, list):
            cats = tuple(str(c) for c in cats_raw if isinstance(c, str) and c.strip())
        else:
            raise ValueError(f"notify_channels[{i}].categories must be a list of strings")

        loc = item.get("location", "all")
        if not isinstance(loc, str):
            raise ValueError(f"notify_channels[{i}].location must be a string")
        loc = loc.strip() or "all"

        out.append(
            NotifyChannel(
                channel_id=cid,
                job_types=tuple(jt_list),
                categories=cats,
                location=loc,
            )
        )

    return tuple(out)


def load_config(path: str | Path = "config.json") -> BotConfig:
    p = Path(path)
    raw = json.loads(p.read_text(encoding="utf-8"))
    if not isinstance(raw, dict):
        raise ValueError("config.json must be a JSON object")

    channel_id_raw = raw.get("channel_id")
    poll_minutes = raw.get("poll_minutes", 15)
    include_newgrad = raw.get("include_newgrad", True)
    category_roles = _as_int_map(raw.get("category_roles", {}), field_name="category_roles")
    location_roles = _as_int_map(raw.get("location_roles", {}), field_name="location_roles")

    arr = raw.get("notify_channels")
    if arr is not None and not isinstance(arr, list):
        raise ValueError("notify_channels must be a list or omitted")
    uses_notify_list = isinstance(arr, list) and len(arr) > 0

    if channel_id_raw is not None and not isinstance(channel_id_raw, int):
        raise ValueError("channel_id must be an integer if provided")

    if uses_notify_list:
        legacy_channel_id: int | None = None
    else:
        if not isinstance(channel_id_raw, int):
            raise ValueError("channel_id must be an integer when notify_channels is omitted or empty")
        legacy_channel_id = channel_id_raw

    if not isinstance(poll_minutes, int) or poll_minutes <= 0:
        raise ValueError("poll_minutes must be a positive integer")
    if not isinstance(include_newgrad, bool):
        raise ValueError("include_newgrad must be a boolean")

    internship_listings_url = _listing_url(
        raw, "internship_listings_url", DEFAULT_INTERNSHIP_LISTINGS_URL
    )
    newgrad_listings_url = _listing_url(raw, "newgrad_listings_url", DEFAULT_NEWGRAD_LISTINGS_URL)

    notify_channels = _parse_notify_channels(
        raw,
        include_newgrad=include_newgrad,
        legacy_channel_id=legacy_channel_id,
    )

    if uses_notify_list:
        resolved_channel_id = (
            channel_id_raw if isinstance(channel_id_raw, int) else notify_channels[0].channel_id
        )
    else:
        assert isinstance(channel_id_raw, int)
        resolved_channel_id = channel_id_raw

    return BotConfig(
        channel_id=resolved_channel_id,
        poll_minutes=poll_minutes,
        include_newgrad=include_newgrad,
        internship_listings_url=internship_listings_url,
        newgrad_listings_url=newgrad_listings_url,
        category_roles=category_roles,
        location_roles=location_roles,
        notify_channels=notify_channels,
    )
