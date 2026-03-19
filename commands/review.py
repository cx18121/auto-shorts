"""
commands/review.py — Backlog review command (interactive or AI-assisted).
"""

import logging

import config

logger = logging.getLogger(__name__)

_HAIKU_MODEL = "claude-haiku-4-5-20251001"


def _ai_review_item(item: dict, source_label: str, channel_cfg) -> tuple[str, str]:
    """Ask Claude whether to approve or reject a backlog item.

    Returns (decision, reason) where decision is 'approve' or 'reject'.
    """
    import time
    import anthropic
    from pipeline.claude_utils import strip_markdown_fences

    if source_label == "Reddit":
        content_block = (
            f"Subreddit: r/{item['subreddit']}\n"
            f"Score: {item['score']:,}  Words: {item['word_count']}\n"
            f"Title: {item['title']}\n\n"
            f"{item['body'][:800]}"
        )
        content_type = "Reddit story"
    else:
        content_block = (
            f"Author: @{item['username']}\n"
            f"Likes: {item['likes']:,}  Retweets: {item['retweets']:,}\n\n"
            f"{item['tweet_text']}"
        )
        content_type = "tweet"

    prompt = (
        f"You are reviewing {content_type}s for a YouTube Shorts channel called \"{channel_cfg.name}\".\n"
        f"The channel niche is: {channel_cfg.slug.replace('-', ' ')}.\n\n"
        f"Decide whether this {content_type} would make an engaging, high-quality YouTube Short.\n"
        f"Approve if it has a strong hook, emotional engagement, and suits the niche.\n"
        f"Reject if it is boring, too short, off-topic, or low quality.\n\n"
        f"CONTENT:\n{content_block}\n\n"
        f'Return exactly this JSON: {{"decision": "approve" or "reject", "reason": "one sentence"}}'
    )

    import json
    client = anthropic.Anthropic(api_key=config.ANTHROPIC_API_KEY)
    for attempt in range(1, 4):
        try:
            resp = client.messages.create(
                model=_HAIKU_MODEL,
                max_tokens=128,
                temperature=0.2,
                messages=[{"role": "user", "content": prompt}],
            )
            result = json.loads(strip_markdown_fences(resp.content[0].text))
            decision = result.get("decision", "reject").lower()
            if decision not in ("approve", "reject"):
                decision = "reject"
            return decision, result.get("reason", "")
        except Exception as e:
            logger.warning("AI review attempt %d failed: %s", attempt, e)
            if attempt == 3:
                return "reject", f"evaluation error: {e}"
            time.sleep(2 ** attempt)
    return "reject", "all attempts failed"


def cmd_review(channel_cfg, ai: bool = False) -> None:
    """Review pending backlog items — interactively or via Claude (--ai)."""
    from analysis.db import get_connection
    from pipeline.backlog import (
        get_pending_stories, get_pending_tweets,
        approve_item, reject_item, get_probation_remaining,
    )

    conn = get_connection()
    try:
        probation_left = get_probation_remaining(conn, channel_cfg.slug)
        if probation_left > 0:
            print(f"\n[{channel_cfg.slug}] Auto-approve activates after "
                  f"{probation_left} more manual review(s).")
        else:
            print(f"\n[{channel_cfg.slug}] Auto-approve is ACTIVE.")

        if channel_cfg.format == "tweets":
            items        = get_pending_tweets(conn, channel_cfg.slug)
            source_label = "Twitter"
            table        = "backlog_tweets"
            id_key       = "tweet_id"
        else:
            items        = get_pending_stories(conn, channel_cfg.slug)
            source_label = "Reddit"
            table        = "backlog_stories"
            id_key       = "id"

        if not items:
            print(f"No pending {source_label} items for [{channel_cfg.slug}].")
            return

        print(f"\nReviewing {len(items)} pending {source_label} item(s) for [{channel_cfg.slug}]")
        if ai:
            print("Mode: AI (Claude) auto-review\n")
        else:
            print("Commands: y=approve  n=reject  s=skip\n")

        approved_count = rejected_count = 0

        for item in items:
            item_id = item[id_key]
            if source_label == "Reddit":
                print(f"--- Reddit | r/{item['subreddit']} ---")
                print(f"Score: {item['score']:,}  Words: {item['word_count']}")
                print(f"\n{item['title']}\n\n{item['body'][:500]}{'...' if len(item['body']) > 500 else ''}")
            else:
                print(f"--- Twitter | @{item['username']} ---")
                print(f"Likes: {item['likes']:,}  Retweets: {item['retweets']:,}")
                print(f"\n{item['tweet_text']}")

            if ai:
                decision, reason = _ai_review_item(dict(item), source_label, channel_cfg)
                print(f"  AI decision: {decision.upper()} — {reason}")
                if decision == "approve":
                    approve_item(conn, table, item_id, channel_cfg.slug)
                    conn.commit()
                    approved_count += 1
                else:
                    reject_item(conn, table, item_id, channel_cfg.slug)
                    conn.commit()
                    rejected_count += 1
            else:
                try:
                    choice = input("\nApprove? (y/n/skip): ").strip().lower()
                except (EOFError, KeyboardInterrupt):
                    print("\nReview session ended.")
                    break

                if choice == "y":
                    approve_item(conn, table, item_id, channel_cfg.slug)
                    conn.commit()
                    print("  Approved.")
                elif choice == "n":
                    reject_item(conn, table, item_id, channel_cfg.slug)
                    conn.commit()
                    print("  Rejected.")
                else:
                    print("  Skipped.")

        if ai:
            print(f"\nAI review complete: {approved_count} approved, {rejected_count} rejected.")
    finally:
        conn.close()
