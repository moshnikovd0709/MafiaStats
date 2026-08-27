from __future__ import annotations

import time
import unicodedata
from pathlib import Path
from urllib.parse import quote, urlencode

import pandas as pd
import requests

# ----- Конфигурация -----
BASE_URL = "https://polemicagame.com"
APP_API_URL = "https://app.polemicagame.com"
OUTPUT_CSV = "polemica_stats.csv"
OUTPUT_OFFLINE_TOURNAMENT_CSV = "polemica_offline_tournament_stats.csv"
OUTPUT_NO_OPEN_CSV = "polemica_no_open_stats.csv"

# Статистика за период (примерно последние 9 месяцев)
DATE_FROM = "2026-01-01"
DATE_TO = "2026-08-27"

HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
        "AppleWebKit/537.36 (KHTML, like Gecko) "
        "Chrome/115.0.0.0 Safari/537.36"
    ),
    "Accept": "application/json",
}

# Ники с постера «Турнир Претендентов» (29–30 августа)
POSTER_NICKS = [
    "Саня запчасти",
    "Фартушная",
    "Белладонна",
    "Ластхиро",
    "avomarika",
    "Д. Колбасенко",
    "Алёна",
    "Лиса",
    "Вега",
    "Axeon",
    "Секрет",
    "Кармин",
    "Elric",
    "Macarena",
    "Марипоса",
    "Фырчик",
    "Hartmann",
    "ФДМ",
    "Аномалия",
    "Story",
]

# Явные соответствия постер → ник на Polemica, если автоматический матч неоднозначен
NICK_ALIASES = {
    "Д. Колбасенко": ["Данил_Колбасенко", "Колбасенко"],
    "Hartmann": ["HARTMANN_SPB"],
    "Секрет": ["Секрет-"],
    "Алёна": ["Alena78", "Алена"],
    "Саня запчасти": ["саня запчасти"],
    "Аномалия": ["Anомалия"],
    "Лиса": ["Лисa"],
}

# Визуально похожие латиница/кириллица (в никах часто смешивают)
HOMOGLYPHS = str.maketrans(
    {
        "а": "a",
        "е": "e",
        "ё": "e",
        "о": "o",
        "р": "p",
        "с": "c",
        "х": "x",
        "у": "y",
        "к": "k",
        "т": "t",
        "в": "b",
        "н": "h",
        "м": "m",
        "и": "u",
        "А": "a",
        "Е": "e",
        "О": "o",
        "Р": "p",
        "С": "c",
        "Х": "x",
        "У": "y",
        "К": "k",
        "Т": "t",
        "В": "b",
        "Н": "h",
        "М": "m",
        "И": "u",
    }
)

SESSION = requests.Session()
SESSION.headers.update(HEADERS)


def normalize_nick(value: str) -> str:
    text = unicodedata.normalize("NFKC", value or "")
    text = text.replace("ё", "е").replace("Ё", "Е")
    text = text.translate(HOMOGLYPHS)
    return "".join(ch.lower() for ch in text if ch.isalnum())


def _full_url(url: str, params=None) -> str:
    if not params:
        return url
    return f"{url}?{urlencode(params, doseq=True)}"


def _parse_json_response(resp: requests.Response):
    ctype = (resp.headers.get("Content-Type") or "").lower()
    if "json" not in ctype and not resp.text.lstrip().startswith(("[", "{")):
        raise ValueError(f"ожидался JSON, пришло {ctype or 'неизвестно'}")
    return resp.json()


def get_json(url: str, params=None, retries: int = 3):
    last_error = None
    try:
        resp = SESSION.get(url, params=params, timeout=5)
        resp.raise_for_status()
        return _parse_json_response(resp)
    except (requests.RequestException, ValueError) as exc:
        last_error = exc

    # Запасной путь: Google Translate проксирует JSON, если прямое соединение недоступно
    target = _full_url(url, params)
    proxy = "https://translate.google.com/translate?sl=auto&tl=en&u=" + quote(target, safe="")
    for attempt in range(1, retries + 1):
        try:
            resp = SESSION.get(proxy, timeout=25)
            resp.raise_for_status()
            return _parse_json_response(resp)
        except (requests.RequestException, ValueError) as exc:
            last_error = exc
            time.sleep(1.5 * attempt)
    raise RuntimeError(f"Не удалось получить {url}: {last_error}")


def pct(wins, games) -> float | None:
    if not games:
        return None
    return round(100.0 * wins / games, 1)


ROLES = (
    ("civilian", "civilian"),
    ("sheriff", "sheriff"),
    ("mafia", "mafia"),
    ("godfather", "don"),
)
# Как в фильтрах профиля Polemica:
# competition = оффлайн-турниры, tournament = онлайн-турниры,
# league / lobby / club = не турнир (онлайн).
# lobby = открытые/фановые столы.
GAME_TYPES = ("league", "lobby", "club", "competition", "tournament")
SCORINGS = ("scoring_1", "scoring_2", "scoring_3")
OFFLINE_TOURNAMENT_TYPE = "competition"
OPEN_GAME_TYPE = "lobby"
NO_OPEN_GAME_TYPES = ("league", "club", "competition", "tournament")
SLICE_TYPES = {
    "all_tournament": ("competition", "tournament"),
    "non_tournament": ("league", "lobby", "club"),
    "online": ("league", "lobby", "club", "tournament"),
    "offline": ("competition",),
    "open": ("lobby",),
    "no_open": NO_OPEN_GAME_TYPES,
}
SLICE_EXPORTS = (
    {
        "path": OUTPUT_OFFLINE_TOURNAMENT_CSV,
        "slice": "offline_tournament",
        "slice_label": "Оффлайн турниры",
        "game_type": OFFLINE_TOURNAMENT_TYPE,
    },
    {
        "path": OUTPUT_NO_OPEN_CSV,
        "slice": "no_open",
        "slice_label": "Без лобби (открытых/фановых игр)",
        "game_type": ",".join(NO_OPEN_GAME_TYPES),
    },
)


def unwrap_totals(data) -> dict:
    if isinstance(data, list):
        return data[0] if data else {}
    return data or {}


def merge_totals(*items) -> dict:
    int_keys = (
        "games_count",
        "wins_count",
        "first_killed_count",
        "fouls_count",
        "tech_fouls_count",
    )
    float_keys = ("points", "extra_points", "best_move_points")
    merged = {key: 0 for key in int_keys}
    merged.update({key: 0.0 for key in float_keys})
    for item in items:
        data = unwrap_totals(item)
        for key in int_keys:
            merged[key] += int(data.get(key) or 0)
        for key in float_keys:
            merged[key] += float(data.get(key) or 0)
    return merged


def totals_fields(data, prefix: str = "") -> dict:
    data = unwrap_totals(data)
    games = int(data.get("games_count") or 0)
    wins = int(data.get("wins_count") or 0)
    points = float(data.get("points") or 0)
    extra = float(data.get("extra_points") or 0)
    first_killed = int(data.get("first_killed_count") or 0)
    pfx = f"{prefix}_" if prefix else ""
    return {
        f"{pfx}games": games,
        f"{pfx}wins": wins,
        f"{pfx}winrate": pct(wins, games),
        f"{pfx}points": round(points, 2),
        f"{pfx}extra_points": round(extra, 2),
        f"{pfx}avg_score": round(points / games, 2) if games else None,
        f"{pfx}avg_extra_score": round(extra / games, 2) if games else None,
        f"{pfx}first_killed": first_killed,
        f"{pfx}first_killed_pct": pct(first_killed, games),
        f"{pfx}fouls": int(data.get("fouls_count") or 0),
        f"{pfx}tech_fouls": int(data.get("tech_fouls_count") or 0),
        f"{pfx}best_move_points": round(float(data.get("best_move_points") or 0), 2),
    }


def fetch_safe(path: str, params=None):
    try:
        data = get_json(f"{BASE_URL}{path}", params=params)
        time.sleep(0.12)
        return data
    except RuntimeError as exc:
        print(f"    [warn] {path}: {exc}", flush=True)
        time.sleep(0.5)
        return None


def load_directory() -> list[dict]:
    """Игроки из рейтинга федераций + топ MMR сайта."""
    directory = []
    seen = set()

    for federation_id in (1, 2, 3):
        rows = get_json(
            f"{APP_API_URL}/v1/competitions/scores",
            params={"federation": federation_id},
        )
        for row in rows or []:
            user_id = row.get("id")
            if not user_id or user_id in seen:
                continue
            seen.add(user_id)
            directory.append(
                {
                    "user_id": int(user_id),
                    "username": row.get("username") or "",
                    "mmr": None,
                    "competition_games": row.get("count"),
                    "competition_scores": row.get("totalScores"),
                    "competition_top1": row.get("top1"),
                    "competition_top3": row.get("top3"),
                    "competition_top10": row.get("top10"),
                    "city": row.get("city"),
                    "region": row.get("region"),
                }
            )
        time.sleep(0.2)

    try:
        top = get_json(f"{BASE_URL}/ratings/default/get-list", params={"limit": 1000})
    except RuntimeError as exc:
        print(f"[Warning] Топ MMR недоступен: {exc}")
        top = []

    by_id = {item["user_id"]: item for item in directory}
    for row in top or []:
        user_id = int(row.get("user_id") or 0)
        if not user_id:
            continue
        if user_id in by_id:
            by_id[user_id]["mmr"] = row.get("mmr")
            if not by_id[user_id]["username"]:
                by_id[user_id]["username"] = row.get("username") or ""
        else:
            directory.append(
                {
                    "user_id": user_id,
                    "username": row.get("username") or "",
                    "mmr": row.get("mmr"),
                    "competition_games": None,
                    "competition_scores": None,
                    "competition_top1": None,
                    "competition_top3": None,
                    "competition_top10": None,
                    "city": None,
                    "region": None,
                }
            )
            by_id[user_id] = directory[-1]
        seen.add(user_id)

    return directory


def match_player(poster_nick: str, directory: list[dict]) -> dict | None:
    wanted = [poster_nick, *NICK_ALIASES.get(poster_nick, [])]
    wanted_norm = [normalize_nick(name) for name in wanted if name]

    exact = [
        item
        for item in directory
        if normalize_nick(item["username"]) in wanted_norm
    ]
    if len(exact) == 1:
        return exact[0]
    if len(exact) > 1:
        exact.sort(key=lambda item: -float(item.get("competition_scores") or 0))
        return exact[0]

    partial = []
    for item in directory:
        uname = normalize_nick(item["username"])
        if any(w and (w in uname or uname in w) and min(len(w), len(uname)) >= 4 for w in wanted_norm):
            partial.append(item)
    if len(partial) == 1:
        return partial[0]
    if len(partial) > 1:
        partial.sort(key=lambda item: -float(item.get("competition_scores") or 0))
        return partial[0]
    return None


def stats_params(user_id: int) -> dict:
    return {
        "user_id": user_id,
        "date_from": DATE_FROM,
        "date_to": DATE_TO,
    }


def fetch_player_bundle(
    user_id: int,
    extra: dict | None = None,
    *,
    include_types: bool = True,
    include_scoring: bool = True,
    include_achievements: bool = True,
) -> dict:
    params = stats_params(user_id)
    if extra:
        params.update(extra)
    bundle = {
        "roles_split": fetch_safe("/profile/default/get-statistic", params) or {},
        "overall": unwrap_totals(
            fetch_safe("/profile/default/get-role-statistic", params)
        ),
        "by_role": {},
        "by_type": {},
        "by_scoring": {},
        "achievements": [],
    }
    for api_role, _prefix in ROLES:
        role_params = dict(params)
        role_params["role"] = api_role
        bundle["by_role"][api_role] = unwrap_totals(
            fetch_safe("/profile/default/get-role-statistic", role_params)
        )
    if include_types:
        for game_type in GAME_TYPES:
            type_params = dict(params)
            type_params["game_type"] = game_type
            bundle["by_type"][game_type] = unwrap_totals(
                fetch_safe("/profile/default/get-role-statistic", type_params)
            )
    if include_scoring:
        for scoring in SCORINGS:
            scoring_params = dict(params)
            scoring_params["scoring_type"] = scoring
            bundle["by_scoring"][scoring] = unwrap_totals(
                fetch_safe("/profile/default/get-role-statistic", scoring_params)
            )
    if include_achievements:
        achievements = fetch_safe(
            "/profile/default/get-achievements",
            {"userId": user_id},
        )
        if isinstance(achievements, list):
            bundle["achievements"] = achievements
    return bundle


def identity_record(poster_nick: str) -> dict:
    return {
        "poster_nick": poster_nick,
        "polemica_nick": None,
        "user_id": None,
        "profile_url": None,
        "mmr": None,
        "city": None,
        "region": None,
        "fed_events": None,
        "fed_scores": None,
        "fed_top1": None,
        "fed_top3": None,
        "fed_top10": None,
        "date_from": DATE_FROM,
        "date_to": DATE_TO,
        "achievements_count": None,
        "achievements": None,
        "error": None,
    }


def fill_identity(record: dict, player: dict) -> None:
    user_id = player["user_id"]
    record.update(
        {
            "polemica_nick": player["username"],
            "user_id": user_id,
            "profile_url": f"{BASE_URL}/profile/{user_id}",
            "mmr": player.get("mmr"),
            "city": player.get("city"),
            "region": player.get("region"),
            "fed_events": player.get("competition_games"),
            "fed_scores": (
                round(float(player["competition_scores"]), 2)
                if player.get("competition_scores") is not None
                else None
            ),
            "fed_top1": player.get("competition_top1"),
            "fed_top3": player.get("competition_top3"),
            "fed_top10": player.get("competition_top10"),
        }
    )


def apply_bundle(record: dict, bundle: dict, *, include_types: bool = True) -> None:
    overall = bundle["overall"]
    roles_split = bundle["roles_split"]
    if not overall and not roles_split:
        record["error"] = "статистика недоступна"
        return

    if overall:
        record.update(totals_fields(overall))
    for api_role, prefix in ROLES:
        detailed = bundle["by_role"].get(api_role) or {}
        if detailed.get("games_count"):
            record.update(totals_fields(detailed, prefix))
        else:
            fallback = (roles_split or {}).get(api_role) or {}
            record.update(totals_fields(fallback, prefix))
    if include_types:
        for game_type in GAME_TYPES:
            record.update(totals_fields(bundle["by_type"].get(game_type), game_type))
        for prefix, types in SLICE_TYPES.items():
            combined = merge_totals(*(bundle["by_type"].get(game_type) for game_type in types))
            record.update(totals_fields(combined, prefix))
    for scoring in SCORINGS:
        if scoring in bundle["by_scoring"]:
            record.update(totals_fields(bundle["by_scoring"].get(scoring), scoring))

    achieved = [
        item.get("name")
        for item in bundle["achievements"]
        if item.get("is_achieved")
    ]
    if bundle["achievements"]:
        record["achievements_count"] = len(achieved)
        record["achievements"] = "; ".join(achieved)


def build_record(poster_nick: str, player: dict | None) -> dict:
    record = identity_record(poster_nick)
    if not player:
        record["error"] = "игрок не найден"
        return record

    fill_identity(record, player)
    apply_bundle(record, fetch_player_bundle(player["user_id"]))
    return record


def build_slice_record(
    poster_nick: str,
    player: dict | None,
    *,
    slice_name: str,
    slice_label: str,
    game_type: str,
) -> dict:
    record = identity_record(poster_nick)
    record.update(
        {
            "slice": slice_name,
            "slice_label": slice_label,
            "game_type": game_type,
        }
    )
    if not player:
        record["error"] = "игрок не найден"
        return record

    fill_identity(record, player)
    apply_bundle(
        record,
        fetch_player_bundle(
            player["user_id"],
            {"game_type": game_type},
            include_types=False,
            include_achievements=False,
        ),
        include_types=False,
    )
    return record


def csv_val(row, *keys):
    for key in keys:
        if key in row and pd.notna(row.get(key)):
            return row.get(key)
    return None


def main():
    print(f"Период статистики: {DATE_FROM} — {DATE_TO}", flush=True)

    known = {}
    csv_path = Path(OUTPUT_CSV)
    if csv_path.exists():
        prev = pd.read_csv(csv_path)
        for _, row in prev.iterrows():
            if pd.notna(row.get("user_id")):
                known[row["poster_nick"]] = {
                    "user_id": int(row["user_id"]),
                    "username": row.get("polemica_nick") or "",
                    "mmr": csv_val(row, "mmr"),
                    "competition_games": csv_val(row, "fed_events", "competition_games"),
                    "competition_scores": csv_val(row, "fed_scores", "competition_scores"),
                    "competition_top1": csv_val(row, "fed_top1", "competition_top1"),
                    "competition_top3": csv_val(row, "fed_top3", "competition_top3"),
                    "competition_top10": csv_val(row, "fed_top10", "competition_top10"),
                    "city": row.get("city") if pd.notna(row.get("city")) else None,
                    "region": row.get("region") if pd.notna(row.get("region")) else None,
                }

    missing = [nick for nick in POSTER_NICKS if nick not in known]
    if missing:
        print("Загружаю справочник игроков Polemica…", flush=True)
        directory = load_directory()
        print(f"В справочнике {len(directory)} игроков", flush=True)
        for nick in missing:
            player = match_player(nick, directory)
            if player:
                known[nick] = player
    else:
        print("Беру сохранённые id игроков из CSV", flush=True)

    print("Обновляю очки оффлайн-турниров…", flush=True)
    try:
        directory = load_directory()
        by_id = {item["user_id"]: item for item in directory}
        for nick, player in known.items():
            extra = by_id.get(player["user_id"])
            if extra:
                player.update(extra)
    except RuntimeError as exc:
        print(f"[Warning] Рейтинг федерации недоступен: {exc}", flush=True)

    records = []
    slice_records = {item["slice"]: [] for item in SLICE_EXPORTS}
    for nick in POSTER_NICKS:
        player = known.get(nick)
        if player:
            print(f"  {nick} → {player['username']} (id={player['user_id']})", flush=True)
        else:
            print(f"  {nick} → не найден", flush=True)
        general = build_record(nick, player)
        records.append(general)
        time.sleep(0.35)
        for item in SLICE_EXPORTS:
            sliced = build_slice_record(
                nick,
                player,
                slice_name=item["slice"],
                slice_label=item["slice_label"],
                game_type=item["game_type"],
            )
            sliced["achievements_count"] = general.get("achievements_count")
            sliced["achievements"] = general.get("achievements")
            slice_records[item["slice"]].append(sliced)
            time.sleep(0.35)

    df = pd.DataFrame(records)
    df.to_csv(OUTPUT_CSV, index=False, encoding="utf-8-sig")
    found = df["user_id"].notna().sum()
    print(f"\nСохранено {found}/{len(df)} игроков в «{OUTPUT_CSV}»", flush=True)
    preview_cols = [
        "poster_nick",
        "games",
        "winrate",
        "all_tournament_games",
        "non_tournament_games",
        "online_games",
        "offline_games",
        "open_games",
        "no_open_games",
        "competition_games",
        "tournament_games",
        "lobby_games",
        "fed_scores",
        "error",
    ]
    print(df[preview_cols].to_string(index=False))

    slice_preview = [
        "poster_nick",
        "games",
        "winrate",
        "avg_score",
        "civilian_avg_score",
        "sheriff_avg_score",
        "mafia_avg_score",
        "don_avg_score",
        "error",
    ]
    for item in SLICE_EXPORTS:
        sliced_df = pd.DataFrame(slice_records[item["slice"]])
        sliced_df.to_csv(item["path"], index=False, encoding="utf-8-sig")
        sliced_found = sliced_df["user_id"].notna().sum()
        print(
            f"\nСохранено {sliced_found}/{len(sliced_df)} игроков в «{item['path']}»",
            flush=True,
        )
        print(sliced_df[slice_preview].to_string(index=False))


if __name__ == "__main__":
    main()
