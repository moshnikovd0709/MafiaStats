from __future__ import annotations

import csv
import json
import threading
import time
from json import JSONDecoder
from pathlib import Path

import pandas as pd
import requests

from script import (
    BASE_URL,
    DATE_FROM,
    DATE_TO,
    HEADERS,
    OUTPUT_OFFLINE_TOURNAMENT_CSV,
    get_json,
)

OUT_DIR = Path("data/offline_tournament")
GAMES_DIR = OUT_DIR / "games"
INDEX_CSV = OUT_DIR / "index.csv"
JSONL_PATH = OUT_DIR / "games.jsonl"
ERRORS_CSV = OUT_DIR / "download_errors.csv"
MANIFEST_PATH = OUT_DIR / "manifest.json"

GAMES_PAGE_LIMIT = 50
DOWNLOAD_WORKERS = 6
REQUEST_PAUSE = 0.08

thread_local = threading.local()


def thread_session() -> requests.Session:
    session = getattr(thread_local, "session", None)
    if session is None:
        session = requests.Session()
        session.headers.update(HEADERS)
        thread_local.session = session
    return session


def load_tracked_players() -> list[dict]:
    df = pd.read_csv(OUTPUT_OFFLINE_TOURNAMENT_CSV)
    players = []
    for _, row in df.iterrows():
        if pd.isna(row.get("user_id")):
            continue
        players.append(
            {
                "poster_nick": row["poster_nick"],
                "polemica_nick": row.get("polemica_nick"),
                "user_id": int(row["user_id"]),
            }
        )
    return players


def game_date(row: dict) -> str:
    return str(row.get("date_start") or "")[:10]


def is_offline_tournament_in_period(row: dict) -> bool:
    mode = ((row.get("game_mode") or {}).get("value") or "").strip()
    if mode != "competition":
        return False
    date = game_date(row)
    return bool(date) and DATE_FROM <= date <= DATE_TO


def iter_user_games(user_id: int):
    page = 1
    while True:
        payload = get_json(
            f"{BASE_URL}/profile/default/get-games",
            params={"userId": user_id, "page": page, "limit": GAMES_PAGE_LIMIT},
        )
        rows = payload.get("rows") or []
        if not rows:
            return
        yield from rows
        oldest = game_date(rows[-1])
        total = int(payload.get("totalCount") or 0)
        if oldest and oldest < DATE_FROM:
            return
        if page * GAMES_PAGE_LIMIT >= total:
            return
        page += 1
        time.sleep(REQUEST_PAUSE)


def collect_game_ids(players: list[dict]) -> tuple[dict[int, dict], list[dict]]:
    games: dict[int, dict] = {}
    listing_errors = []
    for player in players:
        user_id = player["user_id"]
        nick = player["poster_nick"]
        print(f"Список игр: {nick} (id={user_id})", flush=True)
        found = 0
        try:
            for row in iter_user_games(user_id):
                if not is_offline_tournament_in_period(row):
                    continue
                game_id = int(row["id"])
                found += 1
                item = games.setdefault(
                    game_id,
                    {
                        "game_id": game_id,
                        "type": row.get("type"),
                        "date_start": row.get("date_start"),
                        "game_mode": (row.get("game_mode") or {}).get("value"),
                        "seen_by_ids": [],
                        "seen_by_nicks": [],
                    },
                )
                if user_id not in item["seen_by_ids"]:
                    item["seen_by_ids"].append(user_id)
                    item["seen_by_nicks"].append(nick)
        except Exception as exc:
            listing_errors.append({"user_id": user_id, "poster_nick": nick, "error": str(exc)})
            print(f"  [error] {nick}: {exc}", flush=True)
            continue
        print(f"  оффлайн-турнирных в периоде: {found}", flush=True)
        time.sleep(REQUEST_PAUSE)
    return games, listing_errors


def extract_game_data(html: str) -> dict:
    marker = ":game-data='"
    idx = html.find(marker)
    if idx < 0:
        marker = ':game-data="'
        idx = html.find(marker)
        if idx < 0:
            raise ValueError("в HTML нет :game-data")
    raw = html[idx + len(marker) :]
    data, _end = JSONDecoder().raw_decode(raw)
    return data


def fetch_match_payload(game_id: int, game_type: str | None) -> tuple[dict, str]:
    urls = []
    if game_type == "match":
        urls.append(f"{BASE_URL}/match/{game_id}")
        urls.append(f"{BASE_URL}/game-statistics/{game_id}")
    else:
        urls.append(f"{BASE_URL}/game-statistics/{game_id}")
        urls.append(f"{BASE_URL}/match/{game_id}")
    session = thread_session()
    last_error = None
    for url in urls:
        try:
            resp = session.get(url, timeout=25)
            if resp.status_code == 404:
                last_error = f"404 {url}"
                continue
            resp.raise_for_status()
            payload = extract_game_data(resp.text)
            payload["_source_url"] = url
            return payload, url
        except Exception as exc:
            last_error = str(exc)
            time.sleep(0.4)
    raise RuntimeError(last_error or "не удалось скачать матч")


def index_row(meta: dict, payload: dict | None, url: str | None, error: str | None) -> dict:
    data = (payload or {}).get("data") or {}
    scored = (payload or {}).get("players") or []
    return {
        "game_id": meta["game_id"],
        "date_start": meta.get("date_start") or payload.get("started_at") if payload else meta.get("date_start"),
        "type": meta.get("type") or payload.get("type") if payload else meta.get("type"),
        "table": data.get("table"),
        "num": data.get("num"),
        "scoring_version": data.get("scoringVersion"),
        "judge": ((payload or {}).get("judge") or {}).get("username") or (data.get("referee") or {}).get("username"),
        "winner_code": (payload or {}).get("winnerCode"),
        "first_killed": (payload or {}).get("firstKilled"),
        "best_player": ((payload or {}).get("bestPlayer") or {}).get("username"),
        "our_player_count": len(meta.get("seen_by_nicks") or []),
        "our_players": "; ".join(meta.get("seen_by_nicks") or []),
        "table_players": "; ".join(item.get("username") or "" for item in scored),
        "source_url": url or "",
        "error": error or "",
    }


def download_one(meta: dict) -> tuple[int, dict | None, str | None, str | None]:
    game_id = meta["game_id"]
    path = GAMES_DIR / f"{game_id}.json"
    if path.exists():
        try:
            payload = json.loads(path.read_text(encoding="utf-8"))
            return game_id, payload, payload.get("_source_url"), None
        except Exception:
            pass
    try:
        payload, url = fetch_match_payload(game_id, meta.get("type"))
        path.write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
        time.sleep(REQUEST_PAUSE)
        return game_id, payload, url, None
    except Exception as exc:
        return game_id, None, None, str(exc)


def write_index(rows: list[dict]) -> None:
    if not rows:
        INDEX_CSV.write_text("", encoding="utf-8-sig")
        return
    fieldnames = list(rows[0].keys())
    with INDEX_CSV.open("w", encoding="utf-8-sig", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=fieldnames)
        writer.writeheader()
        writer.writerows(rows)


def tracked_ids(players: list[dict]) -> dict[int, str]:
    return {item["user_id"]: item["poster_nick"] for item in players}


def roster_user_ids(payload: dict) -> set[int]:
    ids: set[int] = set()
    for item in payload.get("players") or []:
        if item.get("id") is not None:
            ids.add(int(item["id"]))
    for item in (payload.get("data") or {}).get("players") or []:
        if item.get("player") is not None:
            ids.add(int(item["player"]))
    return ids


def prune_to_tracked_rosters(games: dict[int, dict], players: list[dict]) -> dict[int, dict]:
    """Drop matches that got into a profile list but do not include our players at the table."""
    id_to_nick = tracked_ids(players)
    kept: dict[int, dict] = {}
    removed = 0
    for game_id, meta in games.items():
        path = GAMES_DIR / f"{game_id}.json"
        if not path.exists():
            continue
        payload = json.loads(path.read_text(encoding="utf-8"))
        ours = roster_user_ids(payload) & set(id_to_nick)
        if not ours:
            path.unlink()
            removed += 1
            continue
        meta["seen_by_ids"] = sorted(ours)
        meta["seen_by_nicks"] = [id_to_nick[user_id] for user_id in meta["seen_by_ids"]]
        kept[game_id] = meta
    print(f"Убрано игр без наших игроков за столом: {removed}; осталось {len(kept)}", flush=True)
    return kept


def rebuild_jsonl() -> int:
    count = 0
    with JSONL_PATH.open("w", encoding="utf-8") as handle:
        for path in sorted(GAMES_DIR.glob("*.json"), key=lambda item: int(item.stem)):
            payload = json.loads(path.read_text(encoding="utf-8"))
            handle.write(json.dumps(payload, ensure_ascii=False) + "\n")
            count += 1
    return count


def main() -> None:
    OUT_DIR.mkdir(parents=True, exist_ok=True)
    GAMES_DIR.mkdir(parents=True, exist_ok=True)

    players = load_tracked_players()
    print(
        f"Игроков: {len(players)}; период {DATE_FROM} — {DATE_TO}; тип competition (оффлайн-турниры)",
        flush=True,
    )
    games, listing_errors = collect_game_ids(players)
    print(f"Уникальных игр: {len(games)}", flush=True)

    from concurrent.futures import ThreadPoolExecutor, as_completed

    index_rows = []
    errors = list(listing_errors)
    payloads: dict[int, dict] = {}
    urls: dict[int, str] = {}
    ok = 0
    metas = [games[game_id] for game_id in sorted(games)]
    with ThreadPoolExecutor(max_workers=DOWNLOAD_WORKERS) as pool:
        futures = {pool.submit(download_one, meta): meta for meta in metas}
        done = 0
        for future in as_completed(futures):
            meta = futures[future]
            game_id, payload, url, error = future.result()
            done += 1
            if error:
                errors.append({"game_id": game_id, "error": error})
                print(f"  [fail] {game_id}: {error}", flush=True)
            else:
                ok += 1
                if payload is not None:
                    payloads[game_id] = payload
                    if url:
                        urls[game_id] = url
            if done % 50 == 0 or done == len(metas):
                print(
                    f"Скачано {done}/{len(metas)} (ok={ok}, fail={len([row for row in errors if 'game_id' in row])})",
                    flush=True,
                )

    games = prune_to_tracked_rosters(games, players)
    for game_id, meta in sorted(games.items()):
        payload = payloads.get(game_id)
        if payload is None:
            payload = json.loads((GAMES_DIR / f"{game_id}.json").read_text(encoding="utf-8"))
        index_rows.append(
            index_row(
                meta,
                payload,
                urls.get(game_id) or (payload or {}).get("_source_url"),
                None,
            )
        )

    index_rows.sort(key=lambda row: (str(row.get("date_start") or ""), row["game_id"]))
    write_index(index_rows)
    rebuild_jsonl()

    if errors:
        with ERRORS_CSV.open("w", encoding="utf-8-sig", newline="") as handle:
            writer = csv.DictWriter(handle, fieldnames=sorted({key for row in errors for key in row}))
            writer.writeheader()
            writer.writerows(errors)

    manifest = {
        "date_from": DATE_FROM,
        "date_to": DATE_TO,
        "game_type": "competition",
        "slice": "offline_tournament",
        "tracked_players": len(players),
        "unique_games_listed": ok,
        "unique_games": len(games),
        "downloaded_ok": len(games),
        "failed": len([row for row in errors if "game_id" in row]),
        "listing_errors": len(listing_errors),
        "games_dir": str(GAMES_DIR),
        "jsonl": str(JSONL_PATH),
        "index": str(INDEX_CSV),
    }
    MANIFEST_PATH.write_text(json.dumps(manifest, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(json.dumps(manifest, ensure_ascii=False, indent=2), flush=True)


if __name__ == "__main__":
    main()
