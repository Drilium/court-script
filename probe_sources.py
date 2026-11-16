#!/usr/bin/env python3
"""Phase 1 data proof: which NBA data sources answer from this machine?

Run on a GitHub Actions runner (see .github/workflows/probe.yml) to learn
which sources the daily pipeline can rely on. Standard library only.
Writes probe_report.json and PROBE.md next to this file.
"""
import datetime as dt
import gzip
import json
import os
import time
import urllib.error
import urllib.request

HERE = os.path.dirname(os.path.abspath(__file__))
UA = ("Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
      "(KHTML, like Gecko) Chrome/130.0 Safari/537.36")
STATS_HEADERS = {
    "User-Agent": UA,
    "Accept": "application/json, text/plain, */*",
    "Accept-Language": "en-US,en;q=0.9",
    "Accept-Encoding": "gzip",
    "Origin": "https://www.nba.com",
    "Referer": "https://www.nba.com/",
    "x-nba-stats-origin": "stats",
    "x-nba-stats-token": "true",
}
SEASON = "2026-27"


def fetch(url, headers=None, timeout=25):
    """Return (status, bytes, seconds, body or None, error text)."""
    req = urllib.request.Request(url, headers=headers or {"User-Agent": UA, "Accept-Encoding": "gzip"})
    t0 = time.time()
    try:
        with urllib.request.urlopen(req, timeout=timeout) as r:
            body = r.read()
            if r.headers.get("Content-Encoding") == "gzip":
                body = gzip.decompress(body)
            return r.status, len(body), round(time.time() - t0, 2), body, ""
    except urllib.error.HTTPError as e:
        return e.code, 0, round(time.time() - t0, 2), None, str(e.reason)
    except Exception as e:  # timeouts, resets, DNS
        return 0, 0, round(time.time() - t0, 2), None, type(e).__name__ + ": " + str(e)[:120]


def stats_url(endpoint, **params):
    q = "&".join(f"{k}={v}" for k, v in params.items())
    return f"https://stats.nba.com/stats/{endpoint}?{q}"


def main():
    results = []

    def probe(group, name, gives, url, headers=None, check=None):
        status, size, secs, body, err = fetch(url, headers)
        ok = status == 200 and size > 200
        note = err
        if ok and check:
            try:
                note = check(body)
            except Exception as e:
                ok, note = False, "unexpected shape: " + type(e).__name__
        results.append(dict(group=group, name=name, gives=gives, url=url, status=status,
                            bytes=size, seconds=secs, ok=ok, note=note))
        print(("OK  " if ok else "FAIL"), status, f"{size:>9}b", f"{secs:>5}s", name, "|", note)
        return body if ok else None

    # --- NBA live data CDN -------------------------------------------------
    probe("NBA CDN", "Today's scoreboard", "tonight's games and live scores",
          "https://cdn.nba.com/static/json/liveData/scoreboard/todaysScoreboard_00.json",
          check=lambda b: f"{len(json.loads(b)['scoreboard']['games'])} games today")
    sched = probe("NBA CDN", "Season schedule", "every game, date, status and game id",
                  "https://cdn.nba.com/static/json/staticData/scheduleLeagueV2_1.json",
                  check=lambda b: json.loads(b)["leagueSchedule"]["seasonYear"])
    gid = None
    if sched:
        for d in json.loads(sched)["leagueSchedule"]["gameDates"]:
            for g in d["games"]:
                if g.get("gameStatus") == 3 and str(g.get("gameId", "")).startswith("002"):
                    gid = g["gameId"]
    if gid:
        probe("NBA CDN", "Box score", "minutes and full stat lines per player",
              f"https://cdn.nba.com/static/json/liveData/boxscore/boxscore_{gid}.json",
              check=lambda b: "game " + json.loads(b)["game"]["gameId"])
        probe("NBA CDN", "Play-by-play", "every event, for lineups and with/without splits",
              f"https://cdn.nba.com/static/json/liveData/playbyplay/playbyplay_{gid}.json",
              check=lambda b: f"{len(json.loads(b)['game']['actions'])} events")

    # --- NBA stats site ----------------------------------------------------
    base = dict(Season=SEASON, SeasonType="Regular+Season", PerMode="PerGame", LeagueID="00")
    rows = lambda b: f"{len(json.loads(b)['resultSets'][0]['rowSet'])} rows"
    probe("NBA stats site", "Player stats", "season averages for every player",
          stats_url("leaguedashplayerstats", MeasureType="Base", LastNGames=0, Month=0,
                    OpponentTeamID=0, PaceAdjust="N", Period=0, PlusMinus="N", Rank="N", TeamID=0, **base),
          STATS_HEADERS, rows)
    probe("NBA stats site", "Usage and advanced", "usage rate, pace, efficiency",
          stats_url("leaguedashplayerstats", MeasureType="Advanced", LastNGames=0, Month=0,
                    OpponentTeamID=0, PaceAdjust="N", Period=0, PlusMinus="N", Rank="N", TeamID=0, **base),
          STATS_HEADERS, rows)
    probe("NBA stats site", "Tracking: passing", "potential assists",
          stats_url("leaguedashptstats", PtMeasureType="Passing", PlayerOrTeam="Player", LastNGames=0,
                    Month=0, OpponentTeamID=0, **base), STATS_HEADERS, rows)
    probe("NBA stats site", "Tracking: rebounding", "rebound chances",
          stats_url("leaguedashptstats", PtMeasureType="Rebounding", PlayerOrTeam="Player", LastNGames=0,
                    Month=0, OpponentTeamID=0, **base), STATS_HEADERS, rows)
    probe("NBA stats site", "Defender matchups", "who guarded whom, season totals",
          stats_url("leagueseasonmatchups", **base), STATS_HEADERS, rows)
    probe("NBA stats site", "Game log", "every player's line in every game",
          stats_url("leaguegamelog", Counter=0, Direction="DESC", PlayerOrTeam="P",
                    Season=SEASON, SeasonType="Regular+Season", Sorter="DATE", LeagueID="00"),
          STATS_HEADERS, rows)

    # --- Official injury report (PDF, reissued through the day) --------------
    now_et = dt.datetime.utcnow() - dt.timedelta(hours=5)
    found = False
    for back in range(0, 30):  # walk back in 15 minute steps until one exists
        t = now_et - dt.timedelta(minutes=15 * back)
        t = t.replace(minute=t.minute - t.minute % 15)
        for stamp in (t.strftime("%I_%M%p"), t.strftime("%I%p")):
            url = f"https://ak-static.cms.nba.com/referee/injury/Injury-Report_{t:%Y-%m-%d}_{stamp}.pdf"
            status, size, secs, body, err = fetch(url, timeout=15)
            if status == 200 and body and body[:4] == b"%PDF":
                results.append(dict(group="Injuries", name="Official injury report (PDF)",
                                    gives="every status and reason, reissued through the day",
                                    url=url, status=200, bytes=size, seconds=secs, ok=True,
                                    note=f"latest found: {t:%Y-%m-%d} {stamp}"))
                print("OK  ", 200, f"{size:>9}b", "injury PDF", stamp)
                found = True
                break
        if found:
            break
    if not found:
        results.append(dict(group="Injuries", name="Official injury report (PDF)",
                            gives="every status and reason, reissued through the day",
                            url="https://ak-static.cms.nba.com/referee/injury/", status=status,
                            bytes=0, seconds=0, ok=False, note="no report file found in the last 7 hours: " + err))
        print("FAIL injury PDF", status, err)

    # --- ESPN public JSON (backup) -------------------------------------------
    sb = probe("ESPN", "Scoreboard", "schedule, scores, lines",
               "https://site.api.espn.com/apis/site/v2/sports/basketball/nba/scoreboard",
               check=lambda b: f"{len(json.loads(b)['events'])} games")
    probe("ESPN", "Injuries", "status and notes for every team",
          "https://site.api.espn.com/apis/site/v2/sports/basketball/nba/injuries",
          check=lambda b: f"{len(json.loads(b)['injuries'])} teams")
    if sb:
        ev = json.loads(sb)["events"]
        if ev:
            probe("ESPN", "Game summary", "box score and play-by-play",
                  f"https://site.api.espn.com/apis/site/v2/sports/basketball/nba/summary?event={ev[0]['id']}",
                  check=lambda b: f"{len(json.loads(b).get('plays', []))} plays")

    # --- Bulk history on GitHub ----------------------------------------------
    probe("GitHub bulk data", "shufinskiy/nba_data index", "play-by-play, shots and matchups for past seasons",
          "https://raw.githubusercontent.com/shufinskiy/nba_data/main/list_data.txt",
          check=lambda b: "NBA 2026 season listed" if b"\nnbastatsv3_2026=" in b
          else "past seasons only (latest NBA season listed: 2025-26)")

    # --- Report --------------------------------------------------------------
    stamp = dt.datetime.utcnow().strftime("%Y-%m-%d %H:%M UTC")
    where = "GitHub Actions runner" if os.environ.get("GITHUB_ACTIONS") else "local machine"
    with open(os.path.join(HERE, "probe_report.json"), "w") as f:
        json.dump(dict(generated=stamp, where=where, results=results), f, indent=1)
    lines = [f"# Data source check", "", f"Run from a {where} on {stamp}.", "",
             "| Group | Source | Works | HTTP | Size | Time | Note |", "| --- | --- | --- | --- | --- | --- | --- |"]
    for r in results:
        lines.append(f"| {r['group']} | {r['name']} ({r['gives']}) | {'yes' if r['ok'] else 'NO'} | "
                     f"{r['status'] or 'no reply'} | {r['bytes']:,} b | {r['seconds']} s | {r['note']} |")
    by = {}
    for r in results:
        by.setdefault(r["group"], []).append(r["ok"])
    lines += ["", "## Summary", ""]
    for g, oks in by.items():
        lines.append(f"- **{g}**: {sum(oks)} of {len(oks)} working")
    with open(os.path.join(HERE, "PROBE.md"), "w") as f:
        f.write("\n".join(lines) + "\n")
    print("\nWrote PROBE.md and probe_report.json")


if __name__ == "__main__":
    main()
