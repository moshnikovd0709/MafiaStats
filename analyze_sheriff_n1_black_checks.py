from __future__ import annotations

import json
from pathlib import Path

from analyze_black_speech_fouls import (
    BLACK_ROLES,
    GAMES_DIR,
    ROLE_DON,
    ROLE_MAFIA,
    ROLE_SHERIFF,
    load_tracked_players,
    payload_in_period,
)
from analyze_mafia_day1_votes import pct
from script import DATE_FROM, DATE_TO

OUT_SUMMARY = Path("data/offline_tournament/analysis_sheriff_n1_black_checks.csv")
OUT_OVERALL = Path("data/offline_tournament/analysis_sheriff_n1_black_checks_overall.csv")
SHERIFF_NIGHT = 1

NOTE = (
    f"Период {DATE_FROM} — {DATE_TO}. Только чёрная карта (мафия или дон). "
    "Проверка шерифа в первую ночь = checks.night==1 и checks.role==3. "
    "Случайный уровень ~11.1% (1 из 9 чужих мест)."
)


def empty_stats() -> dict:
    return {
        "black_games": 0,
        "mafia_games": 0,
        "don_games": 0,
        "checked_n1": 0,
        "checked_n1_as_mafia": 0,
        "checked_n1_as_don": 0,
        "games_with_sheriff_n1": 0,
    }


def sheriff_n1_target(checks: list[dict]) -> int | None:
    targets = [
        item.get("player")
        for item in checks
        if item.get("role") == ROLE_SHERIFF and item.get("night") == SHERIFF_NIGHT
    ]
    if not targets or targets[0] is None:
        return None
    try:
        return int(targets[0])
    except (TypeError, ValueError):
        return None


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
        checks = data.get("checks") or []
        n1_target = sheriff_n1_target(checks)
        had_n1 = n1_target is not None

        for player in inner_players:
            user_id = player.get("player")
            role = player.get("role")
            pos = player.get("position")
            if user_id not in tracked or role not in BLACK_ROLES or pos is None:
                continue
            user_id = int(user_id)
            pos = int(pos)
            stats = per_player[user_id]
            stats["black_games"] += 1
            overall["black_games"] += 1
            if role == ROLE_MAFIA:
                stats["mafia_games"] += 1
                overall["mafia_games"] += 1
            else:
                stats["don_games"] += 1
                overall["don_games"] += 1
            if had_n1:
                stats["games_with_sheriff_n1"] += 1
                overall["games_with_sheriff_n1"] += 1
            if n1_target != pos:
                continue
            stats["checked_n1"] += 1
            overall["checked_n1"] += 1
            if role == ROLE_MAFIA:
                stats["checked_n1_as_mafia"] += 1
                overall["checked_n1_as_mafia"] += 1
            else:
                stats["checked_n1_as_don"] += 1
                overall["checked_n1_as_don"] += 1

    return per_player, overall


def row_from_stats(stats: dict, label: str | None = None) -> dict:
    black = stats["black_games"]
    return {
        "poster_nick": stats.get("poster_nick") or label or "ALL",
        "polemica_nick": stats.get("polemica_nick") or "",
        "user_id": stats.get("user_id") or "",
        "black_games": black,
        "mafia_games": stats["mafia_games"],
        "don_games": stats["don_games"],
        "sheriff_n1_checked": stats["checked_n1"],
        "sheriff_n1_checked_as_mafia": stats["checked_n1_as_mafia"],
        "sheriff_n1_checked_as_don": stats["checked_n1_as_don"],
        "pct_sheriff_n1_on_black": pct(stats["checked_n1"], black),
        "games_with_sheriff_n1": stats["games_with_sheriff_n1"],
        "naive_random_pct": 11.1,
        "note": NOTE,
    }


def main() -> None:
    from export_analysis_csv import main as export_main

    export_main()


if __name__ == "__main__":
    main()
