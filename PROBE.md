# Data source check

Run from a GitHub Actions runner on 2026-11-16 16:14 UTC.

| Group | Source | Works | HTTP | Size | Time | Note |
| --- | --- | --- | --- | --- | --- | --- |
| NBA CDN | Today's scoreboard (tonight's games and live scores) | NO | 403 | 0 b | 0.07 s | Forbidden |
| NBA CDN | Season schedule (every game, date, status and game id) | NO | 403 | 0 b | 0.04 s | Forbidden |
| NBA stats site | Player stats (season averages for every player) | NO | no reply | 0 b | 25.08 s | TimeoutError: The read operation timed out |
| NBA stats site | Usage and advanced (usage rate, pace, efficiency) | NO | no reply | 0 b | 25.06 s | TimeoutError: The read operation timed out |
| NBA stats site | Tracking: passing (potential assists) | NO | no reply | 0 b | 25.09 s | TimeoutError: The read operation timed out |
| NBA stats site | Tracking: rebounding (rebound chances) | NO | no reply | 0 b | 25.06 s | TimeoutError: The read operation timed out |
| NBA stats site | Defender matchups (who guarded whom, season totals) | NO | no reply | 0 b | 25.08 s | TimeoutError: The read operation timed out |
| NBA stats site | Game log (every player's line in every game) | NO | no reply | 0 b | 25.03 s | TimeoutError: The read operation timed out |
| Injuries | Official injury report (PDF) (every status and reason, reissued through the day) | yes | 200 | 93,076 b | 0.06 s | latest found: 2026-11-16 11_00AM |
| ESPN | Scoreboard (schedule, scores, lines) | yes | 200 | 159,589 b | 0.06 s | 8 games |
| ESPN | Injuries (status and notes for every team) | yes | 200 | 1,157,669 b | 0.03 s | 27 teams |
| ESPN | Game summary (box score and play-by-play) | yes | 200 | 126,155 b | 0.04 s | 0 plays |
| GitHub bulk data | shufinskiy/nba_data index (play-by-play, shots and matchups for past seasons) | yes | 200 | 52,430 b | 0.04 s | past seasons only (latest NBA season listed: 2025-26) |

## Summary

- **NBA CDN**: 0 of 2 working
- **NBA stats site**: 0 of 6 working
- **Injuries**: 1 of 1 working
- **ESPN**: 3 of 3 working
- **GitHub bulk data**: 1 of 1 working
