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
from analyze_civilian_first_votes import (
    OUT_OVERALL as CIV_OVERALL,
    OUT_SUMMARY as CIV_SUMMARY,
    analyze as analyze_civ,
    row_from_stats as civ_row,
)
from analyze_sheriff_n1_black_checks import (
    OUT_OVERALL as CHECK_OVERALL,
    OUT_SUMMARY as CHECK_SUMMARY,
    analyze as analyze_checks,
    row_from_stats as check_row,
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
ROOT_CIV_CSV = Path("polemica_civilian_first_votes.csv")
ROOT_CHECK_CSV = Path("polemica_sheriff_n1_black_checks.csv")
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
    "civilian_games": "civ_games",
    "civ_voted_civilian": "civ_first_vote_civilian",
    "civ_voted_don": "civ_first_vote_don",
    "civ_voted_mafia": "civ_first_vote_mafia",
    "civ_voted_black": "civ_first_vote_black",
    "civ_voted_self": "civ_first_vote_self",
    "civ_pct_sheriff": "civ_first_vote_pct_sheriff",
    "civ_pct_civilian": "civ_first_vote_pct_civilian",
    "civ_pct_black": "civ_first_vote_pct_black",
    "sheriff_n1_checked": "sheriff_n1_checked_mafia",
    "pct_sheriff_n1_on_mafia": "sheriff_n1_pct_on_mafia",
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


def build_combined_row(vote: dict, foul: dict | None, civ: dict | None, check: dict | None) -> dict:
    foul = foul or {}
    civ = civ or {}
    check = check or {}
    return {
        "date_from": DATE_FROM,
        "date_to": DATE_TO,
        "poster_nick": vote["poster_nick"],
        "polemica_nick": vote.get("polemica_nick") or foul.get("polemica_nick") or civ.get("polemica_nick") or "",
        "user_id": vote.get("user_id") or foul.get("user_id") or civ.get("user_id") or "",
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
        "civilian_games": civ.get("civilian_games"),
        "civ_voted_civilian": civ.get("voted_civilian"),
        "civ_voted_don": civ.get("voted_don"),
        "civ_voted_mafia": civ.get("voted_mafia"),
        "civ_voted_black": civ.get("voted_black"),
        "civ_voted_self": civ.get("voted_self"),
        "civ_pct_sheriff": civ.get("pct_sheriff"),
        "civ_pct_civilian": civ.get("pct_civilian"),
        "civ_pct_black": civ.get("pct_black"),
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
        "sheriff_n1_checked": check.get("sheriff_n1_checked"),
        "pct_sheriff_n1_on_mafia": check.get("pct_sheriff_n1_on_mafia"),
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
    stale = [
        "civ_first_vote_games",
        "civ_first_vote_no_vote",
        "civ_first_vote_sheriff",
        "sheriff_n1_checked_black",
        "sheriff_n1_checked_as_mafia",
        "sheriff_n1_checked_as_don",
        "sheriff_n1_pct_on_black",
    ]
    drop_cols = [
        col
        for col in list(extra.columns) + stale
        if col != "poster_nick" and col in base.columns
    ]
    if drop_cols:
        base = base.drop(columns=drop_cols)
    merged = base.merge(extra, on="poster_nick", how="left")
    merged.to_csv(path, index=False, encoding="utf-8-sig")


def export_all() -> dict:
    fouls_per, fouls_overall = analyze_fouls()
    votes_per, votes_overall = analyze_votes()
    civ_per, civ_overall = analyze_civ()
    check_per, check_overall = analyze_checks()

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
    civ_players = [
        with_period(civ_row(stats))
        for _, stats in sorted(civ_per.items(), key=lambda item: item[1]["poster_nick"])
    ]
    civ_all = with_period(civ_row(civ_overall, "ALL"))
    check_players = [
        with_period(check_row(stats))
        for _, stats in sorted(check_per.items(), key=lambda item: item[1]["poster_nick"])
    ]
    check_all = with_period(check_row(check_overall, "ALL"))

    write_csv(FOULS_SUMMARY, foul_players)
    write_csv(FOULS_OVERALL, [foul_all])
    write_csv(ROOT_FOULS_CSV, [foul_all, *foul_players])

    write_csv(VOTES_SUMMARY, vote_players)
    write_csv(VOTES_OVERALL, [vote_all])
    write_csv(ROOT_VOTES_CSV, [vote_all, *vote_players])

    write_csv(CIV_SUMMARY, civ_players)
    write_csv(CIV_OVERALL, [civ_all])
    write_csv(ROOT_CIV_CSV, [civ_all, *civ_players])

    write_csv(CHECK_SUMMARY, check_players)
    write_csv(CHECK_OVERALL, [check_all])
    write_csv(ROOT_CHECK_CSV, [check_all, *check_players])

    fouls_by_nick = {row["poster_nick"]: row for row in [foul_all, *foul_players]}
    civ_by_nick = {row["poster_nick"]: row for row in [civ_all, *civ_players]}
    check_by_nick = {row["poster_nick"]: row for row in [check_all, *check_players]}
    combined = [
        build_combined_row(
            vote,
            fouls_by_nick.get(vote["poster_nick"]),
            civ_by_nick.get(vote["poster_nick"]),
            check_by_nick.get(vote["poster_nick"]),
        )
        for vote in [vote_all, *vote_players]
    ]
    write_csv(ROOT_COMBINED_CSV, combined)
    merge_into_offline_csv(combined)

    return {
        "votes": (vote_players, vote_all, votes_overall),
        "fouls": (foul_players, foul_all, fouls_overall),
        "civ": (civ_players, civ_all, civ_overall),
        "checks": (check_players, check_all, check_overall),
        "combined": combined,
    }


def main() -> None:
    from analyze_mafia_day1_votes import fmt
    from analyze_sheriff_n1_black_checks import NOTE as CHECK_NOTE

    result = export_all()
    check_players, check_all, check_overall = result["checks"]

    print(
        f"Когда наш игрок именно мафия (не дон): проверка шерифа в первую ночь; "
        f"период {DATE_FROM} — {DATE_TO}",
        flush=True,
    )
    print(CHECK_NOTE, flush=True)
    print(
        f"Мафийных посадок: {check_overall['mafia_games']}; "
        f"шериф ткнул в первую ночь: {check_overall['checked_n1']} "
        f"({check_all['pct_sheriff_n1_on_mafia']}%)",
        flush=True,
    )
    print(f"CSV: {ROOT_CHECK_CSV}", flush=True)
    print(f"CSV всё вместе: {ROOT_COMBINED_CSV}", flush=True)
    print("", flush=True)
    header = "игрок | мафия | ткнул N1 | %"
    print(header, flush=True)
    for row in [check_all, *check_players]:
        print(
            " | ".join(
                [
                    fmt(row["poster_nick"]),
                    fmt(row["mafia_games"]),
                    fmt(row["sheriff_n1_checked"]),
                    fmt(row["pct_sheriff_n1_on_mafia"]),
                ]
            ),
            flush=True,
        )


if __name__ == "__main__":
    main()
