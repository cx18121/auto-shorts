"""
commands/review.py — Backlog review command (interactive or AI-assisted).
"""

import logging

import config

logger = logging.getLogger(__name__)

_HAIKU_MODEL = "claude-haiku-4-5-20251001"
_MAX_RETRIES = 3
_BATCH_SIZE = 50
_CONTENT_TRUNCATE = 400


def _build_content_block(item: dict, source_label: str) -> str:
    """Build the content block string for a single item (used in both single and batch review)."""
    if source_label == "Reddit":
        body_preview = item.get("body", "")[:_CONTENT_TRUNCATE]
        return (
            f"Subreddit: r/{item['subreddit']}\n"
            f"Score: {item['score']:,}  Words: {item['word_count']}\n"
            f"Title: {item['title']}\n\n"
            f"{body_preview}"
        )
    else:
        return (
            f"Author: @{item['username']}\n"
            f"Likes: {item['likes']:,}  Retweets: {item['retweets']:,}\n\n"
            f"{item['tweet_text'][:_CONTENT_TRUNCATE]}"
        )


def _ai_review_batch(
    items: list[dict], source_label: str, channel_cfg
) -> list[tuple[str, str]]:
    """Ask Claude whether to approve or reject a batch of backlog items in a single API call.

    Items are chunked into groups of _BATCH_SIZE (50) and one call is made per chunk.

    Returns a list of (decision, reason) tuples in the same order as *items*.
    """
    import json
    import time
    import anthropic
    from pipeline.claude_utils import strip_markdown_fences

    content_type = "Reddit story" if source_label == "Reddit" else "tweet"
    client = anthropic.Anthropic(api_key=config.ANTHROPIC_API_KEY)
    results: list[tuple[str, str]] = []

    # Chunk items into batches of _BATCH_SIZE
    for chunk_start in range(0, len(items), _BATCH_SIZE):
        chunk = items[chunk_start: chunk_start + _BATCH_SIZE]
        n = len(chunk)

        # Build numbered content list
        items_text = ""
        for i, item in enumerate(chunk, 1):
            block = _build_content_block(item, source_label)
            items_text += f"\n--- Item {i} ---\n{block}\n"

        prompt = (
            f"You are reviewing {content_type}s for a YouTube Shorts channel called \"{channel_cfg.name}\".\n"
            f"The channel niche is: {channel_cfg.slug.replace('-', ' ')}.\n\n"
            f"For each numbered item below, decide whether it would make an engaging, high-quality YouTube Short.\n"
            f"Approve if it has a strong hook, emotional engagement, and suits the niche.\n"
            f"Reject if it is boring, too short, off-topic, or low quality.\n\n"
            f"ITEMS TO REVIEW:\n{items_text}\n"
            f"Return a JSON array with exactly {n} objects, one per item, in order:\n"
            f'[{{"item": 1, "decision": "approve" or "reject", "reason": "one sentence"}}, ...]\n'
            f"Return ONLY the JSON array, no other text."
        )

        max_tokens = max(256, n * 64)

        for attempt in range(1, _MAX_RETRIES + 1):
            try:
                resp = client.messages.create(
                    model=_HAIKU_MODEL,
                    max_tokens=max_tokens,
                    temperature=0.2,
                    messages=[{"role": "user", "content": prompt}],
                )
                raw_text = ""
                for block in resp.content:
                    if block.type == "text":
                        raw_text = block.text.strip()
                        break
                if not raw_text:
                    raise ValueError("No TextBlock in Claude response")
                raw = strip_markdown_fences(raw_text)
                parsed = json.loads(raw)

                # Build a lookup by item number
                lookup: dict[int, tuple[str, str]] = {}
                for entry in parsed:
                    item_num = entry.get("item")
                    decision = entry.get("decision", "reject").lower()
                    if decision not in ("approve", "reject"):
                        decision = "reject"
                    reason = entry.get("reason", "")
                    if isinstance(item_num, int):
                        lookup[item_num] = (decision, reason)

                # Map back to chunk order; fall back for missing items
                chunk_results = []
                for i in range(1, n + 1):
                    chunk_results.append(lookup.get(i, ("reject", "batch parse error")))

                results.extend(chunk_results)
                logger.info(
                    "_ai_review_batch: chunk %d-%d reviewed (%d items)",
                    chunk_start + 1, chunk_start + n, n,
                )
                break

            except Exception as e:
                logger.warning(
                    "_ai_review_batch attempt %d failed for chunk %d-%d: %s",
                    attempt, chunk_start + 1, chunk_start + n, e,
                )
                if attempt == _MAX_RETRIES:
                    # Fall back: reject everything in this chunk
                    results.extend([("reject", f"batch error: {e}")] * n)
                else:
                    time.sleep(2 ** attempt)

    return results


def _ai_review_item(item: dict, source_label: str, channel_cfg) -> tuple[str, str]:
    """Ask Claude whether to approve or reject a backlog item.

    Returns (decision, reason) where decision is 'approve' or 'reject'.
    """
    import time
    import anthropic
    from pipeline.claude_utils import strip_markdown_fences

    content_block = _build_content_block(item, source_label)
    content_type = "Reddit story" if source_label == "Reddit" else "tweet"

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
    for attempt in range(1, _MAX_RETRIES + 1):
        try:
            resp = client.messages.create(
                model=_HAIKU_MODEL,
                max_tokens=128,
                temperature=0.2,
                messages=[{"role": "user", "content": prompt}],
            )
            resp_text = ""
            for block in resp.content:
                if block.type == "text":
                    resp_text = block.text.strip()
                    break
            if not resp_text:
                raise ValueError("No TextBlock in Claude response")
            result = json.loads(strip_markdown_fences(resp_text))
            decision = result.get("decision", "reject").lower()
            if decision not in ("approve", "reject"):
                decision = "reject"
            return decision, result.get("reason", "")
        except Exception as e:
            logger.warning("AI review attempt %d failed: %s", attempt, e)
            if attempt == _MAX_RETRIES:
                return "reject", f"evaluation error: {e}"
            time.sleep(2 ** attempt)
    return "reject", "all attempts failed"


def cmd_review(channel_cfg, ai: bool = False) -> None:
    """Review pending backlog items — interactively or via Claude (--ai)."""
    from pipeline.db import get_connection
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

        if ai:
            # Batch all items into a single (chunked) Claude call
            item_dicts = [dict(item) for item in items]
            ai_results = _ai_review_batch(item_dicts, source_label, channel_cfg)

            for item, (decision, reason) in zip(items, ai_results):
                item_id = item[id_key]
                if source_label == "Reddit":
                    print(f"--- Reddit | r/{item['subreddit']} ---")
                    print(f"Score: {item['score']:,}  Words: {item['word_count']}")
                    print(f"\n{item['title']}")
                else:
                    print(f"--- Twitter | @{item['username']} ---")
                    print(f"Likes: {item['likes']:,}  Retweets: {item['retweets']:,}")
                    print(f"\n{item['tweet_text'][:200]}{'...' if len(item['tweet_text']) > 200 else ''}")

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
