#!/usr/bin/env python3
"""Scan RustChain bounty issues and rank actionable tasks."""

from __future__ import annotations

import argparse
import datetime as dt
import json
import re
import sys
import urllib.error
import urllib.parse
import urllib.request
from dataclasses import asdict, dataclass
from typing import Any, Iterable


DEFAULT_REPO = "Scottcjn/rustchain-bounties"
REWARD_RE = re.compile(
    r"(?P<amount>\d+(?:\.\d+)?)(?:\s*[-/]\s*(?P<max>\d+(?:\.\d+)?))?\s*RTC",
    re.IGNORECASE,
)


@dataclass(slots=True)
class Bounty:
    number: int
    title: str
    url: str
    reward_rtc: float
    max_reward_rtc: float
    labels: list[str]
    comments: int
    updated_at: str
    score: float
    signals: list[str]


def request_json(url: str, token: str | None = None) -> Any:
    headers = {
        "Accept": "application/vnd.github+json",
        "User-Agent": "rustchain-bounty-radar",
    }
    if token:
        headers["Authorization"] = f"Bearer {token}"
    req = urllib.request.Request(url, headers=headers)
    with urllib.request.urlopen(req, timeout=30) as resp:
        return json.loads(resp.read().decode("utf-8"))


def parse_reward(text: str) -> tuple[float, float]:
    matches = list(REWARD_RE.finditer(text))
    if not matches:
        return 0.0, 0.0
    values: list[tuple[float, float]] = []
    for match in matches:
        low = float(match.group("amount"))
        high = float(match.group("max") or low)
        values.append((low, high))
    return max(values, key=lambda pair: pair[1])


def is_claim_issue(title: str) -> bool:
    lowered = title.lower()
    return any(marker in lowered for marker in ("claim]", "bounty claim", "[claim]"))


def is_non_task_issue(title: str) -> bool:
    lowered = title.lower()
    markers = ("payout check", "payment pending", "pending rtc transfers", "rtc claim")
    return is_claim_issue(title) or any(marker in lowered for marker in markers)


def score_issue(issue: dict[str, Any], reward: float, max_reward: float) -> tuple[float, list[str]]:
    title = issue.get("title") or ""
    body = issue.get("body") or ""
    labels = [label["name"].lower() for label in issue.get("labels", [])]
    comments = int(issue.get("comments") or 0)
    text = f"{title}\n{body}".lower()

    score = max_reward * 10
    signals: list[str] = []

    if "good first issue" in labels or "easy" in labels:
        score += 15
        signals.append("easy/onboarding label")
    if "community" in labels or "micro" in labels:
        score += 8
        signals.append("low-friction community task")
    if "open" in labels or "ongoing" in labels:
        score += 6
        signals.append("explicitly open/ongoing")
    if any(word in text for word in ("discord", "social media", "youtube")):
        score -= 8
        signals.append("external account or social proof needed")
    if is_non_task_issue(title):
        score -= 500
        signals.append("existing claim or payout-status thread")
    if comments > 250:
        score -= 6
        signals.append("crowded thread")
    elif comments < 25:
        score += 4
        signals.append("less crowded thread")
    if reward == 0:
        score -= 20
        signals.append("no RTC reward detected")

    return round(score, 2), signals


def issue_to_bounty(issue: dict[str, Any]) -> Bounty | None:
    if "pull_request" in issue:
        return None
    title = issue.get("title") or ""
    body = issue.get("body") or ""
    reward, max_reward = parse_reward(f"{title}\n{body}")
    if max_reward <= 0:
        return None
    score, signals = score_issue(issue, reward, max_reward)
    labels = [label["name"] for label in issue.get("labels", [])]
    return Bounty(
        number=int(issue["number"]),
        title=title,
        url=issue.get("html_url") or "",
        reward_rtc=reward,
        max_reward_rtc=max_reward,
        labels=labels,
        comments=int(issue.get("comments") or 0),
        updated_at=issue.get("updated_at") or "",
        score=score,
        signals=signals,
    )


def fetch_open_issues(repo: str, pages: int, token: str | None) -> Iterable[dict[str, Any]]:
    owner_repo = urllib.parse.quote(repo, safe="/")
    for page in range(1, pages + 1):
        url = (
            f"https://api.github.com/repos/{owner_repo}/issues"
            f"?state=open&per_page=100&page={page}&sort=updated&direction=desc"
        )
        batch = request_json(url, token=token)
        if not batch:
            return
        yield from batch
        if len(batch) < 100:
            return


def render_markdown(bounties: list[Bounty], repo: str) -> str:
    stamp = dt.datetime.now(dt.UTC).replace(microsecond=0).isoformat()
    lines = [
        f"# RustChain Bounty Radar for `{repo}`",
        "",
        f"Generated: `{stamp}`",
        "",
        "| Rank | Issue | Reward | Score | Signals |",
        "| ---: | --- | ---: | ---: | --- |",
    ]
    for rank, bounty in enumerate(bounties, start=1):
        reward = (
            f"{bounty.reward_rtc:g}-{bounty.max_reward_rtc:g} RTC"
            if bounty.reward_rtc != bounty.max_reward_rtc
            else f"{bounty.max_reward_rtc:g} RTC"
        )
        signals = ", ".join(bounty.signals[:3]) or "reward detected"
        title = bounty.title.replace("|", "\\|")
        lines.append(
            f"| {rank} | [#{bounty.number} {title}]({bounty.url}) | "
            f"{reward} | {bounty.score:g} | {signals} |"
        )
    lines.append("")
    return "\n".join(lines)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--repo", default=DEFAULT_REPO, help="owner/repo to scan")
    parser.add_argument("--pages", type=int, default=2, help="issue-list pages to fetch")
    parser.add_argument("--limit", type=int, default=15, help="ranked rows to output")
    parser.add_argument("--min-reward", type=float, default=0.1, help="minimum detected RTC reward")
    parser.add_argument("--token", default=None, help="optional GitHub token")
    parser.add_argument("--json", action="store_true", help="emit JSON instead of Markdown")
    parser.add_argument(
        "--include-non-tasks",
        action="store_true",
        help="include claim and payout-status issues in the ranking",
    )
    args = parser.parse_args(argv)

    try:
        issues = list(fetch_open_issues(args.repo, args.pages, args.token))
    except urllib.error.HTTPError as exc:
        print(f"GitHub API error {exc.code}: {exc.reason}", file=sys.stderr)
        return 2

    bounties = [
        bounty
        for issue in issues
        if (bounty := issue_to_bounty(issue)) and bounty.max_reward_rtc >= args.min_reward
    ]
    if not args.include_non_tasks:
        bounties = [bounty for bounty in bounties if not is_non_task_issue(bounty.title)]
    bounties.sort(key=lambda item: (item.score, item.max_reward_rtc), reverse=True)
    selected = bounties[: args.limit]

    if args.json:
        print(json.dumps([asdict(bounty) for bounty in selected], indent=2))
    else:
        print(render_markdown(selected, args.repo))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
