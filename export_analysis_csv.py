from __future__ import annotations

import csv
from pathlib import Path

import pandas as pd

from analyze_black_speech_fouls import (
    OUT_OVERALL as FOULS_OVERALL,
    OUT_SUMMARY as FOULS_SUMMARY,
    analyze as analyze_fouls,
    row_from_stats as fouls_row,
)
from analyze_mafia_day1_votes import (
    OUT_OVERALL as VOTES_OVERALL,
    OUT_SUMMARY as VOTES_SUMMARY,
    analyze as analyze_votes,
    row_from_stats as votes_row,
)
from script import DATE_FROM, DATE_TO, OUTPUT_OFFLINE_TOURNAMENT_CSV

ROOT_VOTES_CSV = Path("polemica_mafia_first_votes.csv")
ROOT_FOULS_CSV = Path("polemica_black_speech_fouls.csv")
ROOT_COMBINED_CSV = Path("polemica_offline_tournament_analysis.csv")

RENAME_FOR_OFFLINE = {
    "mafia_games": "protocol_mafia_games",
    "games_with_first_vote": "first_vote_games",
    "games_no_first_vote": "first_vote_no_vote",
    "voted_civilian": "first_vote_civilian",
    "voted_sheriff": "first_vote_sheriff",
    "voted_own_mafia": "first_vote_own_mafia",
    "voted_own_don": "first_vote_own_don",
    "voted_own_black": "first_vote_own_black",
    "voted_self": "first_vote_self",
    "pct_civilian": "first_vote_pct_civilian",
    "pct_sheriff": "first_vote_pct_sheriff",
    "pct_own_mafia": "first_vote_pct_own_mafia",
    "pct_own_don": "first_vote_pct_own_don",
    "pct_own_black": "first_vote_pct_own_black",
    "pct_red_town": "first_vote_pct_red_town",
    "black_games": "protocol_black_games",
    "don_games": "protocol_don_games",
    "games_with_speech_foul": "speech_games_with_foul",
}


def write_csv(path: Path, rows: list[dict]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8-sig", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=list(rows[0].keys()))
        writer.writeheader()
        writer.writerows(rows)


def with_period(row: dict) -> dict:
    out = {"date_from": DATE_FROM, "date_to": DATE_TO}
    out.update({key: value for key, value in row.items() if key != "note"})
    return out


def build_combined_row(vote: dict, foul: dict | None) -> dict:
    foul = foul or {}
    return {
        "date_from": DATE_FROM,
        "date_to": DATE_TO,
        "poster_nick": vote["poster_nick"],
        "polemica_nick": vote.get("polemica_nick") or foul.get("polemica_nick") or "",
        "user_id": vote.get("user_id") or foul.get("user_id") or "",
        "mafia_games": vote.get("mafia_games"),
        "games_with_first_vote": vote.get("games_with_first_vote"),
        "games_no_first_vote": vote.get("games_no_first_vote"),
        "voted_civilian": vote.get("voted_civilian"),
        "voted_sheriff": vote.get("voted_sheriff"),
        "voted_own_mafia": vote.get("voted_own_mafia"),
        "voted_own_don": vote.get("voted_own_don"),
        "voted_own_black": vote.get("voted_own_black"),
        "voted_self": vote.get("voted_self"),
        "pct_civilian": vote.get("pct_civilian"),
        "pct_sheriff": vote.get("pct_sheriff"),
        "pct_own_mafia": vote.get("pct_own_mafia"),
        "pct_own_don": vote.get("pct_own_don"),
        "pct_own_black": vote.get("pct_own_black"),
        "pct_red_town": vote.get("pct_red_town"),
        "black_games": foul.get("black_games"),
        "don_games": foul.get("don_games"),
        "games_with_speech_foul": foul.get("games_with_speech_foul"),
        "speech_fouls": foul.get("speech_fouls"),
        "speech_on_black": foul.get("on_black"),
        "speech_on_red": foul.get("on_red"),
        "speech_on_self": foul.get("on_self"),
        "speech_on_don": foul.get("on_don"),
        "speech_on_mafia": foul.get("on_mafia"),
        "speech_on_civilian": foul.get("on_civilian"),
        "speech_on_sheriff": foul.get("on_sheriff"),
        "speech_pct_on_black": foul.get("pct_on_black_vs_red"),
        "speech_pct_on_red": foul.get("pct_on_red_vs_black"),
    }


def merge_into_offline_csv(combined_rows: list[dict]) -> None:
    path = Path(OUTPUT_OFFLINE_TOURNAMENT_CSV)
    if not path.exists():
        return
    base = pd.read_csv(path)
    extra = pd.DataFrame(combined_rows)
    extra = extra[extra["poster_nick"] != "ALL"].copy()
    extra = extra.drop(columns=["date_from", "date_to", "polemica_nick", "user_id"], errors="ignore")
    extra = extra.rename(columns=RENAME_FOR_OFFLINE)
    drop_cols = [col for col in extra.columns if col != "poster_nick" and col in base.columns]
    if drop_cols:
        base = base.drop(columns=drop_cols)
    merged = base.merge(extra, on="poster_nick", how="left")
    merged.to_csv(path, index=False, encoding="utf-8-sig")


def export_all() -> dict:
    fouls_per, fouls_overall = analyze_fouls()
    votes_per, votes_overall = analyze_votes()

    foul_players = [
        with_period(fouls_row(stats))
        for _, stats in sorted(fouls_per.items(), key=lambda item: item[1]["poster_nick"])
    ]
    foul_all = with_period(fouls_row(fouls_overall, "ALL"))
    vote_players = [
        with_period(votes_row(stats))
        for _, stats in sorted(votes_per.items(), key=lambda item: item[1]["poster_nick"])
    ]
    vote_all = with_period(votes_row(votes_overall, "ALL"))

    write_csv(FOULS_SUMMARY, foul_players)
    write_csv(FOULS_OVERALL, [foul_all])
    write_csv(ROOT_FOULS_CSV, [foul_all, *foul_players])

    write_csv(VOTES_SUMMARY, vote_players)
    write_csv(VOTES_OVERALL, [vote_all])
    write_csv(ROOT_VOTES_CSV, [vote_all, *vote_players])

    fouls_by_nick = {row["poster_nick"]: row for row in [foul_all, *foul_players]}
    combined = [
        build_combined_row(vote, fouls_by_nick.get(vote["poster_nick"]))
        for vote in [vote_all, *vote_players]
    ]
    write_csv(ROOT_COMBINED_CSV, combined)
    merge_into_offline_csv(combined)

    return {
        "votes": (vote_players, vote_all, votes_overall),
        "fouls": (foul_players, foul_all, fouls_overall),
        "combined": combined,
    }


def main() -> None:
    from analyze_black_speech_fouls import pct as fouls_pct
    from analyze_mafia_day1_votes import NOTE, fmt, pct

    result = export_all()
    _, _, fouls_overall = result["fouls"]
    vote_players, vote_all, votes_overall = result["votes"]

    print(
        f"Когда наш игрок мафия/дон, фолы на речах; период {DATE_FROM} — {DATE_TO}",
        flush=True,
    )
    other = fouls_overall["on_black"] + fouls_overall["on_red"]
    print(
        f"Чёрных игр: {fouls_overall['black_games']}; фолов: {fouls_overall['speech_fouls']}; "
        f"на своих {fouls_overall['on_black']} ({fouls_pct(fouls_overall['on_black'], other)}%); "
        f"на красных {fouls_overall['on_red']} ({fouls_pct(fouls_overall['on_red'], other)}%)",
        flush=True,
    )
    print(f"CSV: {ROOT_FOULS_CSV}", flush=True)
    print("", flush=True)
    print("Когда наш игрок именно мафия (не дон): куда уходит первый голос", flush=True)
    print(NOTE, flush=True)
    print(
        f"Мафийных посадок: {votes_overall['mafia_games']}; "
        f"с голосом: {votes_overall['games_with_vote']}; "
        f"без голоса: {votes_overall['games_no_vote']}",
        flush=True,
    )
    voted = votes_overall["games_with_vote"]
    print(
        f"В мирных: {votes_overall['voted_civilian']} ({pct(votes_overall['voted_civilian'], voted)}%); "
        f"в шерифа: {votes_overall['voted_sheriff']} ({pct(votes_overall['voted_sheriff'], voted)}%); "
        f"во вторую мафию: {votes_overall['voted_own_mafia']} ({pct(votes_overall['voted_own_mafia'], voted)}%); "
        f"в дона: {votes_overall['voted_own_don']} ({pct(votes_overall['voted_own_don'], voted)}%)",
        flush=True,
    )
    print(f"CSV голосов: {ROOT_VOTES_CSV}", flush=True)
    print(f"CSV всё вместе: {ROOT_COMBINED_CSV}", flush=True)
    print(f"Колонки также добавлены в {OUTPUT_OFFLINE_TOURNAMENT_CSV}", flush=True)
    print("", flush=True)
    header = "игрок | мафия | голос | мирные | шериф | 2-я мафия | дон | %мир | %шер | %маф | %дон"
    print(header, flush=True)
    for row in [vote_all, *vote_players]:
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
