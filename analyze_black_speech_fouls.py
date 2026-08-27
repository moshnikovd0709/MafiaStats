from __future__ import annotations

import csv
import json
from pathlib import Path

from script import DATE_FROM, DATE_TO, OUTPUT_OFFLINE_TOURNAMENT_CSV

GAMES_DIR = Path("data/offline_tournament/games")
OUT_SUMMARY = Path("data/offline_tournament/analysis_black_speech_fouls.csv")
OUT_OVERALL = Path("data/offline_tournament/analysis_black_speech_fouls_overall.csv")

ROLE_DON = 0
ROLE_MAFIA = 1
ROLE_CIVILIAN = 2
ROLE_SHERIFF = 3
BLACK_ROLES = {ROLE_DON, ROLE_MAFIA}
RED_ROLES = {ROLE_CIVILIAN, ROLE_SHERIFF}
SPEECH_STAGES = {"speech", "reSpeech"}

ROLE_TITLE = {
    ROLE_DON: "don",
    ROLE_MAFIA: "mafia",
    ROLE_CIVILIAN: "civilian",
    ROLE_SHERIFF: "sheriff",
}


def payload_date(payload: dict) -> str:
    raw = payload.get("started_at") or (payload.get("data") or {}).get("started") or ""
    return str(raw)[:10]


def payload_in_period(payload: dict) -> bool:
    date = payload_date(payload)
    return bool(date) and DATE_FROM <= date <= DATE_TO


def load_tracked_players() -> dict[int, dict]:
    with open(OUTPUT_OFFLINE_TOURNAMENT_CSV, encoding="utf-8-sig", newline="") as handle:
        rows = list(csv.DictReader(handle))
    tracked = {}
    for row in rows:
        if not row.get("user_id"):
            continue
        user_id = int(row["user_id"])
        tracked[user_id] = {
            "poster_nick": row["poster_nick"],
            "polemica_nick": row.get("polemica_nick") or "",
            "user_id": user_id,
        }
    return tracked


def empty_stats() -> dict:
    return {
        "black_games": 0,
        "mafia_games": 0,
        "don_games": 0,
        "speech_fouls": 0,
        "on_black": 0,
        "on_red": 0,
        "on_self": 0,
        "on_unknown": 0,
        "on_don": 0,
        "on_mafia": 0,
        "on_civilian": 0,
        "on_sheriff": 0,
        "games_with_speech_foul": 0,
    }


def classify_speaker(speaker_role: int | None, fouler_pos: int, speaker_pos: int | None) -> str:
    if speaker_pos is None or speaker_role is None:
        return "unknown"
    if speaker_pos == fouler_pos:
        return "self"
    if speaker_role in BLACK_ROLES:
        return "black"
    if speaker_role in RED_ROLES:
        return "red"
    return "unknown"


def analyze() -> tuple[dict[int, dict], dict]:
    tracked = load_tracked_players()
    per_player = {user_id: empty_stats() | dict(meta) for user_id, meta in tracked.items()}
    overall = empty_stats()

    for path in sorted(GAMES_DIR.glob("*.json"), key=lambda item: int(item.stem)):
        payload = json.loads(path.read_text(encoding="utf-8"))
        if not payload_in_period(payload):
            continue
        inner_players = (payload.get("data") or {}).get("players") or []
        by_pos = {int(item["position"]): item for item in inner_players if item.get("position") is not None}

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

            had_speech_foul = False
            for foul in player.get("fouls") or []:
                stage = foul.get("stage") or {}
                if stage.get("type") not in SPEECH_STAGES:
                    continue
                speaker_pos = stage.get("player")
                speaker_pos = int(speaker_pos) if speaker_pos is not None else None
                speaker = by_pos.get(speaker_pos) if speaker_pos is not None else None
                speaker_role = speaker.get("role") if speaker else None
                bucket = classify_speaker(speaker_role, pos, speaker_pos)

                stats["speech_fouls"] += 1
                overall["speech_fouls"] += 1
                had_speech_foul = True
                if bucket == "self":
                    stats["on_self"] += 1
                    overall["on_self"] += 1
                elif bucket == "black":
                    stats["on_black"] += 1
                    overall["on_black"] += 1
                elif bucket == "red":
                    stats["on_red"] += 1
                    overall["on_red"] += 1
                else:
                    stats["on_unknown"] += 1
                    overall["on_unknown"] += 1

                if speaker_role == ROLE_DON and bucket != "self":
                    stats["on_don"] += 1
                    overall["on_don"] += 1
                elif speaker_role == ROLE_MAFIA and bucket != "self":
                    stats["on_mafia"] += 1
                    overall["on_mafia"] += 1
                elif speaker_role == ROLE_CIVILIAN:
                    stats["on_civilian"] += 1
                    overall["on_civilian"] += 1
                elif speaker_role == ROLE_SHERIFF:
                    stats["on_sheriff"] += 1
                    overall["on_sheriff"] += 1

            if had_speech_foul:
                stats["games_with_speech_foul"] += 1
                overall["games_with_speech_foul"] += 1

    return per_player, overall


def pct(part: int, whole: int) -> float | None:
    if not whole:
        return None
    return round(100.0 * part / whole, 1)


def ratio(left: int, right: int) -> float | None:
    if not right:
        return None
    return round(left / right, 3)


def row_from_stats(stats: dict, label: str | None = None) -> dict:
    other = stats["on_black"] + stats["on_red"]
    return {
        "poster_nick": stats.get("poster_nick") or label or "ALL",
        "polemica_nick": stats.get("polemica_nick") or "",
        "user_id": stats.get("user_id") or "",
        "black_games": stats["black_games"],
        "mafia_games": stats["mafia_games"],
        "don_games": stats["don_games"],
        "games_with_speech_foul": stats["games_with_speech_foul"],
        "speech_fouls": stats["speech_fouls"],
        "on_black": stats["on_black"],
        "on_red": stats["on_red"],
        "on_self": stats["on_self"],
        "on_unknown": stats["on_unknown"],
        "on_don": stats["on_don"],
        "on_mafia": stats["on_mafia"],
        "on_civilian": stats["on_civilian"],
        "on_sheriff": stats["on_sheriff"],
        "pct_on_black_vs_red": pct(stats["on_black"], other),
        "pct_on_red_vs_black": pct(stats["on_red"], other),
        "black_per_red": ratio(stats["on_black"], stats["on_red"]),
        "pct_on_black_all_speech": pct(stats["on_black"], stats["speech_fouls"]),
        "pct_on_red_all_speech": pct(stats["on_red"], stats["speech_fouls"]),
        "pct_on_self_all_speech": pct(stats["on_self"], stats["speech_fouls"]),
        "naive_random_black_share_pct": 22.2,
        "note": "random baseline 2/9 teammates vs 7/9 town, excluding own speech",
    }


def write_csv(path: Path, rows: list[dict]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8-sig", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=list(rows[0].keys()))
        writer.writeheader()
        writer.writerows(rows)


def main() -> None:
    per_player, overall = analyze()
    player_rows = [
        row_from_stats(stats)
        for _, stats in sorted(per_player.items(), key=lambda item: item[1]["poster_nick"])
    ]
    overall_row = row_from_stats(overall, "ALL")
    write_csv(OUT_SUMMARY, player_rows)
    write_csv(OUT_OVERALL, [overall_row])

    print(
        f"Когда наш игрок мафия/дон, фолы на речах (speech + reSpeech); "
        f"период {DATE_FROM} — {DATE_TO}",
        flush=True,
    )
    print(
        f"Чёрных игр: {overall['black_games']}; фолов на речах: {overall['speech_fouls']}",
        flush=True,
    )
    other = overall["on_black"] + overall["on_red"]
    print(
        f"На своих (мафия/дон, не себя): {overall['on_black']} "
        f"({pct(overall['on_black'], other)}% от чужих речей)",
        flush=True,
    )
    print(
        f"На красных (мирный/шериф): {overall['on_red']} "
        f"({pct(overall['on_red'], other)}% от чужих речей)",
        flush=True,
    )
    print(
        f"На своей речи: {overall['on_self']}; неизвестно: {overall['on_unknown']}",
        flush=True,
    )
    print(
        f"Случайная доля на своих была бы ~22.2% (2 из 9 чужих мест).",
        flush=True,
    )
    print(f"По игрокам: {OUT_SUMMARY}", flush=True)
    print(f"Итого: {OUT_OVERALL}", flush=True)
    preview_cols = [
        "poster_nick",
        "black_games",
        "speech_fouls",
        "on_black",
        "on_red",
        "on_self",
        "pct_on_black_vs_red",
        "pct_on_red_vs_black",
    ]
    print("", flush=True)
    for row in [overall_row, *player_rows]:
        print(" | ".join(str(row[col]) for col in preview_cols), flush=True)


if __name__ == "__main__":
    main()
