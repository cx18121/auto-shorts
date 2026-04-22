"""
pipeline/analytics.py — Fetch and analyze video performance metrics.

Public API:
    fetch_youtube_stats(video_ids, api_key)          -> list[dict]
    fetch_instagram_insights(media_ids, access_token) -> list[dict]
    save_insights(conn, ...)                          -> None
    get_recent_uploads_without_insights(conn, ...)    -> list[dict]
    get_top_videos(conn, channel, ...)                -> list[dict]
    extract_hook_words(transcript_path, max_seconds) -> str
    extract_full_transcript(transcript_path)         -> str
    analyze_hook_effectiveness(hooks, views)          -> dict
    analyze_transcript_weighted(transcript_paths, views) -> dict
    analyze_title_patterns(titles)                   -> dict
    analyze_background_performance(conn, channel, days) -> list[dict]
    get_generation_recommendations(conn, channel, days) -> dict
    get_best_backgrounds(conn, channel, limit)        -> list[str]
    get_title_hints(conn, channel, limit)             -> list[str]
    get_hook_examples(conn, channel, limit)           -> list[str]
    get_body_style_hints(conn, channel)               -> str
"""

from __future__ import annotations

import json
import logging
import math
import random
import sqlite3
import time
from datetime import datetime, timezone, timedelta
from pathlib import Path
from typing import Optional

import requests

import config

logger = logging.getLogger(__name__)

_MAX_RETRIES = 3
_INSTAGRAM_RATE_LIMIT_DELAY = 20  # seconds between calls (200/hr limit)

# ---------------------------------------------------------------------------
# Fetch layer
# ---------------------------------------------------------------------------

def fetch_youtube_stats(video_ids: list[str], api_key: str) -> list[dict]:
    """Batch-fetch YouTube statistics AND publish date for up to 50 video IDs at once.

    Uses the YouTube Data API v3 videos.list endpoint with part=statistics,snippet.
    Each video ID costs 1 quota unit per part (batch is more efficient).

    Args:
        video_ids: List of YouTube video ID strings (max 50 per call).
        api_key:   YouTube Data API v3 key.

    Returns:
        List of dicts with keys: video_id, view_count, like_count,
        comment_count, published_at (ISO string or None).
    """
    if not video_ids or not api_key:
        return []

    results = []
    # Batch in groups of 50 (API limit)
    for i in range(0, len(video_ids), 50):
        batch = video_ids[i:i + 50]
        url = "https://www.googleapis.com/youtube/v3/videos"
        params = {
            "part": "statistics,snippet",
            "id": ",".join(batch),
            "key": api_key,
        }
        for attempt in range(1, _MAX_RETRIES + 1):
            try:
                resp = requests.get(url, params=params, timeout=10)
                resp.raise_for_status()
                data = resp.json()
                for item in data.get("items", []):
                    stats = item.get("statistics", {})
                    snippet = item.get("snippet", {})
                    results.append({
                        "video_id": item["id"],
                        "view_count": int(stats.get("viewCount", 0)),
                        "like_count": int(stats.get("likeCount", 0)),
                        "comment_count": int(stats.get("commentCount", 0)),
                        "published_at": snippet.get("publishedAt"),
                    })
                break
            except Exception as exc:
                logger.warning("YouTube stats batch fetch attempt %d failed: %s", attempt, exc)
                if attempt == _MAX_RETRIES:
                    logger.error("YouTube stats fetch failed after %d attempts", _MAX_RETRIES)
                else:
                    time.sleep(2 ** attempt)
    return results


def fetch_instagram_insights(
    media_ids: list[str],
    access_token: str,
) -> list[dict]:
    """Fetch Instagram insights for a list of media IDs (Reels published ≤ 30 days).

    Per-media GET to https://graph.instagram.com/{media_id}/insights.
    Throttles: 20 seconds between calls (200/hr rate limit).

    Args:
        media_ids:    List of Instagram media ID strings.
        access_token: Instagram/Meta long-lived access token.

    Returns:
        List of dicts with keys: media_id, views (reach), likes, comments,
        shares, saves, watch_time_seconds (None if not available).
    """
    if not media_ids:
        return []

    base_url = "https://graph.instagram.com/v19.0"
    results = []

    for mid in media_ids:
        for attempt in range(1, _MAX_RETRIES + 1):
            try:
                url = f"{base_url}/{mid}/insights"
                params = {
                    "metric": "reach,likes,comments,shares,saves,total_video_view_time",
                    "access_token": access_token,
                }
                resp = requests.get(url, params=params, timeout=15)
                if resp.status_code == 429:
                    logger.warning("Instagram rate limited, waiting 60s before retry")
                    time.sleep(60)
                    resp = requests.get(url, params=params, timeout=15)
                resp.raise_for_status()
                data = resp.json()
                metrics = {}
                for item in data.get("data", []):
                    m_name = item.get("name", "")
                    m_val = item.get("values", [{}])
                    val = m_val[0].get("value", 0) if m_val else 0
                    if m_name == "reach":
                        metrics["reach"] = int(val)
                    elif m_name == "likes":
                        metrics["likes"] = int(val)
                    elif m_name == "comments":
                        metrics["comments"] = int(val)
                    elif m_name == "shares":
                        metrics["shares"] = int(val)
                    elif m_name == "saves":
                        metrics["saves"] = int(val)
                    elif m_name == "total_video_view_time":
                        metrics["watch_time_seconds"] = int(val)
                results.append({
                    "media_id": mid,
                    "reach": metrics.get("reach"),
                    "likes": metrics.get("likes"),
                    "comments": metrics.get("comments"),
                    "shares": metrics.get("shares"),
                    "saves": metrics.get("saves"),
                    "watch_time_seconds": metrics.get("watch_time_seconds"),
                })
                break
            except Exception as exc:
                logger.warning("Instagram insights fetch for %s attempt %d failed: %s", mid, attempt, exc)
                if attempt == _MAX_RETRIES:
                    logger.error("Instagram insights fetch failed for media_id=%s", mid)
                else:
                    time.sleep(2 ** attempt)

        # Throttle: 200/hr = 1 call every 18s; use 20s to be safe
        time.sleep(_INSTAGRAM_RATE_LIMIT_DELAY)

    return results


def save_insights(
    conn: sqlite3.Connection,
    channel: str,
    platform: str,
    video_id: str,
    metrics: dict,
    title: Optional[str] = None,
    transcript_path: Optional[str] = None,
    bg_filename: Optional[str] = None,
    published_at: Optional[str] = None,
) -> None:
    """Insert or replace a video_insights row.

    Args:
        conn:           Active SQLite connection.
        channel:        Channel slug.
        platform:       'youtube' or 'instagram'.
        video_id:       Platform-assigned video/media ID.
        metrics:        Dict with keys: view_count, like_count, comment_count,
                       watch_time_seconds, reach, shares, saves (all optional ints).
        title:          Video title for denormalized reference.
        transcript_path: Path to timestamps.json (storytelling format).
        bg_filename:    Background clip filename used.
        published_at:   YouTube publish date (ISO 8601 string) — only for YouTube.
    """
    now = datetime.now(timezone.utc).isoformat()
    conn.execute("""
        INSERT OR REPLACE INTO video_insights
        (channel, platform, video_id, fetched_at, published_at,
         view_count, like_count, comment_count,
         watch_time_seconds, reach, shares, saves,
         title, transcript_path, bg_filename)
        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
    """, (
        channel, platform, video_id, now, published_at,
        metrics.get("view_count"),
        metrics.get("like_count"),
        metrics.get("comment_count"),
        metrics.get("watch_time_seconds"),
        metrics.get("reach"),
        metrics.get("shares"),
        metrics.get("saves"),
        title,
        transcript_path,
        bg_filename,
    ))
    conn.commit()


def get_recent_uploads_without_insights(
    conn: sqlite3.Connection,
    channel: str,
    platform: str,
    limit: int = 50,
    days: int = 30,
) -> list[dict]:
    """Return uploads that haven't had insights fetched yet.

    Args:
        conn:     Active SQLite connection with row_factory=sqlite3.Row.
        channel:  Channel slug.
        platform: 'youtube' or 'instagram'.
        limit:    Max records to return.
        days:     Only consider uploads from the last N days.

    Returns:
        List of dicts: [{video_id, title, uploaded_at, transcript_path, bg_filename}, ...]
    """
    rows = conn.execute("""
        SELECT u.video_id, u.title, u.uploaded_at,
               v.transcript_path, v.bg_filename
        FROM uploads u
        LEFT JOIN video_insights v ON
            v.channel = u.channel AND v.platform = u.platform AND v.video_id = u.video_id
        WHERE u.channel = ? AND u.platform = ? AND u.status = 'success'
          AND u.uploaded_at > datetime('now', ?)
          AND v.id IS NULL
        ORDER BY u.uploaded_at DESC
        LIMIT ?
    """, (channel, platform, f"-{days} days", limit)).fetchall()

    return [dict(row) for row in rows]


# ---------------------------------------------------------------------------
# Analysis layer — timestamp parsing
# ---------------------------------------------------------------------------

def extract_hook_words(transcript_path: str, max_seconds: float = 5.0) -> str:
    """Return the words spoken within the first `max_seconds` of a transcript.

    Reads a timestamps.json file (word-level timing from ElevenLabs).
    Accumulates words whose start time falls within max_seconds.
    Returns a single space-separated string.

    Args:
        transcript_path: Path to timestamps.json.
        max_seconds:     How many seconds of the beginning to capture (default 5.0).

    Returns:
        String of words in the hook window, e.g.
        "What if survival itself became your job description?"
    """
    try:
        with open(transcript_path, "r", encoding="utf-8") as f:
            timestamps = json.load(f)
    except (FileNotFoundError, json.JSONDecodeError):
        return ""

    words = []
    for entry in timestamps:
        if isinstance(entry, dict) and entry.get("start_ms") is not None:
            start_s = entry["start_ms"] / 1000.0
            if start_s > max_seconds:
                break
            word = entry.get("word", "")
            if word:
                words.append(word)
    return " ".join(words)


def extract_full_transcript(transcript_path: str) -> str:
    """Return all words from a timestamps.json concatenated into a string.

    Args:
        transcript_path: Path to timestamps.json.

    Returns:
        Full transcript string.
    """
    try:
        with open(transcript_path, "r", encoding="utf-8") as f:
            timestamps = json.load(f)
    except (FileNotFoundError, json.JSONDecodeError):
        return ""

    words = [entry.get("word", "") for entry in timestamps if entry.get("word")]
    return " ".join(words)


# ---------------------------------------------------------------------------
# Analysis layer — hook effectiveness
# ---------------------------------------------------------------------------

def analyze_hook_effectiveness(hooks: list[str], views: list[int]) -> dict:
    """Correlate hook text patterns with view counts.

    Analyzes:
    - Hook length (word count)
    - Hook structure: question vs statement vs exclamation
    - Stakes keywords: $, million, kill, survive, die, job, money, offer
    - Whether hook poses a problem/stakes scenario

    Returns:
        Dict with:
            avg_words_in_top_25pct: float
            question_ratio_top: float (fraction of top-25% that are questions)
            stakes_keywords_top: list[str] (most common stakes keywords in top quartile)
            hook_structure_top: str ("question", "statement", "exclamation")
            hook_length_avg: float (overall average hook length in words)
            has_stakes_ratio_top: float (fraction of top-25% with stakes framing)
    """
    if not hooks or len(hooks) != len(views):
        return {}

    # Sort by views descending, take top 25%
    sorted_pairs = sorted(zip(hooks, views), key=lambda x: x[1], reverse=True)
    cutoff = max(1, len(sorted_pairs) // 4)
    top_hooks = [h for h, _ in sorted_pairs[:cutoff]]
    all_hooks = [h for h, _ in sorted_pairs]

    def word_count(text: str) -> int:
        return len(text.split())

    def structure(text: str) -> str:
        text = text.strip()
        if text.endswith("?"):
            return "question"
        if text.endswith("!"):
            return "exclamation"
        return "statement"

    STAKE_KEYWORDS = {
        "$", "million", "billion", "kill", "die", "survive",
        "job", "money", "offer", "pay", "salary", "die", "death",
        "dead", "risk", "danger", "threat", "escape", "trapped",
    }

    def has_stakes(text: str) -> bool:
        lower = text.lower()
        return any(kw in lower for kw in STAKE_KEYWORDS)

    top_structures = [structure(h) for h in top_hooks]
    most_common_struct = max(set(top_structures), key=top_structures.count) if top_structures else "statement"

    top_word_counts = [word_count(h) for h in top_hooks]
    avg_words_top = sum(top_word_counts) / len(top_word_counts) if top_word_counts else 0

    all_word_counts = [word_count(h) for h in all_hooks]
    avg_words_all = sum(all_word_counts) / len(all_word_counts) if all_word_counts else 0

    question_ratio_top = sum(1 for h in top_hooks if structure(h) == "question") / len(top_hooks) if top_hooks else 0

    has_stakes_top = sum(1 for h in top_hooks if has_stakes(h)) / len(top_hooks) if top_hooks else 0

    # Keyword frequency in top quartile
    keyword_counts: dict[str, int] = {}
    for hook in top_hooks:
        for kw in STAKE_KEYWORDS:
            if kw in hook.lower():
                keyword_counts[kw] = keyword_counts.get(kw, 0) + 1
    top_keywords = sorted(keyword_counts, key=keyword_counts.get, reverse=True)[:10]

    return {
        "avg_words_in_top_25pct": round(avg_words_top, 1),
        "question_ratio_top": round(question_ratio_top, 2),
        "stakes_keywords_top": top_keywords,
        "hook_structure_top": most_common_struct,
        "hook_length_avg": round(avg_words_all, 1),
        "has_stakes_ratio_top": round(has_stakes_top, 2),
    }


# ---------------------------------------------------------------------------
# Analysis layer — weighted transcript analysis (hook 50% + body 50%)
# ---------------------------------------------------------------------------

def analyze_full_transcript(transcript_path: str) -> dict:
    """Analyze entire transcript for pacing, keywords, sentiment, and structure.

    Returns:
        Dict with: word_count, avg_wpm, top_keywords (list), sentiment (str),
        has_resolution (bool), sentence_count, pacing_stddev.
    """
    try:
        with open(transcript_path, "r", encoding="utf-8") as f:
            timestamps = json.load(f)
    except (FileNotFoundError, json.JSONDecodeError):
        return {}

    if not timestamps:
        return {}

    words = [entry.get("word", "") for entry in timestamps if entry.get("word")]
    if not words:
        return {}

    # Compute duration from first to last word
    first_ms = timestamps[0].get("start_ms", 0)
    last_entry = timestamps[-1]
    last_ms = last_entry.get("end_ms", last_entry.get("start_ms", 0))
    duration_s = (last_ms - first_ms) / 1000.0
    total_words = len(words)

    avg_wpm = (total_words / (duration_s / 60)) if duration_s > 0 else 0

    # Pacing: words-per-second per segment
    segments: list[float] = []
    for entry in timestamps:
        w = entry.get("word", "")
        start = entry.get("start_ms", 0)
        end = entry.get("end_ms", start)
        dur = (end - start) / 1000.0
        if dur > 0:
            segments.append(len(w) / dur)

    pacing_stddev = (sum((s - (total_words / duration_s)) ** 2 for s in segments) / len(segments)) ** 0.5 if len(segments) > 1 and duration_s > 0 else 0

    # Keyword frequency (normalized)
    STOPWORDS = {
        "the", "a", "an", "and", "or", "but", "in", "on", "at", "to", "for",
        "of", "with", "by", "from", "is", "was", "are", "be", "been", "being",
        "have", "has", "had", "do", "does", "did", "will", "would", "could",
        "should", "may", "might", "must", "shall", "can", "this", "that",
        "these", "those", "i", "you", "he", "she", "it", "we", "they", "what",
        "when", "where", "why", "how", "all", "each", "every", "both", "few",
        "more", "most", "other", "some", "such", "no", "not", "only", "same",
        "so", "than", "too", "very", "just", "also", "now", "here", "there",
        "then", "once", "if", "because", "as", "until", "while", "about",
        "after", "before", "above", "below", "between", "into", "through",
        "during", "under", "again", "further", "our", "my", "your", "his",
        "her", "its", "their", "who", "which", "whom", "this", "that",
    }

    word_freq: dict[str, int] = {}
    for word in words:
        w = word.lower().strip(".,!?\"':;()[]{}")
        if w and w not in STOPWORDS and len(w) > 2:
            word_freq[w] = word_freq.get(w, 0) + 1

    top_keywords = sorted(word_freq, key=word_freq.get, reverse=True)[:20]

    SENTIMENT_KEYWORDS = {
        "exciting": ["amazing", "incredible", "shocking", "unbelievable", "wow", "astonishing"],
        "suspenseful": ["suddenly", "but", "however", "yet", "meanwhile", "unexpected", "twist"],
        "conflict": ["fight", "battle", "war", "struggle", "challenge", "threat", "enemy"],
        "resolution": ["finally", "in the end", "resolved", "success", "victory", "escaped"],
        "emotional": ["love", "fear", "hope", "regret", "angry", "sad", "happy", "cry"],
    }

    sentiment_scores: dict[str, int] = {k: 0 for k in SENTIMENT_KEYWORDS}
    full_text = " ".join(words).lower()
    for sent, keywords in SENTIMENT_KEYWORDS.items():
        for kw in keywords:
            sentiment_scores[sent] += full_text.count(kw)

    dominant_sentiment = max(sentiment_scores, key=sentiment_scores.get) if sentiment_scores else "neutral"

    RESOLUTION_PHRASES = [
        "in the end", "finally", "resolved", "everything worked out",
        "they lived", "happily ever after", "victory", "success",
        "escaped", "survived", "got away",
    ]
    has_resolution = any(rp in full_text for rp in RESOLUTION_PHRASES)

    sentence_count = sum(1 for w in words if w[-1:] in ".!?")

    return {
        "word_count": total_words,
        "avg_wpm": round(avg_wpm),
        "pacing_stddev": round(pacing_stddev, 2),
        "top_keywords": top_keywords,
        "sentiment": dominant_sentiment,
        "has_resolution": has_resolution,
        "sentence_count": sentence_count,
    }


def analyze_transcript_weighted(transcript_paths: list[str], views: list[int]) -> dict:
    """Full transcript analysis with 50% hook weight + 50% body weight.

    For each video:
      - Hook (first 5s): 50% weight → analyzed for hook patterns
      - Body (remaining): 50% weight → analyzed for pacing, keywords, tone

    Aggregated across all videos, returns hook_patterns, body_patterns,
    and a unified_recommendation string.

    Args:
        transcript_paths: List of paths to timestamps.json files.
        views:            Corresponding view counts (parallel list).

    Returns:
        Dict with hook_patterns, body_patterns, unified_recommendation.
    """
    if not transcript_paths or len(transcript_paths) != len(views):
        return {}

    hook_texts = []
    body_texts = []
    top_views = sorted(views, reverse=True)[:10]  # top 10 for recommendations
    top_idx = sorted(range(len(views)), key=lambda i: views[i], reverse=True)[:10]

    for idx in top_idx:
        path = transcript_paths[idx]
        try:
            with open(path, "r", encoding="utf-8") as f:
                ts = json.load(f)
        except (FileNotFoundError, json.JSONDecodeError):
            continue

        words = [e.get("word", "") for e in ts if e.get("word")]
        hook_texts.append(" ".join(words[:15]))  # first ~15 words ≈ 5 seconds
        body_texts.append(" ".join(words[15:]))  # rest

    # Hook analysis (from top videos only)
    hook_results = []
    for path in transcript_paths:
        h = extract_hook_words(path, max_seconds=5.0)
        if h:
            hook_results.append(h)
    # Use top videos for hook patterns
    hook_views = [views[transcript_paths.index(p)] for p in transcript_paths[:len(hook_results)] if p in transcript_paths]
    hook_analysis = analyze_hook_effectiveness(hook_results[:len(hook_views)], hook_views[:len(hook_results)]) if hook_results else {}

    # Body analysis (full transcripts from top videos)
    body_analysis_results = []
    for idx in top_idx:
        analysis = analyze_full_transcript(transcript_paths[idx])
        if analysis:
            body_analysis_results.append(analysis)

    # Aggregate body patterns
    if body_analysis_results:
        avg_wpm = sum(a.get("avg_wpm", 0) for a in body_analysis_results) / len(body_analysis_results)
        keyword_freq: dict[str, int] = {}
        sentiments: dict[str, int] = {}
        resolution_count = sum(1 for a in body_analysis_results if a.get("has_resolution"))
        for a in body_analysis_results:
            for kw in a.get("top_keywords", []):
                keyword_freq[kw] = keyword_freq.get(kw, 0) + 1
            sent = a.get("sentiment", "neutral")
            sentiments[sent] = sentiments.get(sent, 0) + 1
        top_body_keywords = sorted(keyword_freq, key=keyword_freq.get, reverse=True)[:10]
        dominant_sentiment = max(sentiments, key=sentiments.get) if sentiments else "neutral"
        resolution_ratio = resolution_count / len(body_analysis_results)
    else:
        avg_wpm = 0
        top_body_keywords = []
        dominant_sentiment = "unknown"
        resolution_ratio = 0

    hook_struct = hook_analysis.get("hook_structure_top", "question")
    hook_stakes = hook_analysis.get("stakes_keywords_top", [])

    recommendation = (
        f"Start with a {hook_struct} in the first 5 words that establishes stakes"
        + (f" (e.g. '{hook_results[0] if hook_results else '...'}')" if hook_results else "")
        + f". Keep pace around {int(avg_wpm)} WPM."
        + f" Dominant tone: {dominant_sentiment}."
        + f" Resolution ratio in top performers: {int(resolution_ratio * 100)}%."
        + (f" Top body keywords: {', '.join(top_body_keywords[:5])}." if top_body_keywords else "")
    )

    return {
        "hook_patterns": hook_analysis,
        "body_patterns": {
            "avg_wpm": round(avg_wpm),
            "top_keywords": top_body_keywords,
            "dominant_sentiment": dominant_sentiment,
            "resolution_ratio": round(resolution_ratio, 2),
        },
        "unified_recommendation": recommendation,
    }


# ---------------------------------------------------------------------------
# Analysis layer — title patterns and background performance
# ---------------------------------------------------------------------------

def analyze_title_patterns(titles: list[str]) -> dict:
    """Detect patterns in video titles.

    Detects: prefixes ("What if", "Imagine", "AITA"), dollar amounts,
    question marks, word count, sentence structure.

    Returns:
        Dict with: prefixes (dict[str, int]), has_dollar (int),
        has_question (int), avg_word_count (float), title_examples (list[str]).
    """
    if not titles:
        return {}

    PREFIXES = ["what if", "imagine", "aita", "update:", "story:", "my", "the"]
    prefix_counts: dict[str, int] = {p: 0 for p in PREFIXES}

    question_count = 0
    dollar_count = 0
    word_counts = []
    examples = []

    for title in titles:
        lower = title.lower()
        for prefix in PREFIXES:
            if lower.startswith(prefix):
                prefix_counts[prefix] += 1
        if "?" in title:
            question_count += 1
        import re
        if re.search(r"\$\d+|\d+K|\d+million|\d+,\d+", title, re.IGNORECASE):
            dollar_count += 1
        words = title.split()
        word_counts.append(len(words))
        if len(examples) < 5:
            examples.append(title)

    return {
        "prefixes": prefix_counts,
        "has_dollar": dollar_count,
        "has_question": question_count,
        "avg_word_count": round(sum(word_counts) / len(word_counts), 1),
        "title_examples": examples[:5],
    }


def analyze_background_performance(
    conn: sqlite3.Connection,
    channel: str,
    days: int = 30,
) -> list[dict]:
    """Aggregate average views per background clip filename.

    Args:
        conn:     Active SQLite connection with row_factory=sqlite3.Row.
        channel:  Channel slug.
        days:     Lookback window in days.

    Returns:
        List of dicts sorted by avg_views descending:
        [{"bg": "geometry_dash.mp4", "avg_views": 18200, "count": 5}, ...]
    """
    rows = conn.execute("""
        SELECT vi.bg_filename, AVG(vi.view_count) as avg_views, COUNT(*) as cnt
        FROM video_insights vi
        WHERE vi.channel = ?
          AND vi.fetched_at > datetime('now', ?)
          AND vi.bg_filename IS NOT NULL
          AND vi.bg_filename != ''
        GROUP BY vi.bg_filename
        ORDER BY avg_views DESC
    """, (channel, f"-{days} days")).fetchall()

    return [
        {"bg": row["bg_filename"], "avg_views": int(row["avg_views"]), "count": row["cnt"]}
        for row in rows
    ]


# ---------------------------------------------------------------------------
# Recommendations for generation
# ---------------------------------------------------------------------------

def get_generation_recommendations(
    conn: sqlite3.Connection,
    channel: str,
    days: int = 30,
) -> dict:
    """Aggregate all signals into actionable recommendations for video generation.

    Returns:
        Dict with keys: title_hints (list[str]), hook_style (str),
        hook_examples (list[str]), body_style (str),
        preferred_backgrounds (list[str]), avoid (list[str]).
    """
    min_views = 100  # minimum views for a video to be considered "performant"

    # Top videos with content references
    top_videos = get_top_videos(conn, channel, metric="view_count",
                                min_views=min_views, limit=20, days=days)

    if not top_videos:
        return {
            "title_hints": [],
            "hook_style": "unknown — run fetch-analytics first to collect data",
            "hook_examples": [],
            "body_style": "",
            "preferred_backgrounds": [],
            "avoid": [],
        }

    titles = [v.get("title", "") for v in top_videos if v.get("title")]
    transcript_paths = [v.get("transcript_path") for v in top_videos if v.get("transcript_path")]
    views = [v.get("view_count", 0) for v in top_videos]

    title_analysis = analyze_title_patterns(titles)
    bg_analysis = analyze_background_performance(conn, channel, days)
    hook_analysis = analyze_hook_effectiveness(
        [extract_hook_words(p, 5.0) for p in transcript_paths if p],
        views,
    )
    transcript_weighted = analyze_transcript_weighted(
        [p for p in transcript_paths if p],
        views,
    )

    # Title hints
    title_hints: list[str] = []
    prefixes = title_analysis.get("prefixes", {})
    if prefixes.get("what if", 0) >= 2:
        title_hints.append("Start with 'What if...' or 'What would you do if...'")
    if prefixes.get("imagine", 0) >= 1:
        title_hints.append("Consider 'Imagine if...' as a title opener")
    if title_analysis.get("has_dollar", 0) >= 2:
        title_hints.append("Include a dollar amount or specific number")
    if title_analysis.get("has_question", 0) >= 3:
        title_hints.append("Use a compelling question as the title (ends with '?')")
    avg_wc = title_analysis.get("avg_word_count", 0)
    if avg_wc > 0:
        title_hints.append(f"Keep titles under {int(avg_wc + 5)} characters")
    if title_hints:
        title_hints.append("Keep title under 60 characters")

    # Hook examples from top videos
    hook_examples = []
    for path in transcript_paths:
        if path:
            hook = extract_hook_words(path, max_seconds=5.0)
            if hook:
                hook_examples.append(hook)
        if len(hook_examples) >= 3:
            break

    hook_style = hook_analysis.get("hook_structure_top", "question")
    stakes_ratio = hook_analysis.get("has_stakes_ratio_top", 0)
    if stakes_ratio > 0.5:
        hook_style += " with stakes framing"

    body_rec = transcript_weighted.get("unified_recommendation", "")
    preferred_backgrounds = [b["bg"] for b in bg_analysis[:3]]

    avoid: list[str] = []
    if hook_analysis.get("question_ratio_top", 0) > 0.6:
        avoid.append("Question-only hooks without stakes framing")
    if title_analysis.get("avg_word_count", 0) > 50:
        avoid.append("Titles over 60 characters")
    if not bg_analysis:
        avoid.append("Using unproven background clips (no data yet)")

    return {
        "title_hints": title_hints,
        "hook_style": f"Open with a {hook_style} in first 5 words that establishes a problem/stakes scenario",
        "hook_examples": hook_examples,
        "body_style": body_rec,
        "preferred_backgrounds": preferred_backgrounds,
        "avoid": avoid,
    }


# ---------------------------------------------------------------------------
# Query helpers for generation
# ---------------------------------------------------------------------------

def get_top_videos(
    conn: sqlite3.Connection,
    channel: str,
    metric: str = "view_count",
    min_views: int = 100,
    limit: int = 20,
    days: int = 30,
) -> list[dict]:
    """Get top performing videos with content references.

    Joins uploads + video_insights. Requires video_insights data.

    Args:
        conn:      Active SQLite connection with row_factory=sqlite3.Row.
        channel:   Channel slug.
        metric:    Sort column (default 'view_count').
        min_views: Minimum view_count to include.
        limit:     Max results.
        days:      Lookback window.

    Returns:
        List of dicts: [{video_id, view_count, title, transcript_path, bg_filename}, ...]
    """
    # Validate metric column
    valid_metrics = {"view_count", "like_count", "comment_count", "reach", "watch_time_seconds"}
    if metric not in valid_metrics:
        metric = "view_count"

    rows = conn.execute(f"""
        SELECT vi.video_id, vi.{metric}, u.title,
               vi.transcript_path, vi.bg_filename,
               vi.published_at,
               CAST(vi.view_count AS REAL) / MAX(1, julianday('now') - julianday(vi.published_at)) as views_per_day
        FROM video_insights vi
        JOIN uploads u ON u.video_id = vi.video_id
            AND u.channel = vi.channel AND u.platform = vi.platform
        WHERE vi.channel = ?
          AND vi.fetched_at > datetime('now', ?)
          AND vi.view_count >= ?
        ORDER BY views_per_day DESC
        LIMIT ?
    """, (channel, f"-{days} days", min_views, limit)).fetchall()

    return [dict(row) for row in rows]


def get_best_backgrounds(conn: sqlite3.Connection, channel: str, limit: int = 3) -> list[str]:
    """Return top-performing background filenames for a channel."""
    rows = conn.execute("""
        SELECT vi.bg_filename, AVG(vi.view_count) as avg_views
        FROM video_insights vi
        WHERE vi.channel = ?
          AND vi.bg_filename IS NOT NULL AND vi.bg_filename != ''
        GROUP BY vi.bg_filename
        ORDER BY avg_views DESC
        LIMIT ?
    """, (channel, limit)).fetchall()
    return [row["bg_filename"] for row in rows if row["bg_filename"]]


def get_title_hints(conn: sqlite3.Connection, channel: str, limit: int = 5) -> list[str]:
    """Return title pattern strings from top performers."""
    recs = get_generation_recommendations(conn, channel)
    hints = recs.get("title_hints", [])
    return hints[:limit]


def get_hook_examples(conn: sqlite3.Connection, channel: str, limit: int = 3) -> list[str]:
    """Return best-performing opening hook phrases (first ~5 seconds of transcript)."""
    top_videos = get_top_videos(conn, channel, limit=10, days=30)
    hooks = []
    for v in top_videos:
        path = v.get("transcript_path")
        if path:
            hook = extract_hook_words(path, max_seconds=5.0)
            if hook:
                hooks.append(hook)
        if len(hooks) >= limit:
            break
    return hooks


def get_body_style_hints(conn: sqlite3.Connection, channel: str) -> str:
    """Return full transcript style hints from top performers."""
    recs = get_generation_recommendations(conn, channel)
    return recs.get("body_style", "")