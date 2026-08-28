#!/usr/bin/env python3
"""Fetch contribution stats for the live "NOW IN PRODUCTION" card (stdlib only).

    GITHUB_TOKEN=... python3 scripts/fetch_stats.py > stats.json

Reads the contribution calendar, which includes private contributions because
the profile has "Include private contributions" enabled. Only day counts are
used, so no repository or organization name can leak into the README.
"""
from __future__ import annotations

import json
import os
import sys
import urllib.request
from datetime import date, datetime, timedelta, timezone
from typing import Dict, Optional

LOGIN = "halilmertogut"
ENDPOINT = "https://api.github.com/graphql"
QUERY = """
query($login: String!, $from: DateTime!, $to: DateTime!) {
  user(login: $login) {
    contributionsCollection(from: $from, to: $to) {
      contributionCalendar {
        totalContributions
        weeks { contributionDays { date contributionCount } }
      }
    }
  }
}
"""


def fetch_calendar(token: str, start: date, end: date) -> dict:
    body = json.dumps(
        {"query": QUERY, "variables": {"login": LOGIN, "from": f"{start}T00:00:00Z", "to": f"{end}T23:59:59Z"}}
    ).encode()
    req = urllib.request.Request(
        ENDPOINT,
        data=body,
        headers={"Authorization": f"bearer {token}", "Content-Type": "application/json", "User-Agent": "profile-readme"},
    )
    with urllib.request.urlopen(req, timeout=30) as resp:
        payload = json.load(resp)
    if payload.get("errors"):
        raise SystemExit(f"GraphQL error: {payload['errors']}")
    return payload["data"]["user"]["contributionsCollection"]["contributionCalendar"]


def summarize(days: Dict[date, int], today: date) -> dict:
    last_30 = sum(count for day, count in days.items() if today - timedelta(days=29) <= day <= today)
    # Streak counts back from today, or from yesterday while today is still empty.
    cursor = today if days.get(today, 0) > 0 else today - timedelta(days=1)
    streak = 0
    while days.get(cursor, 0) > 0:
        streak += 1
        cursor -= timedelta(days=1)
    active = [day for day, count in days.items() if count > 0]
    last_seen: Optional[int] = (today - max(active)).days if active else None
    return {"last_30_days": last_30, "streak_days": streak, "last_seen_days_ago": last_seen}


def main() -> None:
    token = os.environ.get("GITHUB_TOKEN")
    if not token:
        sys.exit("GITHUB_TOKEN is not set")
    now = datetime.now(timezone.utc)
    today = now.date()
    calendar = fetch_calendar(token, today - timedelta(days=364), today)  # API allows at most one year
    days = {
        date.fromisoformat(d["date"]): d["contributionCount"]
        for week in calendar["weeks"]
        for d in week["contributionDays"]
    }
    stats = summarize(days, today)
    stats["last_year"] = calendar["totalContributions"]
    stats["generated_at"] = now.strftime("%Y-%m-%dT%H:%M:%SZ")
    print(json.dumps(stats, indent=2))


if __name__ == "__main__":
    main()
