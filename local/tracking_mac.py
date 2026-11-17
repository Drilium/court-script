#!/usr/bin/env python3
"""Court Script: NBA tracking stats, pulled from your Mac.

The NBA stats site (stats.nba.com) blocks GitHub's servers but not home
internet. This script runs on your Mac, pulls the stats only that site has,
writes two data files at the repo root and pushes them to GitHub:

  nba_tracking.json        season totals: tracking (potential assists, rebound
                           chances, drives, touches, catch-and-shoot, pull-ups,
                           defense at the rim...), usage/advanced, hustle, and
                           season defender matchups (who guarded whom)
  nba_tracking_games.json  game by game: player tracking and defender matchups

First run backfills every game played so far (about 10 minutes); after that a
daily run takes under a minute. Raw game files are cached in local/.cache so
a game is only ever downloaded once.

Usage (from the repo folder):
  python3 local/tracking_mac.py            pull, write, commit and push
  python3 local/tracking_mac.py --check    one request, to see if the site answers
  python3 local/tracking_mac.py --no-push  pull and write, but don't commit
  python3 local/tracking_mac.py --help     all options

Standard library only, and works with the Python 3.9 that ships with macOS.
"""
import argparse
import datetime as dt
import gzip
import json
import os
import random
import subprocess
import sys
import time
import urllib.error
import urllib.parse
import urllib.request
import zlib

HERE = os.path.dirname(os.path.abspath(__file__))
REPO = os.path.dirname(HERE)
CACHE = os.path.join(HERE, ".cache")
OUT_SEASON = os.path.join(REPO, "nba_tracking.json")
OUT_GAMES = os.path.join(REPO, "nba_tracking_games.json")

BASE = "https://stats.nba.com/stats/"
# Same browser headers the open-source nba_api library sends (minus brotli,
# which Python's standard library can't decode).
HEADERS = {
    "User-Agent": ("Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 "
                   "(KHTML, like Gecko) Chrome/145.0.0.0 Safari/537.36"),
    "Accept": "application/json, text/plain, */*",
    "Accept-Language": "en-US,en;q=0.5",
    "Accept-Encoding": "gzip, deflate",
    "Connection": "keep-alive",
    "Referer": "https://www.nba.com/",
    "Origin": "https://www.nba.com",
    "Pragma": "no-cache",
    "Cache-Control": "no-cache",
    "Sec-Ch-Ua": '"Not:A-Brand";v="99", "Google Chrome";v="145", "Chromium";v="145"',
    "Sec-Ch-Ua-Mobile": "?0",
    "Sec-Fetch-Dest": "empty",
    "Sec-Fetch-Mode": "cors",
    "Sec-Fetch-Site": "same-site",
}

# Tracking families from the NBA's player tracking pages. One request each
# returns every player in the league.
PT_MEASURES = ["Passing", "Rebounding", "Possessions", "Drives", "CatchShoot", "PullUpShot",
               "Defense", "Efficiency", "SpeedDistance", "PaintTouch", "PostTouch", "ElbowTouch"]

# Keep season matchup pairs with at least this many partial possessions, and
# game matchup pairs with at least this many, so the files stay small.
MIN_SEASON_POSS = 10
MIN_GAME_POSS = 3


def log(msg):
    print(dt.datetime.now().strftime("%H:%M:%S"), msg, flush=True)


def current_season(today=None):
    today = today or dt.date.today()
    start = today.year if today.month >= 9 else today.year - 1
    return f"{start}-{(start + 1) % 100:02d}"


def season_types(today=None):
    today = today or dt.date.today()
    types = ["Regular Season"]
    if 4 <= today.month <= 6:
        types += ["PlayIn", "Playoffs"]
    return types


class Blocked(Exception):
    """Too many failures in a row: stop and keep what we have."""


class Client:
    def __init__(self, delay, max_fail=5):
        self.delay = delay
        self.max_fail = max_fail
        self.fails_in_row = 0
        self.requests = 0
        self.last = 0.0

    def get(self, endpoint, params):
        url = BASE + endpoint + "?" + urllib.parse.urlencode(params)
        waits = [5, 20, 60]
        for attempt in range(len(waits) + 1):
            gap = time.time() - self.last
            pause = self.delay + random.uniform(0, self.delay / 2)
            if gap < pause:
                time.sleep(pause - gap)
            self.last = time.time()
            self.requests += 1
            try:
                req = urllib.request.Request(url, headers=HEADERS)
                with urllib.request.urlopen(req, timeout=45) as r:
                    body = r.read()
                    enc = r.headers.get("Content-Encoding", "")
                if enc == "gzip":
                    body = gzip.decompress(body)
                elif enc == "deflate":
                    body = zlib.decompress(body)
                data = json.loads(body)
                self.fails_in_row = 0
                return data
            except urllib.error.HTTPError as e:
                err = f"HTTP {e.code}"
                if e.code in (400, 404):  # bad request or no data: retrying won't help
                    log(f"  {endpoint}: {err}, skipping")
                    return None
            except Exception as e:  # timeout, reset, bad JSON
                err = type(e).__name__ + ": " + str(e)[:100]
            self.fails_in_row += 1
            if self.fails_in_row >= self.max_fail:
                raise Blocked(f"{self.fails_in_row} failures in a row (last: {err})")
            if attempt < len(waits):
                log(f"  {endpoint}: {err}, retrying in {waits[attempt]}s")
                time.sleep(waits[attempt])
        log(f"  {endpoint}: gave up after {len(waits) + 1} tries")
        return None


def league_params(season, stype, **extra):
    """The full parameter set the stats site expects on its league dashboards."""
    p = dict(College="", Conference="", Country="", DateFrom="", DateTo="", Division="",
             DraftPick="", DraftYear="", GameScope="", Height="", LastNGames=0, LeagueID="00",
             Location="", Month=0, OpponentTeamID=0, Outcome="", PORound=0, PerMode="PerGame",
             PlayerExperience="", PlayerPosition="", Season=season, SeasonSegment="",
             SeasonType=stype, StarterBench="", TeamID=0, VsConference="", VsDivision="",
             Weight="")
    p.update(extra)
    return p


def table(data, drop_ranks=True):
    """resultSets[0] as {"cols": [...], "rows": [[...]]}."""
    rs = data.get("resultSets") or data.get("resultSet")
    if isinstance(rs, dict):
        rs = [rs]
    if not rs:
        return None
    cols, rows = rs[0]["headers"], rs[0]["rowSet"]
    if drop_ranks:
        keep = [i for i, c in enumerate(cols) if not c.endswith("_RANK")]
        cols = [cols[i] for i in keep]
        rows = [[r[i] for i in keep] for r in rows]
    return {"cols": cols, "rows": rows}


# ---------------------------------------------------------------- season totals

def pull_season(client, season, stype, teams):
    out = {}
    for m in PT_MEASURES:
        d = client.get("leaguedashptstats", league_params(
            season, stype, PlayerOrTeam="Player", PtMeasureType=m))
        if d and table(d):
            out["pt_" + m] = table(d)
            log(f"  tracking {m}: {len(out['pt_' + m]['rows'])} players")
    for mt in ("Base", "Advanced", "Usage", "Misc", "Scoring"):
        d = client.get("leaguedashplayerstats", league_params(
            season, stype, MeasureType=mt, PaceAdjust="N", Period=0, PlusMinus="N", Rank="N",
            GameSegment="", ShotClockRange="", TwoWay=""))
        if d and table(d):
            out["dash_" + mt] = table(d)
            log(f"  {mt.lower()}: {len(out['dash_' + mt]['rows'])} players")
    d = client.get("leaguehustlestatsplayer", league_params(season, stype, PerMode="PerGame"))
    if d and table(d):
        out["hustle"] = table(d)
        log(f"  hustle: {len(out['hustle']['rows'])} players")

    # Season defender matchups, one request per offensive team.
    cols, rows = None, []
    for tid in sorted(teams):
        d = client.get("leagueseasonmatchups", dict(
            LeagueID="00", PerMode="Totals", Season=season, SeasonType=stype,
            DefPlayerID="", DefTeamID="", OffPlayerID="", OffTeamID=tid))
        t = d and table(d, drop_ranks=False)
        if not t:
            continue
        cols = t["cols"]
        ip = cols.index("PARTIAL_POSS") if "PARTIAL_POSS" in cols else None
        for r in t["rows"]:
            if ip is None or (r[ip] or 0) >= MIN_SEASON_POSS:
                rows.append(r)
    if cols:
        out["matchups"] = {"cols": cols, "rows": rows, "min_partial_poss": MIN_SEASON_POSS}
        log(f"  season matchups: {len(rows)} pairs with {MIN_SEASON_POSS}+ possessions")
    return out


# ---------------------------------------------------------------- game by game

def game_list(client, season, stype):
    d = client.get("leaguegamelog", dict(
        Counter=0, Direction="DESC", LeagueID="00", PlayerOrTeam="T", Season=season,
        SeasonType=stype, Sorter="DATE", DateFrom="", DateTo=""))
    t = d and table(d, drop_ranks=False)
    if not t:
        return {}, set()
    c = {k: i for i, k in enumerate(t["cols"])}
    games, teams = {}, set()
    for r in t["rows"]:
        games.setdefault(r[c["GAME_ID"]], r[c["GAME_DATE"]])
        teams.add(r[c["TEAM_ID"]])
    return games, teams


def cached_box(client, kind, gid, refresh_days, game_date):
    """Raw box score JSON for one game, from the cache when we have it."""
    path = os.path.join(CACHE, kind, gid + ".json.gz")
    if os.path.exists(path):
        try:
            recent = (dt.date.today() - dt.date.fromisoformat(game_date[:10])).days <= refresh_days
        except ValueError:
            recent = False
        age_h = (time.time() - os.path.getmtime(path)) / 3600
        if not (recent and age_h > 12):  # re-pull last night's games once, for stat corrections
            with gzip.open(path, "rt") as f:
                return json.load(f), False
    d = client.get(kind, {"GameID": gid})
    if d is None:
        return None, True
    root = d.get("boxScorePlayerTrack") or d.get("boxScoreMatchups")
    if not root or not (root.get("homeTeam") or {}).get("players"):
        return None, True  # tracking not posted yet: try again next run
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with gzip.open(path, "wt") as f:
        json.dump(d, f)
    return d, True


def flatten_track(d, cols):
    root = d.get("boxScorePlayerTrack", {})
    rows = []
    for side in ("homeTeam", "awayTeam"):
        team = root.get(side) or {}
        for p in team.get("players", []):
            s = p.get("statistics") or {}
            if not cols:
                cols.extend(k for k, v in s.items() if isinstance(v, (int, float)) or k == "minutes")
            if not s.get("minutes"):
                continue  # did not play
            rows.append([root.get("gameId"), team.get("teamId"), p.get("personId")]
                        + [s.get(k) for k in cols])
    return rows


def flatten_matchups(d, cols):
    """Each team's players are the offense; their "matchups" are the defenders on them."""
    root = d.get("boxScoreMatchups", {})
    rows = []
    for side in ("homeTeam", "awayTeam"):
        team = root.get(side) or {}
        for off in team.get("players", []):
            for m in off.get("matchups", []):
                s = m.get("statistics") or {}
                if not cols:
                    cols.extend(k for k, v in s.items()
                                if isinstance(v, (int, float)) and not k.lower().endswith("percentage"))
                if (s.get("partialPossessions") or 0) < MIN_GAME_POSS:
                    continue
                rows.append([root.get("gameId"), team.get("teamId"), off.get("personId"),
                             m.get("personId")] + [s.get(k) for k in cols])
    return rows


def pull_games(client, games, max_new, refresh_days):
    track_cols, match_cols, track_rows, match_rows = [], [], [], []
    new = done = missing = 0
    for gid, gdate in sorted(games.items(), key=lambda kv: kv[1]):
        got, fetched = True, False
        for kind in ("boxscoreplayertrackv3", "boxscorematchupsv3"):
            if max_new is not None and new >= max_new and not os.path.exists(
                    os.path.join(CACHE, kind, gid + ".json.gz")):
                got = False
                continue
            d, f = cached_box(client, kind, gid, refresh_days, gdate)
            new += f
            fetched = fetched or f
            if d is None:
                got = False
                continue
            if kind == "boxscoreplayertrackv3":
                track_rows += flatten_track(d, track_cols)
            else:
                match_rows += flatten_matchups(d, match_cols)
        done += got
        missing += not got
        if fetched and new % 40 == 0:
            log(f"  {done} of {len(games)} games ready ({new} downloaded this run)")
    log(f"  games: {done} complete, {missing} waiting, {new} files downloaded this run")
    return {
        "track": {"cols": ["GAME_ID", "TEAM_ID", "PLAYER_ID"] + track_cols, "rows": track_rows},
        "matchups": {"cols": ["GAME_ID", "OFF_TEAM_ID", "OFF_PLAYER_ID", "DEF_PLAYER_ID"] + match_cols,
                     "rows": match_rows, "min_partial_poss": MIN_GAME_POSS},
    }, done, missing


# ---------------------------------------------------------------- output and git

def git(*args):
    return subprocess.run(["git", "-C", REPO] + list(args), capture_output=True, text=True)


def write_json(path, obj):
    tmp = path + ".tmp"
    with open(tmp, "w") as f:
        json.dump(obj, f, separators=(",", ":"))
    os.replace(tmp, path)


def push(summary):
    git("add", os.path.basename(OUT_SEASON), os.path.basename(OUT_GAMES))
    if git("diff", "--cached", "--quiet").returncode == 0:
        log("No changes to push.")
        return True
    msg = f"Tracking data from Mac: {summary}"
    r = git("commit", "-m", msg)
    if r.returncode:
        log("git commit failed: " + r.stderr.strip())
        return False
    for _ in range(3):
        git("pull", "--rebase", "--autostash", "origin", "main")
        r = git("push", "origin", "HEAD:main")
        if r.returncode == 0:
            log("Pushed to GitHub.")
            return True
        time.sleep(5)
    log("git push failed: " + r.stderr.strip())
    return False


def notify(text):
    """A Mac notification, so a failed scheduled run doesn't go unnoticed."""
    try:
        subprocess.run(["osascript", "-e",
                        f'display notification "{text}" with title "Court Script tracking"'],
                       capture_output=True, timeout=10)
    except Exception:
        pass


def main():
    ap = argparse.ArgumentParser(description="Pull NBA tracking stats from stats.nba.com and push them to court-script.")
    ap.add_argument("--season", default=current_season(), help="for example 2026-27 (default: current)")
    ap.add_argument("--check", action="store_true", help="make one request and report whether the site answers")
    ap.add_argument("--no-push", action="store_true", help="write the files but don't commit or push")
    ap.add_argument("--season-only", action="store_true", help="skip the game-by-game files")
    ap.add_argument("--max-new", type=int, default=None, help="download at most this many new game files (testing)")
    ap.add_argument("--delay", type=float, default=1.2, help="seconds between requests (default 1.2)")
    ap.add_argument("--refresh-days", type=int, default=2, help="re-pull games this recent once, for stat corrections")
    a = ap.parse_args()

    client = Client(a.delay)
    log(f"Court Script tracking pull, season {a.season}")

    if a.check:
        try:
            games, teams = game_list(client, a.season, "Regular Season")
        except Blocked as e:
            games, teams = {}, set()
            log(str(e))
        if games:
            log(f"The NBA stats site answered: {len(games)} games played, {len(teams)} teams.")
            return 0
        log("No answer from the NBA stats site. Try again later, or from another network.")
        return 1

    if not a.no_push:
        r = git("pull", "--rebase", "--autostash", "origin", "main")
        if r.returncode:
            log("git pull failed (continuing): " + r.stderr.strip()[:200])

    t0 = time.time()
    season_out = {"generated": dt.datetime.now(dt.timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
                  "season": a.season, "source": "stats.nba.com via local/tracking_mac.py",
                  "season_types": {}}
    games_out = {"generated": season_out["generated"], "season": a.season, "season_types": {}}
    status, blocked = [], None
    try:
        for stype in season_types():
            games, teams = game_list(client, a.season, stype)
            if not games:
                log(f"{stype}: no games yet")
                continue
            log(f"{stype}: {len(games)} games played; pulling season totals")
            season_out["season_types"][stype] = pull_season(client, a.season, stype, teams)
            if not a.season_only:
                log(f"{stype}: game-by-game tracking and matchups")
                g, done, missing = pull_games(client, games, a.max_new, a.refresh_days)
                g["games_complete"], g["games_waiting"] = done, missing
                g["last_game_date"] = max(games.values())[:10]
                games_out["season_types"][stype] = g
                status.append(f"{stype} {done}/{len(games)} games")
    except Blocked as e:
        blocked = str(e)
        log(f"Stopped early: {blocked}. Saving what was pulled; the next run picks up the rest.")

    have_season = any(season_out["season_types"].values())
    if not have_season and not any(games_out["season_types"].values()):
        log("Nothing was pulled, so the existing files are left as they are.")
        notify("No data pulled from the NBA stats site. It may be blocking this network for now.")
        return 1

    # Never replace good season totals with an emptier partial pull.
    if os.path.exists(OUT_SEASON) and blocked:
        try:
            with open(OUT_SEASON) as f:
                old = json.load(f)
            for stype, tables in old.get("season_types", {}).items():
                fresh = season_out["season_types"].setdefault(stype, {})
                for k, v in tables.items():
                    fresh.setdefault(k, v)
        except Exception:
            pass
    season_out["complete"] = blocked is None
    if blocked:
        season_out["note"] = "partial pull: " + blocked
    write_json(OUT_SEASON, season_out)
    if games_out["season_types"]:
        write_json(OUT_GAMES, games_out)
    log(f"Wrote {os.path.basename(OUT_SEASON)}"
        + (f" and {os.path.basename(OUT_GAMES)}" if games_out["season_types"] else "")
        + f" ({client.requests} requests, {time.time() - t0:.0f}s)")

    if a.no_push:
        return 0 if not blocked else 2
    ok = push(", ".join(status) or "season totals")
    if not ok:
        notify("Pulled the data but couldn't push it to GitHub. See the log.")
        return 3
    if blocked:
        notify("Partial pull: the NBA stats site stopped answering. The next run will finish it.")
        return 2
    return 0


if __name__ == "__main__":
    sys.exit(main())
