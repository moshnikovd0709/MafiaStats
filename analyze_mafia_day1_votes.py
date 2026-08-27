from __future__ import annotations

import csv
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
from script import DATE_FROM, DATE_TO

OUT_SUMMARY = Path("data/offline_tournament/analysis_mafia_day1_votes.csv")
OUT_OVERALL = Path("data/offline_tournament/analysis_mafia_day1_votes_overall.csv")

NOTE = (
    f"Период {DATE_FROM} — {DATE_TO}. Только роль мафия, не дон. "
    "Голос = первый кружок голосования (votes.num>=1) в первый день, "
    "где в протоколе вообще было голосование. "
    "В оффлайн-турнирах Polemica в 1-й день голосования почти нет "
    "(zeroVoting=none), поэтому это обычно день 2 после первого отстрела. "
    "Красные = мирные; шериф отдельно; "
    "вторая мафия и дон считаются порознь."
)


def empty_stats() -> dict:
    return {
        "mafia_games": 0,
        "games_with_vote": 0,
        "games_no_vote": 0,
        "voted_civilian": 0,
        "voted_sheriff": 0,
        "voted_own_black": 0,
        "voted_own_don": 0,
        "voted_own_mafia": 0,
        "voted_self": 0,
        "voted_unknown": 0,
        "first_vote_on_protocol_day1": 0,
        "first_vote_on_protocol_day2plus": 0,
        "protocol_day1_ballot_games": 0,
        "protocol_day1_voted_civilian": 0,
        "protocol_day1_voted_sheriff": 0,
        "protocol_day1_voted_own_black": 0,
        "protocol_day1_voted_own_don": 0,
        "protocol_day1_voted_own_mafia": 0,
        "protocol_day1_voted_self": 0,
        "protocol_day1_no_ballot": 0,
    }


def ballot_num(vote: dict) -> int | None:
    num = vote.get("num")
    if num is None:
        return None
    try:
        num = int(num)
    except (TypeError, ValueError):
        return None
    return num if num >= 1 else None


def first_vote_for(votes: list[dict], voter_pos: int, day: int | None = None) -> dict | None:
    mine = []
    for vote in votes:
        if vote.get("voter") != voter_pos:
            continue
        if day is not None and vote.get("day") != day:
            continue
        num = ballot_num(vote)
        if num is None:
            continue
        vote_day = vote.get("day")
        if vote_day is None:
            continue
        mine.append((int(vote_day), num, vote))
    if not mine:
        return None
    mine.sort(key=lambda item: (item[0], item[1]))
    if day is None:
        first_day = mine[0][0]
        mine = [item for item in mine if item[0] == first_day]
    return mine[0][2]


def classify_target(voter_pos: int, candidate, by_pos: dict) -> str:
    if candidate is None:
        return "unknown"
    try:
        candidate = int(candidate)
    except (TypeError, ValueError):
        return "unknown"
    if candidate == voter_pos:
        return "self"
    target = by_pos.get(candidate)
    if not target:
        return "unknown"
    role = target.get("role")
    if role == ROLE_CIVILIAN:
        return "civilian"
    if role == ROLE_SHERIFF:
        return "sheriff"
    if role == ROLE_DON:
        return "own_don"
    if role == ROLE_MAFIA:
        return "own_mafia"
    return "unknown"


def apply_vote(stats: dict, bucket: str, prefix: str = "") -> None:
    if bucket == "civilian":
        stats[f"{prefix}voted_civilian"] += 1
    elif bucket == "sheriff":
        stats[f"{prefix}voted_sheriff"] += 1
    elif bucket == "own_don":
        stats[f"{prefix}voted_own_black"] += 1
        stats["voted_own_don"] += 1
    elif bucket == "own_mafia":
        stats[f"{prefix}voted_own_black"] += 1
        stats["voted_own_mafia"] += 1
    elif bucket == "self":
        stats[f"{prefix}voted_self"] += 1
    else:
        stats[f"{prefix}voted_unknown"] += 1


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
            if user_id not in tracked or role != ROLE_MAFIA or pos is None:
                continue
            user_id = int(user_id)
            pos = int(pos)
            stats = per_player[user_id]
            stats["mafia_games"] += 1
            overall["mafia_games"] += 1

            vote = first_vote_for(votes, pos)
            if vote is None:
                stats["games_no_vote"] += 1
                overall["games_no_vote"] += 1
            else:
                stats["games_with_vote"] += 1
                overall["games_with_vote"] += 1
                bucket = classify_target(pos, vote.get("candidate"), by_pos)
                apply_vote(stats, bucket)
                apply_vote(overall, bucket)
                if int(vote["day"]) == 1:
                    stats["first_vote_on_protocol_day1"] += 1
                    overall["first_vote_on_protocol_day1"] += 1
                else:
                    stats["first_vote_on_protocol_day2plus"] += 1
                    overall["first_vote_on_protocol_day2plus"] += 1

            day1_vote = first_vote_for(votes, pos, day=1)
            if day1_vote is None:
                stats["protocol_day1_no_ballot"] += 1
                overall["protocol_day1_no_ballot"] += 1
            else:
                stats["protocol_day1_ballot_games"] += 1
                overall["protocol_day1_ballot_games"] += 1
                bucket = classify_target(pos, day1_vote.get("candidate"), by_pos)
                if bucket == "civilian":
                    stats["protocol_day1_voted_civilian"] += 1
                    overall["protocol_day1_voted_civilian"] += 1
                elif bucket == "sheriff":
                    stats["protocol_day1_voted_sheriff"] += 1
                    overall["protocol_day1_voted_sheriff"] += 1
                elif bucket == "own_don":
                    stats["protocol_day1_voted_own_black"] += 1
                    overall["protocol_day1_voted_own_black"] += 1
                    stats["protocol_day1_voted_own_don"] += 1
                    overall["protocol_day1_voted_own_don"] += 1
                elif bucket == "own_mafia":
                    stats["protocol_day1_voted_own_black"] += 1
                    overall["protocol_day1_voted_own_black"] += 1
                    stats["protocol_day1_voted_own_mafia"] += 1
                    overall["protocol_day1_voted_own_mafia"] += 1
                elif bucket == "self":
                    stats["protocol_day1_voted_self"] += 1
                    overall["protocol_day1_voted_self"] += 1

    return per_player, overall


def pct(part: int, whole: int) -> float | None:
    if not whole:
        return None
    return round(100.0 * part / whole, 1)


def row_from_stats(stats: dict, label: str | None = None) -> dict:
    voted = stats["games_with_vote"]
    return {
        "poster_nick": stats.get("poster_nick") or label or "ALL",
        "polemica_nick": stats.get("polemica_nick") or "",
        "user_id": stats.get("user_id") or "",
        "mafia_games": stats["mafia_games"],
        "games_with_first_vote": voted,
        "games_no_first_vote": stats["games_no_vote"],
        "voted_civilian": stats["voted_civilian"],
        "voted_sheriff": stats["voted_sheriff"],
        "voted_own_mafia": stats["voted_own_mafia"],
        "voted_own_don": stats["voted_own_don"],
        "voted_own_black": stats["voted_own_black"],
        "voted_self": stats["voted_self"],
        "voted_unknown": stats["voted_unknown"],
        "pct_civilian": pct(stats["voted_civilian"], voted),
        "pct_sheriff": pct(stats["voted_sheriff"], voted),
        "pct_own_mafia": pct(stats["voted_own_mafia"], voted),
        "pct_own_don": pct(stats["voted_own_don"], voted),
        "pct_own_black": pct(stats["voted_own_black"], voted),
        "pct_red_town": pct(stats["voted_civilian"] + stats["voted_sheriff"], voted),
        "first_vote_on_protocol_day1": stats["first_vote_on_protocol_day1"],
        "first_vote_on_protocol_day2plus": stats["first_vote_on_protocol_day2plus"],
        "protocol_day1_ballot_games": stats["protocol_day1_ballot_games"],
        "protocol_day1_voted_civilian": stats["protocol_day1_voted_civilian"],
        "protocol_day1_voted_sheriff": stats["protocol_day1_voted_sheriff"],
        "protocol_day1_voted_own_mafia": stats["protocol_day1_voted_own_mafia"],
        "protocol_day1_voted_own_don": stats["protocol_day1_voted_own_don"],
        "protocol_day1_voted_own_black": stats["protocol_day1_voted_own_black"],
        "protocol_day1_voted_self": stats["protocol_day1_voted_self"],
        "protocol_day1_no_ballot": stats["protocol_day1_no_ballot"],
        "note": NOTE,
    }


def write_csv(path: Path, rows: list[dict]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8-sig", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=list(rows[0].keys()))
        writer.writeheader()
        writer.writerows(rows)


def fmt(value) -> str:
    if value is None:
        return "—"
    return str(value)


def main() -> None:
    per_player, overall = analyze()
    player_rows = [
        row_from_stats(stats)
        for _, stats in sorted(per_player.items(), key=lambda item: item[1]["poster_nick"])
    ]
    overall_row = row_from_stats(overall, "ALL")
    write_csv(OUT_SUMMARY, player_rows)
    write_csv(OUT_OVERALL, [overall_row])

    print("Когда наш игрок именно мафия (не дон): куда уходит первый голос", flush=True)
    print(NOTE, flush=True)
    print(
        f"Мафийных посадок: {overall['mafia_games']}; "
        f"с первым голосом: {overall['games_with_vote']}; "
        f"без голоса: {overall['games_no_vote']}",
        flush=True,
    )
    print(
        f"В мирных: {overall['voted_civilian']} "
        f"({pct(overall['voted_civilian'], overall['games_with_vote'])}%); "
        f"в шерифа: {overall['voted_sheriff']} "
        f"({pct(overall['voted_sheriff'], overall['games_with_vote'])}%); "
        f"во вторую мафию: {overall['voted_own_mafia']} "
        f"({pct(overall['voted_own_mafia'], overall['games_with_vote'])}%); "
        f"в дона: {overall['voted_own_don']} "
        f"({pct(overall['voted_own_don'], overall['games_with_vote'])}%); "
        f"в своих суммарно: {overall['voted_own_black']} "
        f"({pct(overall['voted_own_black'], overall['games_with_vote'])}%); "
        f"в себя: {overall['voted_self']}",
        flush=True,
    )
    print(
        f"Строго протоколный день 1: {overall['protocol_day1_ballot_games']} голосов "
        f"(мирные {overall['protocol_day1_voted_civilian']}, "
        f"шериф {overall['protocol_day1_voted_sheriff']}, "
        f"вторая мафия {overall['protocol_day1_voted_own_mafia']}, "
        f"дон {overall['protocol_day1_voted_own_don']}, "
        f"себя {overall['protocol_day1_voted_self']})",
        flush=True,
    )
    print(f"По игрокам: {OUT_SUMMARY}", flush=True)
    print(f"Итого: {OUT_OVERALL}", flush=True)
    print("", flush=True)
    header = (
        "игрок | мафия | голос | мирные | шериф | 2-я мафия | дон | %мир | %шер | %маф | %дон"
    )
    print(header, flush=True)
    for row in [overall_row, *player_rows]:
        print(
            " | ".join(
                [
                    fmt(row["poster_nick"]),
                    fmt(row["mafia_games"]),
                    fmt(row["games_with_first_vote"]),
                    fmt(row["voted_civilian"]),
                    fmt(row["voted_sheriff"]),
                    fmt(row["voted_own_mafia"]),
                    fmt(row["voted_own_don"]),
                    fmt(row["pct_civilian"]),
                    fmt(row["pct_sheriff"]),
                    fmt(row["pct_own_mafia"]),
                    fmt(row["pct_own_don"]),
                ]
            ),
            flush=True,
        )


if __name__ == "__main__":
    main()
