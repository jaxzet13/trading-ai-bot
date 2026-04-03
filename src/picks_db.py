"""
SQLite access layer for BetLab AI Discord bot.
Stores picks, outcomes, and per-user request tracking for free-tier rate limiting.
"""

import sqlite3
import os
from datetime import datetime, timezone, timedelta

DB_PATH = os.environ.get("DISCORD_DB_PATH", "betlab_picks.db")


def get_conn() -> sqlite3.Connection:
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA foreign_keys = ON")
    return conn


def init_db() -> None:
    """Create tables if they don't exist. Safe to call multiple times."""
    with get_conn() as conn:
        conn.executescript("""
            CREATE TABLE IF NOT EXISTS picks (
                id                  INTEGER PRIMARY KEY AUTOINCREMENT,
                sport               TEXT NOT NULL,
                home_team           TEXT NOT NULL,
                away_team           TEXT NOT NULL,
                pick_type           TEXT NOT NULL,
                recommendation      TEXT NOT NULL,
                confidence          INTEGER NOT NULL,
                odds                TEXT NOT NULL,
                game_time           TEXT NOT NULL,
                analysis_text       TEXT NOT NULL,
                posted_at           TEXT,
                outcome             TEXT,
                discord_message_id  TEXT,
                created_at          TEXT NOT NULL
            );

            CREATE TABLE IF NOT EXISTS pick_requests (
                id              INTEGER PRIMARY KEY AUTOINCREMENT,
                user_id         TEXT NOT NULL,
                pick_id         INTEGER NOT NULL REFERENCES picks(id),
                requested_at    TEXT NOT NULL
            );
        """)


def save_pick(
    sport: str,
    home_team: str,
    away_team: str,
    pick_type: str,
    recommendation: str,
    confidence: int,
    odds: str,
    game_time: str,
    analysis_text: str,
) -> int:
    """Insert a new pick and return its id."""
    now = datetime.now(tz=timezone.utc).isoformat()
    with get_conn() as conn:
        cur = conn.execute(
            """
            INSERT INTO picks
                (sport, home_team, away_team, pick_type, recommendation,
                 confidence, odds, game_time, analysis_text, created_at)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (sport, home_team, away_team, pick_type, recommendation,
             confidence, odds, game_time, analysis_text, now),
        )
        return cur.lastrowid


def get_todays_picks(sport: str = None) -> list:
    """Return all picks created today, optionally filtered by sport."""
    with get_conn() as conn:
        if sport:
            rows = conn.execute(
                "SELECT * FROM picks WHERE DATE(created_at) = DATE('now') AND sport = ?",
                (sport,),
            ).fetchall()
        else:
            rows = conn.execute(
                "SELECT * FROM picks WHERE DATE(created_at) = DATE('now')"
            ).fetchall()
        return [dict(r) for r in rows]


def _build_record(rows) -> dict:
    record = {"wins": 0, "losses": 0, "pushes": 0, "pending": 0}
    for row in rows:
        outcome = row["outcome"]
        if outcome == "WIN":
            record["wins"] += 1
        elif outcome == "LOSS":
            record["losses"] += 1
        elif outcome == "PUSH":
            record["pushes"] += 1
        else:
            record["pending"] += 1
    return record


def get_todays_record() -> dict:
    with get_conn() as conn:
        rows = conn.execute(
            "SELECT outcome FROM picks WHERE DATE(created_at) = DATE('now')"
        ).fetchall()
    return _build_record(rows)


def get_weekly_record() -> dict:
    cutoff = (datetime.now(tz=timezone.utc) - timedelta(days=7)).isoformat()
    with get_conn() as conn:
        rows = conn.execute(
            "SELECT outcome FROM picks WHERE created_at >= ?", (cutoff,)
        ).fetchall()
    return _build_record(rows)


def mark_pick_posted(pick_id: int, message_id: str) -> None:
    now = datetime.now(tz=timezone.utc).isoformat()
    with get_conn() as conn:
        conn.execute(
            "UPDATE picks SET posted_at = ?, discord_message_id = ? WHERE id = ?",
            (now, message_id, pick_id),
        )


def update_outcome(pick_id: int, outcome: str) -> None:
    """Set outcome to WIN, LOSS, or PUSH."""
    with get_conn() as conn:
        conn.execute(
            "UPDATE picks SET outcome = ? WHERE id = ?", (outcome, pick_id)
        )


def count_user_requests_today(user_id: str) -> int:
    with get_conn() as conn:
        row = conn.execute(
            """
            SELECT COUNT(*) as cnt FROM pick_requests
            WHERE user_id = ? AND DATE(requested_at) = DATE('now')
            """,
            (user_id,),
        ).fetchone()
    return row["cnt"]


def log_user_request(user_id: str, pick_id: int) -> None:
    now = datetime.now(tz=timezone.utc).isoformat()
    with get_conn() as conn:
        conn.execute(
            "INSERT INTO pick_requests (user_id, pick_id, requested_at) VALUES (?, ?, ?)",
            (user_id, pick_id, now),
        )
