# Tracking stats from your Mac

The NBA stats site blocks GitHub's servers, so the few stats that only exist
there are pulled from your Mac instead and pushed to the repo:

- **Tracking:** potential assists, rebound chances, touches, drives, catch-and-shoot,
  pull-ups, paint, post and elbow touches, defense at the rim, speed and distance
- **Usage and advanced:** usage rate, pace, efficiency, scoring breakdown
- **Hustle:** deflections, box-outs, contested shots, loose balls
- **Defender matchups:** who guarded whom, for the season and game by game

Everything else on the site comes from GitHub on its own, so if your Mac is
off, only these stats pause. The site shows the date they were last updated.

## One-time setup (about 10 minutes)

All of this is typed in **Terminal** (Applications > Utilities > Terminal).

1. **Install Apple's developer tools** (Python 3 and git). Skip if you already
   use git in Terminal.

   ```
   xcode-select --install
   ```

2. **Get the repo onto your Mac**, outside Desktop, Documents and Downloads
   (macOS blocks scheduled jobs from reading those folders):

   ```
   mkdir -p ~/code && cd ~/code
   git clone https://github.com/Drilium/court-script.git
   cd court-script
   ```

3. **Check the NBA site answers from your network** (one request):

   ```
   python3 local/tracking_mac.py --check
   ```

4. **Run the first pull.** This backfills every game so far, about 10 minutes
   in mid-November, and pushes the files. If git asks you to sign in to GitHub,
   do it here once; your Mac remembers it for the scheduled runs.

   ```
   python3 local/tracking_mac.py
   ```

5. **Schedule it for every morning** (9:20am by default, after last night's
   tracking data is posted):

   ```
   bash local/install_mac.sh
   ```

## Day to day

Nothing to do. Each morning it pulls last night's games (under a minute) and
pushes. If the Mac is asleep at 9:20 it runs when it wakes. If a run fails,
you get a Mac notification.

| Task | Command |
| --- | --- |
| Run now | `launchctl kickstart gui/$(id -u)/com.drilium.courtscript.tracking` |
| Read the log | `tail -50 ~/Library/Logs/court-script/tracking.log` |
| Change the time (e.g. 7:45am) | `bash local/install_mac.sh 7 45` |
| Stop the daily run | `bash local/install_mac.sh --remove` |
| Pull without pushing | `python3 local/tracking_mac.py --no-push` |

## Being a good guest

The script waits 1.2 to 1.8 seconds between requests, downloads each game only
once (cached in `local/.cache`), and stops after 5 failures in a row rather
than hammering the site. If it stops early it keeps what it got and finishes on
the next run. Pulling faster is how home addresses get temporarily blocked, so
leave `--delay` alone.

## If the sign-in prompt keeps coming back

Scheduled runs can't type a password. If pushes fail in the log with an
authentication error, set up the GitHub CLI once and it handles sign-in:

```
brew install gh   # or download from cli.github.com
gh auth login     # choose GitHub.com, HTTPS, and log in with a browser
gh auth setup-git
```
