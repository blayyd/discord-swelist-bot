from __future__ import annotations

from dataclasses import dataclass
import time
from typing import Any, Literal

import aiohttp

DEFAULT_INTERNSHIP_LISTINGS_URL = (
    "https://raw.githubusercontent.com/SimplifyJobs/Summer2026-Internships/refs/heads/dev/"
    ".github/scripts/listings.json"
)
DEFAULT_NEWGRAD_LISTINGS_URL = (
    "https://raw.githubusercontent.com/SimplifyJobs/New-Grad-Positions/refs/heads/dev/"
    ".github/scripts/listings.json"
)


ListingKind = Literal["internship", "newgrad"]


@dataclass(frozen=True)
class Listing:
    job: dict[str, Any]
    kind: ListingKind


async def _fetch_json(url: str) -> list[dict[str, Any]]:
    timeout = aiohttp.ClientTimeout(total=30)
    async with aiohttp.ClientSession(timeout=timeout) as session:
        async with session.get(url) as resp:
            resp.raise_for_status()
            data = await resp.json(content_type=None)
            if not isinstance(data, list):
                raise ValueError(f"Unexpected payload from {url}: expected list")
            return [x for x in data if isinstance(x, dict)]


def _is_active_and_visible(job: dict[str, Any]) -> bool:
    if not job.get("active", False):
        return False
    if job.get("is_visible") is False:
        return False
    return True


def filter_by_timeframe(jobs: list[dict[str, Any]], timeframe: str) -> list[dict[str, Any]]:
    tf = (timeframe or "lastday").strip().lower()
    seconds = 60 * 60 * 24
    if tf == "lastweek":
        seconds *= 7
    elif tf == "lastmonth":
        seconds *= 30
    elif tf == "lastday":
        seconds *= 1
    else:
        raise ValueError("timeframe must be one of: lastday, lastweek, lastmonth")

    now = time.time()
    out: list[dict[str, Any]] = []
    for j in jobs:
        dp = j.get("date_posted")
        if isinstance(dp, (int, float)) and abs(float(dp) - now) < seconds:
            out.append(j)
    return out


async def fetch_all(
    *,
    include_newgrad: bool,
    internship_url: str,
    newgrad_url: str,
) -> list[Listing]:
    jobs: list[Listing] = []

    internships = await _fetch_json(internship_url)
    jobs.extend(Listing(job=j, kind="internship") for j in internships if _is_active_and_visible(j))

    if include_newgrad:
        newgrads = await _fetch_json(newgrad_url)
        jobs.extend(Listing(job=j, kind="newgrad") for j in newgrads if _is_active_and_visible(j))

    return jobs


async def fetch_role(
    role: ListingKind,
    *,
    internship_url: str,
    newgrad_url: str,
) -> list[dict[str, Any]]:
    if role == "internship":
        data = await _fetch_json(internship_url)
    else:
        data = await _fetch_json(newgrad_url)
    return [j for j in data if _is_active_and_visible(j)]


def match_locations(jobs: list[dict[str, Any]], location_query: str) -> list[dict[str, Any]]:
    q = (location_query or "").strip().lower()
    if not q or q == "all":
        return jobs

    user_locations = [loc.strip().lower() for loc in location_query.split(",") if loc.strip()]
    out: list[dict[str, Any]] = []
    for job in jobs:
        job_locations = job.get("locations", [])
        if not isinstance(job_locations, list):
            continue
        loc_norms = [l.strip().lower() for l in job_locations if isinstance(l, str) and l.strip()]

        matched = False
        for user_loc in user_locations:
            if len(user_loc) == 2:
                # Treat as state/province code.
                if any(ln.endswith(f", {user_loc}") or ln.endswith(f" {user_loc}") for ln in loc_norms):
                    matched = True
                    break
            else:
                if any(user_loc in ln for ln in loc_norms):
                    matched = True
                    break

        if matched:
            out.append(job)

    return out


def filter_by_keywords(jobs: list[dict[str, Any]], keywords: str) -> list[dict[str, Any]]:
    q = (keywords or "").strip()
    if not q:
        return jobs
    qn = q.lower()
    out: list[dict[str, Any]] = []
    for j in jobs:
        company = j.get("company_name")
        title = j.get("title")
        c = company.lower() if isinstance(company, str) else ""
        t = title.lower() if isinstance(title, str) else ""
        if qn in c or qn in t:
            out.append(j)
    return out


def sort_jobs(jobs: list[dict[str, Any]], sort_key: str) -> list[dict[str, Any]]:
    sk = (sort_key or "date_posted").strip().lower()
    if sk == "date_posted":

        def sort_key_fn(j: dict[str, Any]) -> tuple[float, str, str]:
            dp = j.get("date_posted")
            ts = -float(dp) if isinstance(dp, (int, float)) else float("inf")
            comp = (j.get("company_name") or "").lower()
            tit = (j.get("title") or "").lower()
            return (ts, comp, tit)

        return sorted(jobs, key=sort_key_fn)

    if sk == "company":

        def sort_key_fn(j: dict[str, Any]) -> tuple[str, str]:
            return ((j.get("company_name") or "").lower(), (j.get("title") or "").lower())

        return sorted(jobs, key=sort_key_fn)

    if sk == "title":

        def sort_key_fn(j: dict[str, Any]) -> tuple[str, str]:
            return ((j.get("title") or "").lower(), (j.get("company_name") or "").lower())

        return sorted(jobs, key=sort_key_fn)

    raise ValueError("sort must be one of: date_posted, company, title")


def filter_by_category(jobs: list[dict[str, Any]], category_query: str) -> list[dict[str, Any]]:
    q = (category_query or "").strip()
    if not q or q.lower() == "all":
        return jobs
    qn = q.lower()
    out: list[dict[str, Any]] = []
    for j in jobs:
        c = j.get("category")
        if isinstance(c, str) and c.strip().lower() == qn:
            out.append(j)
    return out

