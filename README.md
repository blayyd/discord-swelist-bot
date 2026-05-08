# Discord swelist Bot

Discord bot that posts **new** internship / new-grad openings sourced from the same SimplifyJobs `listings.json` files used by `swelist`, and pings roles based on **category** (SWE/PM/DS-ML/Quant/Hardware) and **location** (CA/NY/etc.).

## Setup

### 1) Create a Discord application + bot

- In the Discord Developer Portal, create an application and add a bot.
- Copy the bot token.

### 2) Invite the bot to your server

The bot only needs to send messages and use slash commands.

### 3) Create roles in your server

Create roles you want pinged, e.g.:
- Category roles: `Software Engineering`, `Product Management`, `Data Science, AI & Machine Learning`, `Quantitative Finance`, `Hardware Engineering`
- Location roles: `CA`, `NY`, `Remote`, etc.

Copy the **role IDs** (Developer Mode → right click role → Copy ID).

### 4) Pick a channel

Copy the **channel ID** (Developer Mode → right click channel → Copy ID).

## Configure

From the project root:

1) Create `.env` from `.env.example`:

```bash
copy .env.example .env
```

Edit `.env` and set:

```
DISCORD_TOKEN=YOUR_TOKEN_HERE
```

2) Create `config.json` from `config.example.json`:

```bash
copy config.example.json config.json
```

Edit `config.json`:
- `channel_id`: required when `notify_channels` is omitted or `[]` (single-channel mode). If `notify_channels` has one or more entries, you may omit `channel_id`; it then defaults to the first entry’s `channel_id` for display/legacy purposes. You can still set `channel_id` explicitly if you want a different “primary” id in `/status`.
- `poll_minutes`: how often to poll (default 15)
- `include_newgrad`: when using legacy single-channel mode, controls which job types are fetched; when `notify_channels` entries omit `job_types`, they default to `internship` plus `newgrad` if this is true
- `notify_channels` **(optional)**: list of per-channel filters for automatic job posts. Each object:
  - `channel_id`: Discord channel to post into
  - `job_types`: `["internship"]`, `["newgrad"]`, or both (omit to use the same default as `include_newgrad`)
  - `categories`: list of SimplifyJobs category strings (e.g. `"Hardware"`, `"Software Engineering"`). Empty list `[]` means all categories
  - `location`: same syntax as `/swelist` (e.g. `"all"`, `"CA"`, `"Toronto"`, `"CA, NY"`)
- `internship_listings_url` / `newgrad_listings_url` **(optional)**: raw GitHub URLs to each repo’s `listings.json` (same shape as SimplifyJobs). If omitted, built-in defaults are used (Summer 2026 internships + New-Grad-Positions on `dev`).
- `category_roles`: map SimplifyJobs `category` string → Discord role id (for pings)
- `location_roles`: map a location key → Discord role id (for pings)
  - 2-letter keys (e.g. `CA`, `NY`) match if a job location ends with that state code
  - longer keys (e.g. `Remote`, `Toronto`) match substring anywhere in locations

## Run

```bash
py -m venv .venv
.venv\\Scripts\\activate
pip install -r requirements.txt
python bot.py
```

## Slash commands

- `/status`: show current config summary (including whether listing feed URLs are default or custom)
- `/reload-config`: reload `config.json` (admin only)
- `/test-post`: posts a single listing as a preview (admin only)
- `/swelist`: search listings with `role`, `timeframe`, `location`, `category`, optional `keywords` (substring on company or title), `sort` (`date_posted` newest first, `company`, `title`), and `limit`

## Notes

- On the **first run**, the bot seeds its `state.db` with all currently active postings **without posting anything**, to avoid flooding a channel.
- De-dupe is keyed by the SimplifyJobs `id` field.

