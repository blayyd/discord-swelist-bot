from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Iterable

import discord

from config import BotConfig


@dataclass(frozen=True)
class Mentions:
    role_ids: tuple[int, ...]

    def as_message_prefix(self) -> str:
        if not self.role_ids:
            return ""
        return " ".join(f"<@&{rid}>" for rid in self.role_ids)


def _job_locations(job: dict[str, Any]) -> list[str]:
    locs = job.get("locations")
    if isinstance(locs, list):
        return [x for x in locs if isinstance(x, str)]
    loc = job.get("location")
    if isinstance(loc, str) and loc.strip():
        return [loc]
    return []


def compute_mentions(job: dict[str, Any], cfg: BotConfig) -> Mentions:
    role_ids: set[int] = set()

    category = job.get("category")
    if isinstance(category, str):
        rid = cfg.category_roles.get(category)
        if isinstance(rid, int):
            role_ids.add(rid)

    loc_texts = _job_locations(job)
    loc_joined = " | ".join(loc_texts).lower()
    for key, rid in cfg.location_roles.items():
        k = key.strip().lower()
        if not k:
            continue
        # Heuristic: 2-letter keys match end-of-location (state code)
        if len(k) == 2:
            if any(l.strip().lower().endswith(k) for l in loc_texts):
                role_ids.add(rid)
        else:
            if k in loc_joined:
                role_ids.add(rid)

    return Mentions(role_ids=tuple(sorted(role_ids)))


def build_embed(job: dict[str, Any], kind: str) -> discord.Embed:
    company = job.get("company_name") or "Unknown company"
    title = job.get("title") or "Unknown title"
    url = job.get("url") or None

    category = job.get("category")
    category_str = category if isinstance(category, str) else "Unknown"

    locations = _job_locations(job)
    locations_str = ", ".join(locations) if locations else "Unknown"

    embed = discord.Embed(
        title=f"{company} — {title}",
        url=url if isinstance(url, str) else None,
    )
    embed.add_field(name="Type", value=str(kind), inline=True)
    embed.add_field(name="Category", value=category_str, inline=True)
    embed.add_field(name="Location", value=locations_str, inline=False)
    if isinstance(url, str) and url:
        embed.add_field(name="Apply", value=url, inline=False)
    return embed

