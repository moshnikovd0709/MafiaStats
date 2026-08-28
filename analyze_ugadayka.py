from __future__ import annotations

import json
from collections import Counter
from pathlib import Path

from analyze_black_speech_fouls import (
    BLACK_ROLES,
    GAMES_DIR,
    ROLE_DON,
    ROLE_MAFIA,
    load_tracked_players,
    payload_in_period,
)
from analyze_mafia_day1_votes import pct
from script import DATE_FROM, DATE_TO

OUT_SUMMARY = Path("data/offline_tournament/analysis_ugadayka.csv")
OUT_OVERALL = Path("data/offline_tournament/analysis_ugadayka_overall.csv")

NOTE = (
    f"Период {DATE_FROM} — {DATE_TO}. Угадайка = первый момент, когда за столом "
    "ровно 3 живых и среди них ровно 1 чёрный (мафия или дон). "
    "Обычно это утро после последней ночи: ночь была 1 чёрный + 3 красных, "
    "отстрел, осталось трое, дальше дневное голосование. "
    "Реже трое уже к началу ночи — чёрный стреляет и закрывает игру ночью. "
    "Считается только живой чёрный (мафия/дон) из этой тройки. "
    "Победа = чёрные выиграли партию (winnerCode=1)."
)


def empty_stats() -> dict:
    return {
        "ugadayka_games": 0,
        "ugadayka_wins": 0,
        "as_mafia": 0,
        "as_don": 0,
        "day_games": 0,
        "day_wins": 0,
        "night_games": 0,
        "night_wins": 0,
        "unique_games": 0,
        "unique_wins": 0,
    }


def last_vote_day_by_seat(votes: list[dict]) -> dict[int, int]:
    last: dict[int, int] = {}
    for vote in votes:
        voter = vote.get("voter")
        day = vote.get("day")
        if voter is None or day is None:
            continue
        try:
            voter = int(voter)
            day = int(day)
        except (TypeError, ValueError):
            continue
        last[voter] = max(last.get(voter, 0), day)
    return last


def unanimous_night_kill(
    shots: list[dict], night: int, alive: set[int], by_role: dict[int, int]
) -> int | None:
    living_black = [seat for seat in alive if by_role.get(seat) in BLACK_ROLES]
    night_shots = [
        item
        for item in shots
        if item.get("night") == night and item.get("shooter") in living_black
    ]
    if not living_black or not night_shots:
        return None
    victims = [item.get("victim") for item in night_shots]
    if len(set(victims)) != 1 or len(night_shots) != len(living_black):
        return None
    victim = victims[0]
    try:
        victim = int(victim)
    except (TypeError, ValueError):
        return None
    return victim if victim in alive else None


def last_ballot_tied(votes: list[dict], day: int, alive: set[int]) -> list[int]:
    ballots = [
        item
        for item in votes
        if item.get("day") == day
        and item.get("num") is not None
        and int(item["num"]) >= 1
        and item.get("voter") in alive
    ]
    if not ballots:
        return []
    max_num = max(int(item["num"]) for item in ballots)
    last = [item for item in ballots if int(item["num"]) == max_num]
    counts: Counter[int] = Counter()
    for item in last:
        candidate = item.get("candidate")
        if candidate in alive:
            counts[int(candidate)] += 1
    if not counts:
        return []
    top = max(counts.values())
    return [seat for seat, votes_n in counts.items() if votes_n == top]


def vote_eliminated(
    votes: list[dict],
    day: int,
    alive: set[int],
    last_vote_day: dict[int, int],
    with_quit_time: set[int],
) -> list[int]:
    leaders = last_ballot_tied(votes, day, alive)
    if not leaders:
        return []
    if any(last_vote_day.get(seat, 0) > day for seat in leaders):
        return []
    if len(leaders) == 1:
        return leaders
    if all(seat in with_quit_time for seat in leaders):
        return leaders
    return []


def replay(payload: dict) -> dict:
    data = payload.get("data") or {}
    inner = data.get("players") or []
    by_role = {
        int(item["position"]): item.get("role")
        for item in inner
        if item.get("position") is not None
    }
    by_player = {
        int(item["position"]): item.get("player")
        for item in inner
        if item.get("position") is not None
    }
    votes = data.get("votes") or []
    shots = data.get("shots") or []
    with_quit_time = {int(item["position"]) for item in inner if item.get("quitTime")}
    last_vote_day = last_vote_day_by_seat(votes)
    alive = set(by_role)
    nights = sorted({item.get("night") for item in shots if item.get("night")})
    days = sorted({item.get("day") for item in votes if item.get("day")})
    disquals = []
    for item in inner:
        dq = item.get("disqual")
        if isinstance(dq, dict) and item.get("position") is not None:
            disquals.append((int(dq.get("day") or 0), int(item["position"])))
    stage = data.get("stage") or {}
    go_day = stage.get("day") if stage.get("type") == "gameOver" else None
    max_n = max(
        nights[-1] if nights else 0,
        days[-1] if days else 0,
        go_day or 0,
        1,
    )
    alive_at_night: dict[int, set[int]] = {}
    alive_at_day: dict[int, set[int]] = {}
    vote_elims: list[dict] = []

    def apply_disquals(day: int) -> None:
        for dq_day, seat in disquals:
            if dq_day == day and seat in alive and last_vote_day.get(seat, 0) <= day:
                alive.discard(seat)

    def take_vote(day: int) -> None:
        elims = vote_eliminated(votes, day, alive, last_vote_day, with_quit_time)
        if elims:
            vote_elims.append({"day": day, "seats": list(elims)})
            for seat in elims:
                alive.discard(seat)

    apply_disquals(1)
    alive_at_day[1] = set(alive)
    if 1 in days:
        take_vote(1)

    for night in range(1, max_n + 1):
        alive_at_night[night] = set(alive)
        victim = unanimous_night_kill(shots, night, alive, by_role)
        if victim is not None and last_vote_day.get(victim, 0) <= night:
            alive.discard(victim)
        day = night + 1
        apply_disquals(day)
        alive_at_day[day] = set(alive)
        if day in days:
            take_vote(day)

    return {
        "by_role": by_role,
        "by_player": by_player,
        "alive_at_night": alive_at_night,
        "alive_at_day": alive_at_day,
        "nights": nights,
        "winner": payload.get("winnerCode"),
        "inner": inner,
        "with_quit_time": with_quit_time,
        "final_alive": set(alive),
        "vote_elims": vote_elims,
    }


def iter_phases(state: dict):
    alive_at_day = state["alive_at_day"]
    alive_at_night = state["alive_at_night"]
    max_n = max(list(alive_at_night) or [0])
    if 1 in alive_at_day:
        yield "day", 1, alive_at_day[1]
    for night in range(1, max_n + 1):
        if night in alive_at_night:
            yield "night", night, alive_at_night[night]
        if night + 1 in alive_at_day:
            yield "day", night + 1, alive_at_day[night + 1]


def first_ugadayka(state: dict) -> dict | None:
    by_role = state["by_role"]
    for kind, num, alive in iter_phases(state):
        if len(alive) != 3:
            continue
        blacks = [seat for seat in alive if by_role.get(seat) in BLACK_ROLES]
        if len(blacks) != 1:
            continue
        black_seat = blacks[0]
        return {
            "kind": kind,
            "num": num,
            "alive": set(alive),
            "black_seat": black_seat,
            "black_role": by_role[black_seat],
            "black_user_id": state["by_player"].get(black_seat),
        }
    return None


def analyze() -> tuple[dict[int, dict], dict]:
    tracked = load_tracked_players()
    per_player = {user_id: empty_stats() | dict(meta) for user_id, meta in tracked.items()}
    overall = empty_stats()
    seen_games = 0
    seen_wins = 0

    for path in sorted(GAMES_DIR.glob("*.json"), key=lambda item: int(item.stem)):
        payload = json.loads(path.read_text(encoding="utf-8"))
        if not payload_in_period(payload):
            continue
        inner = (payload.get("data") or {}).get("players") or []
        if len(inner) < 10:
            continue
        state = replay(payload)
        found = first_ugadayka(state)
        if found is None:
            continue
        seen_games += 1
        black_win = state["winner"] == 1
        if black_win:
            seen_wins += 1

        user_id = found["black_user_id"]
        try:
            user_id = int(user_id) if user_id is not None else None
        except (TypeError, ValueError):
            user_id = None
        if user_id not in tracked:
            continue

        buckets = [per_player[user_id], overall]
        for stats in buckets:
            stats["ugadayka_games"] += 1
            if found["black_role"] == ROLE_DON:
                stats["as_don"] += 1
            elif found["black_role"] == ROLE_MAFIA:
                stats["as_mafia"] += 1
            if found["kind"] == "night":
                stats["night_games"] += 1
            else:
                stats["day_games"] += 1
            if black_win:
                stats["ugadayka_wins"] += 1
                if found["kind"] == "night":
                    stats["night_wins"] += 1
                else:
                    stats["day_wins"] += 1

    overall["unique_games"] = seen_games
    overall["unique_wins"] = seen_wins
    return per_player, overall


def row_from_stats(stats: dict, label: str | None = None) -> dict:
    games = stats["ugadayka_games"]
    return {
        "poster_nick": stats.get("poster_nick") or label or "ALL",
        "polemica_nick": stats.get("polemica_nick") or "",
        "user_id": stats.get("user_id") or "",
        "ugadayka_games": games,
        "ugadayka_wins": stats["ugadayka_wins"],
        "ugadayka_losses": games - stats["ugadayka_wins"],
        "pct_ugadayka_win": pct(stats["ugadayka_wins"], games),
        "as_mafia": stats["as_mafia"],
        "as_don": stats["as_don"],
        "day_games": stats["day_games"],
        "day_wins": stats["day_wins"],
        "pct_day_win": pct(stats["day_wins"], stats["day_games"]),
        "night_games": stats["night_games"],
        "night_wins": stats["night_wins"],
        "pct_night_win": pct(stats["night_wins"], stats["night_games"]),
        "unique_games": stats.get("unique_games") or "",
        "unique_wins": stats.get("unique_wins") or "",
        "note": NOTE,
    }


def sort_rows(rows: list[dict]) -> list[dict]:
    return sorted(
        rows,
        key=lambda row: (
            row["pct_ugadayka_win"] is None,
            -(row["pct_ugadayka_win"] or 0),
            -(row["ugadayka_wins"] or 0),
            -(row["ugadayka_games"] or 0),
            row["poster_nick"],
        ),
    )


def main() -> None:
    from export_analysis_csv import main as export_main

    export_main()


if __name__ == "__main__":
    main()
