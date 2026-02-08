from __future__ import annotations

import os
import sqlite3
from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Any, Dict, List

from flask import Flask, jsonify, request


DB_PATH = os.environ.get("X_GROWTH_DB", "x_growth.db")
X_DRY_RUN = os.environ.get("X_DRY_RUN", "true").lower() == "true"


@dataclass
class PostDraft:
    text: str
    publish_at: str
    campaign_name: str


class XClient:
    """Simple client abstraction.

    This intentionally supports a dry-run mode so users can validate automation
    without posting spam or violating platform policies.
    """

    def __init__(self, dry_run: bool = True) -> None:
        self.dry_run = dry_run

    def publish(self, text: str) -> Dict[str, Any]:
        if self.dry_run:
            return {
                "status": "dry_run",
                "tweet_id": f"dry-{int(datetime.now(tz=timezone.utc).timestamp())}",
            }

        # Real API integration would go here. Keeping this disabled by default
        # prevents accidental ToS violations.
        raise NotImplementedError(
            "Live posting is disabled in this template. Keep X_DRY_RUN=true until you add official X API integration."
        )


def get_conn() -> sqlite3.Connection:
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    return conn


def init_db() -> None:
    conn = get_conn()
    cur = conn.cursor()
    cur.execute(
        """
        CREATE TABLE IF NOT EXISTS campaigns (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            name TEXT NOT NULL,
            persona TEXT NOT NULL,
            audience TEXT NOT NULL,
            created_at TEXT NOT NULL
        )
        """
    )
    cur.execute(
        """
        CREATE TABLE IF NOT EXISTS posts (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            campaign_id INTEGER NOT NULL,
            text TEXT NOT NULL,
            publish_at TEXT NOT NULL,
            status TEXT NOT NULL,
            x_post_id TEXT,
            created_at TEXT NOT NULL,
            posted_at TEXT,
            FOREIGN KEY(campaign_id) REFERENCES campaigns(id)
        )
        """
    )
    cur.execute(
        """
        CREATE TABLE IF NOT EXISTS events (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            post_id INTEGER NOT NULL,
            event_type TEXT NOT NULL,
            value INTEGER NOT NULL,
            observed_at TEXT NOT NULL,
            FOREIGN KEY(post_id) REFERENCES posts(id)
        )
        """
    )
    conn.commit()
    conn.close()


app = Flask(__name__)
init_db()
client = XClient(dry_run=X_DRY_RUN)


@app.get("/health")
def health() -> Any:
    return jsonify({"status": "ok", "dry_run": X_DRY_RUN})


@app.post("/campaigns")
def create_campaign() -> Any:
    payload = request.get_json(force=True)
    required = ["name", "persona", "audience", "hooks", "hashtags", "start_at", "cadence_minutes"]
    missing = [k for k in required if k not in payload]
    if missing:
        return jsonify({"error": f"Missing fields: {', '.join(missing)}"}), 400

    hooks: List[str] = payload["hooks"]
    hashtags: List[str] = payload["hashtags"]
    cadence = int(payload["cadence_minutes"])

    conn = get_conn()
    cur = conn.cursor()
    created_at = datetime.now(tz=timezone.utc).isoformat()
    cur.execute(
        "INSERT INTO campaigns (name, persona, audience, created_at) VALUES (?, ?, ?, ?)",
        (payload["name"], payload["persona"], payload["audience"], created_at),
    )
    campaign_id = cur.lastrowid

    start = datetime.fromisoformat(payload["start_at"])
    drafts: List[PostDraft] = []
    for idx, hook in enumerate(hooks):
        when = start.timestamp() + idx * cadence * 60
        publish_at = datetime.fromtimestamp(when, tz=timezone.utc).isoformat()
        hash_str = " ".join(f"#{h.strip('#')}" for h in hashtags)
        text = f"{hook}\n\n{payload['persona']} insight for {payload['audience']}.\n\n{hash_str}".strip()
        drafts.append(PostDraft(text=text[:280], publish_at=publish_at, campaign_name=payload["name"]))
        cur.execute(
            """
            INSERT INTO posts (campaign_id, text, publish_at, status, created_at)
            VALUES (?, ?, ?, 'scheduled', ?)
            """,
            (campaign_id, text[:280], publish_at, created_at),
        )

    conn.commit()
    conn.close()

    return jsonify(
        {
            "campaign_id": campaign_id,
            "scheduled_posts": len(drafts),
            "posts": [draft.__dict__ for draft in drafts],
            "note": "Use /automation/run to publish due posts. Keep content compliant with X policies.",
        }
    )


@app.post("/automation/run")
def run_automation() -> Any:
    now = datetime.now(tz=timezone.utc).isoformat()
    conn = get_conn()
    cur = conn.cursor()
    rows = cur.execute(
        "SELECT id, text FROM posts WHERE status='scheduled' AND publish_at <= ? ORDER BY publish_at ASC",
        (now,),
    ).fetchall()

    published = []
    for row in rows:
        result = client.publish(row["text"])
        posted_at = datetime.now(tz=timezone.utc).isoformat()
        cur.execute(
            "UPDATE posts SET status='posted', posted_at=?, x_post_id=? WHERE id=?",
            (posted_at, result["tweet_id"], row["id"]),
        )
        published.append({"post_id": row["id"], **result})

    conn.commit()
    conn.close()
    return jsonify({"published_count": len(published), "published": published})


@app.post("/events")
def ingest_event() -> Any:
    payload = request.get_json(force=True)
    required = ["post_id", "event_type", "value"]
    missing = [k for k in required if k not in payload]
    if missing:
        return jsonify({"error": f"Missing fields: {', '.join(missing)}"}), 400

    if payload["event_type"] not in {"impression", "like", "reply", "repost", "follow"}:
        return jsonify({"error": "Unsupported event_type"}), 400

    conn = get_conn()
    cur = conn.cursor()
    cur.execute(
        "INSERT INTO events (post_id, event_type, value, observed_at) VALUES (?, ?, ?, ?)",
        (
            int(payload["post_id"]),
            payload["event_type"],
            int(payload["value"]),
            datetime.now(tz=timezone.utc).isoformat(),
        ),
    )
    conn.commit()
    conn.close()
    return jsonify({"status": "recorded"})


@app.get("/analytics/summary")
def analytics_summary() -> Any:
    conn = get_conn()
    cur = conn.cursor()

    totals = {
        row["event_type"]: row["sum_value"]
        for row in cur.execute(
            "SELECT event_type, COALESCE(SUM(value),0) as sum_value FROM events GROUP BY event_type"
        ).fetchall()
    }

    posts_count = cur.execute("SELECT COUNT(*) as c FROM posts").fetchone()["c"]
    posted_count = cur.execute("SELECT COUNT(*) as c FROM posts WHERE status='posted'").fetchone()["c"]
    conn.close()

    impressions = totals.get("impression", 0)
    engagement = totals.get("like", 0) + totals.get("reply", 0) + totals.get("repost", 0)
    engagement_rate = (engagement / impressions) if impressions else 0

    return jsonify(
        {
            "posts_total": posts_count,
            "posts_published": posted_count,
            "followers_gained": totals.get("follow", 0),
            "engagement_rate": round(engagement_rate, 4),
            "totals": totals,
        }
    )


@app.get("/posts")
def list_posts() -> Any:
    conn = get_conn()
    rows = conn.execute(
        "SELECT id, campaign_id, text, publish_at, status, x_post_id, posted_at FROM posts ORDER BY publish_at ASC"
    ).fetchall()
    conn.close()
    return jsonify([dict(r) for r in rows])


if __name__ == "__main__":
    app.run(host="0.0.0.0", port=5000)
