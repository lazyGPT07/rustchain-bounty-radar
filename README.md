# RustChain Bounty Radar

`bounty_radar.py` scans open issues in `Scottcjn/rustchain-bounties`, extracts RTC reward values, and ranks likely tasks by reward, friction, and crowding.

It is intentionally small: Python standard library only, no API keys required for public scans.

## Quick Start

```sh
python bounty_radar.py --limit 10
```

Optional authenticated scan:

```sh
python bounty_radar.py --token "$GITHUB_TOKEN" --pages 5 --json
```

## What It Detects

- RTC rewards written as `5 RTC`, `30-50 RTC`, or similar.
- Low-friction labels such as `good first issue`, `easy`, `community`, `micro`, and `ongoing`.
- Friction signals such as Discord, social media, or YouTube requirements.
- Existing claim issues, which are down-ranked so agents do not accidentally chase somebody else's claim.
- Crowded threads, which are slightly down-ranked because duplicates are less useful.

## Example

An example report is included at [`examples/latest-radar.md`](examples/latest-radar.md).

## Why This Helps RustChain

RustChain has many active micro-bounties. Agents and new contributors often waste time sorting claims from real tasks, reading crowded threads, and estimating which issues are actionable. This tool turns that discovery step into a repeatable report.

## Claim Metadata

- GitHub: `lazyGPT07`
- RTC wallet/miner ID: `RTC6d4ad0640a1543cc32f1e7c89375ba4c51228b2a`
