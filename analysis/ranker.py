"""
analysis/ranker.py — Score video performance and compute channel-level aggregates.

Public API:
    rank_channel(channel_id) -> dict    (returns channel-level aggregate stats)
"""

import json
import logging
import math
from collections import Counter
from datetime import datetime, timezone
from typing import Any

from analysis.db import get_connection

logger = logging.getLogger(__name__)

_MIN_AGE_DAYS = 3          # exclude videos younger than this
_TOP_PERFORMER_PCT = 0.20  # top 20% marked as high performers


def rank_channel(channel_id: str) -> dict[str, Any]:
    """Score all videos for a channel and mark top performers.

    Computes per-video derived metrics and channel-level aggregates, then
    writes everything back to SQLite.

    Args:
        channel_id: YouTube channel ID already in the database.

    Returns:
        Dict of channel-level aggregate statistics.
    """
    videos = _load_videos(channel_id)
    logger.info("Loaded %d videos for channel %s", len(videos), channel_id)

    now = datetime.now(timezone.utc)
    eligible = []
    for v in videos:
        pub = _parse_dt(v["published_at"])
        if pub is None:
            continue
        age_days = (now - pub).total_seconds() / 86400
        if age_days < _MIN_AGE_DAYS:
            logger.debug("Skipping %s (only %.1f days old)", v["id"], age_days)
            continue
        v = dict(v)   # make mutable
        v["_age_days"] = age_days
        v["_views_per_day"] = v["view_count"] / age_days if age_days > 0 else 0
        eligible.append(v)

    if not eligible:
        logger.warning("No eligible videos found for channel %s", channel_id)
        return {}

    avg_vpd = sum(v["_views_per_day"] for v in eligible) / len(eligible)
    threshold_score = sorted(
        [v["_views_per_day"] / max(avg_vpd, 1) for v in eligible],
        reverse=True
    )[max(0, math.floor(len(eligible) * _TOP_PERFORMER_PCT) - 1)]

    updated: list[dict[str, Any]] = []
    for v in eligible:
        score = v["_views_per_day"] / max(avg_vpd, 1)
        is_top = 1 if score >= threshold_score else 0
        pub = _parse_dt(v["published_at"])

        like_ratio    = v["like_count"]    / max(v["view_count"], 1)
        comment_ratio = v["comment_count"] / max(v["view_count"], 1)

        updated.append({
            "id":                     v["id"],
            "performance_score":      round(score, 4),
            "is_top_performer":       is_top,
            "title_length":           len(v["title"] or ""),
            "description_length":     len(v["description"] or ""),
            "like_to_view_ratio":     round(like_ratio, 6),
            "comment_to_view_ratio":  round(comment_ratio, 6),
            "hour_of_day_published":  pub.hour if pub else None,
            "day_of_week_published":  pub.weekday() if pub else None,  # 0=Mon
        })

    _save_scores(updated)
    logger.info("Scored %d videos; %d marked as top performers",
                len(updated), sum(v["is_top_performer"] for v in updated))

    aggregates = _compute_aggregates(eligible, updated)
    logger.info("Channel aggregates: posting_freq=%.1f days, top_duration=%.0fs",
                aggregates.get("avg_posting_frequency_days", 0),
                aggregates.get("avg_duration_top_performers", 0))
    return aggregates


# ---------------------------------------------------------------------------
# Aggregate computation
# ---------------------------------------------------------------------------

def _compute_aggregates(
    eligible: list[dict],
    scored: list[dict],
) -> dict[str, Any]:
    scored_map = {v["id"]: v for v in scored}
    top = [v for v in eligible if scored_map[v["id"]]["is_top_performer"]]

    def safe_avg(lst: list[float]) -> float:
        return sum(lst) / len(lst) if lst else 0.0

    # Title word frequencies for top performers
    all_title_words: list[str] = []
    for v in top:
        words = (v["title"] or "").lower().split()
        all_title_words.extend(w.strip("\"'.,!?") for w in words if len(w) > 3)
    top_title_words = [w for w, _ in Counter(all_title_words).most_common(20)]

    # Tag frequencies across top performers
    all_tags: list[str] = []
    for v in top:
        try:
            tags = json.loads(v["tags"] or "[]")
            all_tags.extend(t.lower() for t in tags)
        except (json.JSONDecodeError, TypeError):
            pass
    top_tags = [t for t, _ in Counter(all_tags).most_common(20)]

    # Posting frequency
    pub_dates = sorted(
        _parse_dt(v["published_at"])
        for v in eligible
        if _parse_dt(v["published_at"]) is not None
    )
    if len(pub_dates) >= 2:
        gaps = [(pub_dates[i + 1] - pub_dates[i]).total_seconds() / 86400
                for i in range(len(pub_dates) - 1)]
        posting_freq = safe_avg(gaps)
    else:
        posting_freq = 0.0

    # Best hour/day based on top-performer publication times
    top_hours   = [scored_map[v["id"]]["hour_of_day_published"]  for v in top if scored_map[v["id"]]["hour_of_day_published"] is not None]
    top_days    = [scored_map[v["id"]]["day_of_week_published"]   for v in top if scored_map[v["id"]]["day_of_week_published"]  is not None]
    day_names   = ["Monday", "Tuesday", "Wednesday", "Thursday", "Friday", "Saturday", "Sunday"]

    best_hours  = [h for h, _ in Counter(top_hours).most_common(3)]
    best_days   = [day_names[d] for d, _ in Counter(top_days).most_common(3) if d < 7]

    return {
        "avg_duration_top_performers":  safe_avg([v["duration_seconds"] for v in top]),
        "avg_duration_all":             safe_avg([v["duration_seconds"] for v in eligible]),
        "avg_posting_frequency_days":   round(posting_freq, 1),
        "most_common_tags":             top_tags,
        "most_common_title_words":      top_title_words,
        "best_performing_hour_of_day":  best_hours,
        "best_performing_day_of_week":  best_days,
        "num_eligible":                 len(eligible),
        "num_top_performers":           len(top),
    }


# ---------------------------------------------------------------------------
# Database helpers
# ---------------------------------------------------------------------------

def _load_videos(channel_id: str) -> list[Any]:
    with get_connection() as conn:
        return conn.execute(
            "SELECT * FROM videos WHERE channel_id=?", (channel_id,)
        ).fetchall()


def _save_scores(rows: list[dict[str, Any]]) -> None:
    with get_connection() as conn:
        conn.executemany("""
            UPDATE videos SET
                performance_score       = :performance_score,
                is_top_performer        = :is_top_performer,
                title_length            = :title_length,
                description_length      = :description_length,
                like_to_view_ratio      = :like_to_view_ratio,
                comment_to_view_ratio   = :comment_to_view_ratio,
                hour_of_day_published   = :hour_of_day_published,
                day_of_week_published   = :day_of_week_published
            WHERE id = :id
        """, rows)


def _parse_dt(s: str | None) -> datetime | None:
    if not s:
        return None
    try:
        return datetime.fromisoformat(s.replace("Z", "+00:00"))
    except (ValueError, AttributeError):
        return None
