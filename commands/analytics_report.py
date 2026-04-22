"""
commands/analytics_report.py — Human-readable performance insights and recommendations.

Usage:
    python main.py --channel hypothetical-scenarios analytics-report --days 30
"""

import logging

logger = logging.getLogger(__name__)


def cmd_analytics_report(channel_cfg, days: int = 30) -> None:
    """Print a formatted analytics report with top backgrounds, title patterns,
    hook analysis (50% weight), body analysis, and generation recommendations."""
    from pipeline.db import get_connection
    from pipeline.analytics import (
        get_top_videos,
        extract_hook_words,
        analyze_title_patterns,
        analyze_background_performance,
        analyze_hook_effectiveness,
        analyze_transcript_weighted,
        get_generation_recommendations,
    )

    slug = channel_cfg.slug
    from pipeline.db import init_db
    init_db()  # Ensure video_insights table exists
    conn = get_connection()

    try:
        min_views = 100

        print(f"\n{'='*60}")
        print(f"  ANALYTICS REPORT — {slug} (last {days} days)")
        print(f"{'='*60}")

        # ---- Top videos overview ----
        top = get_top_videos(conn, slug, metric="view_count", min_views=min_views, limit=20, days=days)
        if not top:
            print("\nNo video insights yet. Run 'fetch-analytics' first.")
            return

        print(f"\n  Found {len(top)} videos with ≥{min_views} views\n")

        # ---- Background performance ----
        bg_data = analyze_background_performance(conn, slug, days)
        if bg_data:
            print(f"  {'─'*56}")
            print("  TOP BACKGROUNDS (by avg views)")
            print(f"  {'─'*56}")
            for b in bg_data[:5]:
                print(f"    {b['bg']:<45} avg {b['avg_views']:>7,} views ({b['count']} videos)")
        else:
            print("\n  TOP BACKGROUNDS: no data yet")

        # ---- Title patterns ----
        titles = [v.get("title", "") for v in top if v.get("title")]
        title_analysis = analyze_title_patterns(titles)
        print(f"\n  {'─'*56}")
        print("  TITLE PATTERNS (from top videos)")
        print(f"  {'─'*56}")
        prefixes = title_analysis.get("prefixes", {})
        what_if_ct = prefixes.get("what if", 0)
        imagine_ct = prefixes.get("imagine", 0)
        dollar_ct = title_analysis.get("has_dollar", 0)
        question_ct = title_analysis.get("has_question", 0)
        avg_wc = title_analysis.get("avg_word_count", 0)
        examples = title_analysis.get("title_examples", [])

        print(f"    {'✓' if what_if_ct >= 2 else ' '} {what_if_ct} of {len(titles)} start with 'What if...'")
        print(f"    {imagine_ct} of {len(titles)} start with 'Imagine...'")
        print(f"    {dollar_ct} of {len(titles)} contain a dollar amount or number")
        print(f"    {question_ct} of {len(titles)} are questions (end with '?')")
        print(f"    Avg word count: {avg_wc}")
        if examples:
            print(f"    Examples:")
            for ex in examples[:3]:
                print(f"      • {ex}")

        # ---- Transcript analysis ----
        transcript_paths = [v.get("transcript_path") for v in top if v.get("transcript_path")]
        views = [v.get("view_count", 0) for v in top if v.get("view_count", 0) >= min_views]

        print(f"\n  {'─'*56}")
        print("  TRANSCRIPT ANALYSIS (Hook = 50% weight, Body = 50% weight)")
        print(f"  {'─'*56}")

        # Hook analysis (first 5 seconds)
        hooks = []
        for path in transcript_paths:
            if path:
                h = extract_hook_words(path, max_seconds=5.0)
                if h:
                    hooks.append(h)

        hook_analysis = analyze_hook_effectiveness(hooks, views) if hooks else {}
        hook_struct = hook_analysis.get("hook_structure_top", "unknown")
        avg_words_top = hook_analysis.get("avg_words_in_top_25pct", 0)
        stakes_ratio = hook_analysis.get("has_stakes_ratio_top", 0)
        stakes_kw = hook_analysis.get("stakes_keywords_top", [])

        print(f"\n  FIRST 5 SECONDS — HOOK (50% weight):")
        print(f"    Top performers open with: {hook_struct} in first {avg_words_top} words (avg)")
        print(f"    Stakes framing ratio in top 25%: {int(stakes_ratio * 100)}%")
        if stakes_kw:
            print(f"    Top stakes keywords: {', '.join(stakes_kw[:8])}")
        if hooks:
            print(f"    Examples from top performers:")
            for h in hooks[:3]:
                print(f"      • \"{h}\"")

        # Body analysis
        weighted = analyze_transcript_weighted(
            [p for p in transcript_paths if p],
            views[:len(transcript_paths)],
        )
        body = weighted.get("body_patterns", {})
        rec = weighted.get("unified_recommendation", "")

        print(f"\n  REST OF SCRIPT — BODY (50% combined weight):")
        avg_wpm = body.get("avg_wpm", 0)
        sentiment = body.get("dominant_sentiment", "unknown")
        res_ratio = body.get("resolution_ratio", 0)
        body_kw = body.get("top_keywords", [])
        print(f"    Avg pace: {avg_wpm} WPM")
        print(f"    Dominant tone: {sentiment}")
        print(f"    Resolution ratio in top performers: {int(res_ratio * 100)}%")
        if body_kw:
            print(f"    Top keywords: {', '.join(body_kw[:8])}")

        # ---- Recommendations ----
        print(f"\n  {'─'*56}")
        print("  RECOMMENDATIONS FOR NEXT VIDEO")
        print(f"  {'─'*56}")
        gen_rec = get_generation_recommendations(conn, slug, days)
        title_hints = gen_rec.get("title_hints", [])
        hook_style = gen_rec.get("hook_style", "")
        hook_examples = gen_rec.get("hook_examples", [])
        body_style = gen_rec.get("body_style", "")
        preferred_bgs = gen_rec.get("preferred_backgrounds", [])
        avoid = gen_rec.get("avoid", [])

        print(f"\n  Title:")
        for h in title_hints[:4]:
            print(f"    • {h}")

        print(f"\n  Hook style (HIGHEST WEIGHT):")
        print(f"    • {hook_style}")
        if hook_examples:
            print(f"    Best examples from past videos:")
            for ex in hook_examples[:3]:
                print(f"      \"{ex}\"")

        if body_style:
            print(f"\n  Body transcript style:")
            print(f"    • {body_style}")

        if preferred_bgs:
            print(f"\n  Preferred backgrounds:")
            for bg in preferred_bgs:
                print(f"    • {bg}")

        if avoid:
            print(f"\n  Avoid:")
            for a in avoid:
                print(f"    ✗ {a}")

        # New OAuth-enriched metrics
        avg_dur = gen_rec.get("avg_view_duration_seconds")
        avg_ret = gen_rec.get("avg_view_percentage")
        avg_likes = gen_rec.get("avg_engagement_likes")
        top_vc = gen_rec.get("top_view_count")
        total_analyzed = gen_rec.get("total_videos_analyzed")
        if avg_dur is not None or avg_ret is not None:
            print(f"\n  PERFORMANCE BENCHMARKS ({total_analyzed} videos analyzed):")
            if avg_dur is not None:
                print(f"    • Avg watch duration: {avg_dur}s per view")
            if avg_ret is not None:
                print(f"    • Avg retention rate: {avg_ret}% of video")
            if avg_likes is not None:
                print(f"    • Avg likes per video: {avg_likes}")
            if top_vc:
                print(f"    • Top video views: {top_vc:,}")

        print(f"\n{'='*60}\n")

    finally:
        conn.close()