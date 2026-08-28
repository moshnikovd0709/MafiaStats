from __future__ import annotations

import json
from pathlib import Path

from analyze_black_speech_fouls import (
    GAMES_DIR,
    ROLE_CIVILIAN,
    load_tracked_players,
    payload_in_period,
)
from analyze_mafia_day1_votes import classify_target, first_vote_for, pct
from script import DATE_FROM, DATE_TO

OUT_SUMMARY = Path("data/offline_tournament/analysis_civilian_first_votes.csv")
OUT_OVERALL = Path("data/offline_tournament/analysis_civilian_first_votes_overall.csv")

NOTE = (
    f"Период {DATE_FROM} — {DATE_TO}. Только роль мирный, не шериф. "
    "Голос = первый кружок голосования (votes.num>=1) в первый день, "
    "где в протоколе вообще было голосование. "
    "В оффлайн-турнирах Polemica это обычно день 2 после первого отстрела."
)


def empty_stats() -> dict:
    return {
        "civilian_games": 0,
        "games_with_vote": 0,
        "games_no_vote": 0,
        "voted_sheriff": 0,
        "voted_civilian": 0,
        "voted_don": 0,
        "voted_mafia": 0,
        "voted_black": 0,
        "voted_self": 0,
        "voted_unknown": 0,
    }


def apply_vote(stats: dict, bucket: str) -> None:
    if bucket == "sheriff":
        stats["voted_sheriff"] += 1
    elif bucket == "civilian":
        stats["voted_civilian"] += 1
    elif bucket == "own_don":
        stats["voted_don"] += 1
        stats["voted_black"] += 1
    elif bucket == "own_mafia":
        stats["voted_mafia"] += 1
        stats["voted_black"] += 1
    elif bucket == "self":
        stats["voted_self"] += 1
    else:
        stats["voted_unknown"] += 1


def analyze() -> tuple[dict[int, dict], dict]:
    tracked = load_tracked_players()
    per_player = {user_id: empty_stats() | dict(meta) for user_id, meta in tracked.items()}
    overall = empty_stats()

    for path in sorted(GAMES_DIR.glob("*.json"), key=lambda item: int(item.stem)):
        payload = json.loads(path.read_text(encoding="utf-8"))
        if not payload_in_period(payload):
            continue
        data = payload.get("data") or {}
        inner_players = data.get("players") or []
        by_pos = {
            int(item["position"]): item
            for item in inner_players
            if item.get("position") is not None
        }
        votes = data.get("votes") or []

        for player in inner_players:
            user_id = player.get("player")
            role = player.get("role")
            pos = player.get("position")
            if user_id not in tracked or role != ROLE_CIVILIAN or pos is None:
                continue
            user_id = int(user_id)
            pos = int(pos)
            stats = per_player[user_id]
            stats["civilian_games"] += 1
            overall["civilian_games"] += 1

            vote = first_vote_for(votes, pos)
            if vote is None:
                stats["games_no_vote"] += 1
                overall["games_no_vote"] += 1
                continue
            stats["games_with_vote"] += 1
            overall["games_with_vote"] += 1
            bucket = classify_target(pos, vote.get("candidate"), by_pos)
            apply_vote(stats, bucket)
            apply_vote(overall, bucket)

    return per_player, overall


def row_from_stats(stats: dict, label: str | None = None) -> dict:
    voted = stats["games_with_vote"]
    return {
        "poster_nick": stats.get("poster_nick") or label or "ALL",
        "polemica_nick": stats.get("polemica_nick") or "",
        "user_id": stats.get("user_id") or "",
        "civilian_games": stats["civilian_games"],
        "voted_civilian": stats["voted_civilian"],
        "voted_don": stats["voted_don"],
        "voted_mafia": stats["voted_mafia"],
        "voted_black": stats["voted_black"],
        "voted_self": stats["voted_self"],
        "voted_unknown": stats["voted_unknown"],
        "pct_sheriff": pct(stats["voted_sheriff"], voted),
        "pct_civilian": pct(stats["voted_civilian"], voted),
        "pct_don": pct(stats["voted_don"], voted),
        "pct_mafia": pct(stats["voted_mafia"], voted),
        "pct_black": pct(stats["voted_black"], voted),
        "note": NOTE,
    }


def main() -> None:
    from export_analysis_csv import main as export_main

    export_main()


if __name__ == "__main__":
    main()
