from __future__ import annotations

import json
from pathlib import Path

from analyze_black_speech_fouls import (
    GAMES_DIR,
    ROLE_CIVILIAN,
    ROLE_DON,
    ROLE_MAFIA,
    ROLE_SHERIFF,
    load_tracked_players,
    payload_in_period,
)
from analyze_mafia_day1_votes import pct
from analyze_ugadayka import replay
from script import DATE_FROM, DATE_TO

OUT_SUMMARY = Path("data/offline_tournament/analysis_first_voted.csv")
OUT_OVERALL = Path("data/offline_tournament/analysis_first_voted_overall.csv")

NOTE = (
    f"Период {DATE_FROM} — {DATE_TO}. Первый уход со стола голосованием: "
    "кто вылетел на первом состоявшемся голосовании партии (обычно день 2 "
    "после ночного отстрела; в оффлайн-турнирах Polemica в 1-й день голосования почти нет). "
    "Ночной отстрел не считается. Любая роль. "
    "Если на первом круге ничья и со стола уходят несколько — все они первый вылет. "
    "Случайный уровень ~11.1% (1 из 9 живых после первого отстрела)."
)


def empty_stats() -> dict:
    return {
        "games": 0,
        "games_with_first_vote_out": 0,
        "first_voted": 0,
        "as_civilian": 0,
        "as_sheriff": 0,
        "as_mafia": 0,
        "as_don": 0,
        "day2": 0,
        "day3plus": 0,
        "solo_elim": 0,
        "multi_elim": 0,
        "unique_games": 0,
        "unique_with_vote_out": 0,
    }


def first_vote_out(state: dict) -> dict | None:
    elims = state.get("vote_elims") or []
    if not elims:
        return None
    first = elims[0]
    return {"day": first["day"], "seats": list(first["seats"])}


def apply_role(stats: dict, role: int | None) -> None:
    if role == ROLE_CIVILIAN:
        stats["as_civilian"] += 1
    elif role == ROLE_SHERIFF:
        stats["as_sheriff"] += 1
    elif role == ROLE_MAFIA:
        stats["as_mafia"] += 1
    elif role == ROLE_DON:
        stats["as_don"] += 1


def analyze() -> tuple[dict[int, dict], dict]:
    tracked = load_tracked_players()
    per_player = {user_id: empty_stats() | dict(meta) for user_id, meta in tracked.items()}
    overall = empty_stats()
    unique_games = 0
    unique_with = 0

    for path in sorted(GAMES_DIR.glob("*.json"), key=lambda item: int(item.stem)):
        payload = json.loads(path.read_text(encoding="utf-8"))
        if not payload_in_period(payload):
            continue
        inner = (payload.get("data") or {}).get("players") or []
        if len(inner) < 10:
            continue
        unique_games += 1
        state = replay(payload)
        found = first_vote_out(state)
        if found:
            unique_with += 1
        first_seats = set(found["seats"]) if found else set()
        first_day = found["day"] if found else None
        multi = len(first_seats) > 1

        for player in inner:
            user_id = player.get("player")
            pos = player.get("position")
            if user_id not in tracked or pos is None:
                continue
            user_id = int(user_id)
            pos = int(pos)
            role = player.get("role")
            buckets = [per_player[user_id], overall]
            for stats in buckets:
                stats["games"] += 1
                if found:
                    stats["games_with_first_vote_out"] += 1
                if pos not in first_seats:
                    continue
                stats["first_voted"] += 1
                apply_role(stats, role)
                if first_day == 2:
                    stats["day2"] += 1
                elif first_day is not None and first_day >= 3:
                    stats["day3plus"] += 1
                if multi:
                    stats["multi_elim"] += 1
                else:
                    stats["solo_elim"] += 1

    overall["unique_games"] = unique_games
    overall["unique_with_vote_out"] = unique_with
    return per_player, overall


def row_from_stats(stats: dict, label: str | None = None) -> dict:
    games = stats["games"]
    first = stats["first_voted"]
    return {
        "poster_nick": stats.get("poster_nick") or label or "ALL",
        "polemica_nick": stats.get("polemica_nick") or "",
        "user_id": stats.get("user_id") or "",
        "games": games,
        "games_with_first_vote_out": stats["games_with_first_vote_out"],
        "first_voted": first,
        "pct_first_voted": pct(first, games),
        "as_civilian": stats["as_civilian"],
        "as_sheriff": stats["as_sheriff"],
        "as_mafia": stats["as_mafia"],
        "as_don": stats["as_don"],
        "day2": stats["day2"],
        "day3plus": stats["day3plus"],
        "solo_elim": stats["solo_elim"],
        "multi_elim": stats["multi_elim"],
        "naive_random_pct": 11.1,
        "unique_games": stats.get("unique_games") or "",
        "unique_with_vote_out": stats.get("unique_with_vote_out") or "",
        "note": NOTE,
    }


def sort_rows(rows: list[dict]) -> list[dict]:
    return sorted(
        rows,
        key=lambda row: (
            row["pct_first_voted"] is None,
            -(row["pct_first_voted"] or 0),
            -(row["first_voted"] or 0),
            -(row["games"] or 0),
            row["poster_nick"],
        ),
    )


def main() -> None:
    from export_analysis_csv import main as export_main

    export_main()


if __name__ == "__main__":
    main()
