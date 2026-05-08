from __future__ import annotations

import logging
import os
import time
from pathlib import Path
from urllib.parse import urlparse

import discord
from discord import app_commands
from discord.ext import tasks
from dotenv import load_dotenv

from .config import BotConfig, load_config
from .filters import job_matches_notify_target
from .formatter import build_embed, compute_mentions
from .state import State
from .swelist_client import (
    DEFAULT_INTERNSHIP_LISTINGS_URL,
    DEFAULT_NEWGRAD_LISTINGS_URL,
    Listing,
    fetch_all,
    fetch_role,
    filter_by_category,
    filter_by_keywords,
    filter_by_timeframe,
    match_locations,
    sort_jobs,
)

log = logging.getLogger("discord-swelist-bot")


class SwelistBot(discord.Client):
    def __init__(self) -> None:
        intents = discord.Intents.default()
        super().__init__(intents=intents)
        self.tree = app_commands.CommandTree(self)

        self.cfg: BotConfig | None = None
        self.state = State("state.db")

    async def setup_hook(self) -> None:
        await self.tree.sync()
        poll_loop.start()


bot = SwelistBot()


def _load_cfg() -> BotConfig:
    return load_config("config.json")


@tasks.loop(minutes=1)
async def poll_loop() -> None:
    await poll_once()


async def poll_once() -> None:
    if bot.cfg is None:
        bot.cfg = _load_cfg()
        poll_loop.change_interval(minutes=bot.cfg.poll_minutes)

    cfg = bot.cfg
    assert cfg is not None

    listings: list[Listing] = await fetch_all(
        include_newgrad=cfg.include_newgrad,
        internship_url=cfg.internship_listings_url,
        newgrad_url=cfg.newgrad_listings_url,
    )
    jobs = [l.job for l in listings]
    unseen = bot.state.filter_unseen(jobs)

    if not bot.state.has_any_rows():
        bot.state.mark_seen([j.get("id", "") for j in jobs if isinstance(j.get("id"), str)])
        log.info("Seeded seen_jobs with %d jobs; no messages sent.", len(jobs))
        return

    if not unseen:
        return

    kind_by_id: dict[str, str] = {}
    for l in listings:
        jid = l.job.get("id")
        if isinstance(jid, str) and jid:
            kind_by_id[jid] = l.kind

    processed_ids: list[str] = []
    for job in unseen:
        jid = job.get("id")
        if not isinstance(jid, str) or not jid:
            continue

        kind = kind_by_id.get(jid, "internship")

        for target in cfg.notify_channels:
            if not job_matches_notify_target(
                job,
                kind,
                job_types=list(target.job_types),
                categories=list(target.categories),
                location=target.location,
            ):
                continue

            channel = bot.get_channel(target.channel_id)
            if channel is None or not isinstance(channel, discord.abc.Messageable):
                log.warning("Channel %s not found or not messageable", target.channel_id)
                continue

            embed = build_embed(job, kind)
            mentions = compute_mentions(job, cfg).as_message_prefix()

            await channel.send(
                content=mentions or None,
                embed=embed,
                allowed_mentions=discord.AllowedMentions(roles=True),
            )

        processed_ids.append(jid)

    bot.state.mark_seen(processed_ids)
    log.info("Processed %d new jobs (posted to matching notify channels).", len(processed_ids))


@poll_loop.before_loop
async def before_poll_loop() -> None:
    await bot.wait_until_ready()


def _is_admin(interaction: discord.Interaction) -> bool:
    perms = getattr(interaction.user, "guild_permissions", None)
    return bool(perms and perms.administrator)


def _listing_url_summary_line(label: str, url: str, default: str) -> str:
    if url == default:
        return f"{label}: **default**"
    p = urlparse(url)
    tail = ((p.path or "").rstrip("/").split("/")[-1]) or "(path)"
    return f"{label}: **custom** (`{p.netloc}` … `{tail}`)"


@bot.tree.command(name="status", description="Show bot status and current config.")
async def status(interaction: discord.Interaction) -> None:
    try:
        cfg = bot.cfg or _load_cfg()
    except Exception as e:
        await interaction.response.send_message(f"Config load failed: {e}", ephemeral=True)
        return

    msg = (
        f"Legacy channel_id: `{cfg.channel_id}`\n"
        f"Notify targets: `{len(cfg.notify_channels)}`\n"
        f"{_listing_url_summary_line('Internship feed', cfg.internship_listings_url, DEFAULT_INTERNSHIP_LISTINGS_URL)}\n"
        f"{_listing_url_summary_line('New-grad feed', cfg.newgrad_listings_url, DEFAULT_NEWGRAD_LISTINGS_URL)}\n"
        f"Poll minutes: `{cfg.poll_minutes}`\n"
        f"Include newgrad: `{cfg.include_newgrad}`\n"
        f"Category roles: `{len(cfg.category_roles)}`\n"
        f"Location roles: `{len(cfg.location_roles)}`"
    )
    await interaction.response.send_message(msg, ephemeral=True)


@bot.tree.command(name="reload-config", description="Reload config.json (admin only).")
async def reload_config(interaction: discord.Interaction) -> None:
    if not _is_admin(interaction):
        await interaction.response.send_message("Admin only.", ephemeral=True)
        return
    try:
        bot.cfg = _load_cfg()
        poll_loop.change_interval(minutes=bot.cfg.poll_minutes)
    except Exception as e:
        await interaction.response.send_message(f"Reload failed: {e}", ephemeral=True)
        return
    await interaction.response.send_message("Reloaded config.json.", ephemeral=True)


@bot.tree.command(name="test-post", description="Post a single newest job (admin only).")
async def test_post(interaction: discord.Interaction) -> None:
    if not _is_admin(interaction):
        await interaction.response.send_message("Admin only.", ephemeral=True)
        return

    try:
        cfg = bot.cfg or _load_cfg()
        listings = await fetch_all(
            include_newgrad=cfg.include_newgrad,
            internship_url=cfg.internship_listings_url,
            newgrad_url=cfg.newgrad_listings_url,
        )
    except Exception as e:
        await interaction.response.send_message(f"Fetch failed: {e}", ephemeral=True)
        return

    if not listings:
        await interaction.response.send_message("No listings returned.", ephemeral=True)
        return

    job = listings[0].job
    embed = build_embed(job, listings[0].kind)
    mentions = compute_mentions(job, cfg).as_message_prefix()
    await interaction.response.send_message(
        content=mentions or None,
        embed=embed,
        allowed_mentions=discord.AllowedMentions(roles=True),
    )


@bot.tree.command(name="swelist", description="List postings (role/timeframe/location), like the swelist CLI.")
@app_commands.describe(
    role="internship (default) or newgrad",
    timeframe="lastday (default), lastweek, or lastmonth",
    location='Location filter: "all" or e.g. "Toronto" or "CA, Boston, NY"',
    category='Category filter: "all" or exact category like "Hardware" or "Software Engineering"',
    keywords="Substring match on company or title (leave empty for no filter)",
    sort="Sort: date_posted = newest first; company / title = A–Z",
    limit="Max number of postings to show (default 10)",
)
@app_commands.choices(
    role=[
        app_commands.Choice(name="internship", value="internship"),
        app_commands.Choice(name="newgrad", value="newgrad"),
    ],
    timeframe=[
        app_commands.Choice(name="lastday", value="lastday"),
        app_commands.Choice(name="lastweek", value="lastweek"),
        app_commands.Choice(name="lastmonth", value="lastmonth"),
    ],
    sort=[
        app_commands.Choice(name="date_posted (newest first)", value="date_posted"),
        app_commands.Choice(name="company (A–Z)", value="company"),
        app_commands.Choice(name="title (A–Z)", value="title"),
    ],
)
async def swelist_cmd(
    interaction: discord.Interaction,
    role: app_commands.Choice[str] | None = None,
    timeframe: app_commands.Choice[str] | None = None,
    location: str = "all",
    category: str = "all",
    keywords: str = "",
    sort: app_commands.Choice[str] | None = None,
    limit: app_commands.Range[int, 1, 25] = 10,
) -> None:
    r = role.value if role else "internship"
    tf = timeframe.value if timeframe else "lastday"
    sk = sort.value if sort else "date_posted"
    kw_display = (keywords or "").strip() or "(none)"

    sort_header = {
        "date_posted": "date_posted (newest first)",
        "company": "company (A–Z)",
        "title": "title (A–Z)",
    }.get(sk, sk)

    await interaction.response.defer(ephemeral=True)
    try:
        cfg = bot.cfg or _load_cfg()
        jobs = await fetch_role(
            r,  # type: ignore[arg-type]
            internship_url=cfg.internship_listings_url,
            newgrad_url=cfg.newgrad_listings_url,
        )
        jobs = filter_by_timeframe(jobs, tf)
        jobs = match_locations(jobs, location)
        jobs = filter_by_category(jobs, category)
        jobs = filter_by_keywords(jobs, keywords)
        jobs = sort_jobs(jobs, sk)
    except Exception as e:
        await interaction.followup.send(f"Fetch failed: {e}", ephemeral=True)
        return

    total = len(jobs)
    if total == 0:
        await interaction.followup.send(
            f"No postings found for role `{r}`, location `{location}`, category `{category}`, "
            f"keywords `{kw_display}`, timeframe `{tf}`, sort `{sort_header}`.",
            ephemeral=True,
        )
        return

    shown = jobs[: int(limit)]

    lines: list[str] = []
    for idx, job in enumerate(shown, start=1):
        company = job.get("company_name") or "Unknown company"
        title = job.get("title") or "Unknown title"
        locs = job.get("locations") or []
        loc_str = ", ".join(locs) if isinstance(locs, list) else str(locs)
        url = job.get("url") or ""
        dp = job.get("date_posted")

        age = ""
        if isinstance(dp, (int, float)):
            seconds = max(0, int(time.time() - float(dp)))
            if seconds < 60:
                age = f"{seconds}s ago"
            elif seconds < 3600:
                age = f"{seconds // 60}m ago"
            elif seconds < 86400:
                age = f"{seconds // 3600}h ago"
            else:
                age = f"{seconds // 86400}d ago"

        entry = f"{idx}. **{company}** — {title} ({loc_str})"
        if age:
            entry = f"{entry} — {age}"
        if isinstance(url, str) and url:
            entry += f" — <{url}>"
        lines.append(entry)

    header = (
        f"Found **{total}** postings for role `{r}`, location `{location}`, category `{category}`, "
        f"keywords `{kw_display}`, timeframe `{tf}`, sort `{sort_header}`.\n"
        f"Showing **{len(shown)}** (limit={int(limit)}):\n"
    )

    msg = header
    for line in lines:
        if len(msg) + len(line) + 1 > 1950:
            msg += "\n…and more (raise `limit` or narrow filters)."
            break
        msg += line + "\n"

    await interaction.followup.send(msg.strip(), ephemeral=True, suppress_embeds=True)


def main() -> None:
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s: %(message)s")
    load_dotenv()

    token = os.getenv("DISCORD_TOKEN")
    if not token:
        raise SystemExit("Missing DISCORD_TOKEN in environment (.env).")

    if not Path("config.json").exists():
        raise SystemExit("Missing config.json. Copy config.example.json to config.json and edit it.")

    bot.run(token)


if __name__ == "__main__":
    main()

