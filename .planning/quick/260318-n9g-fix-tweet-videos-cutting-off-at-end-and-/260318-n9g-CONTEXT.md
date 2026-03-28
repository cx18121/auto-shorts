# Quick Task 260318-n9g: Fix videos cutting off + add @username says intro - Context

**Gathered:** 2026-03-18
**Status:** Ready for planning

<domain>
## Task Boundary

Two fixes:
1. Storytelling videos cut off at the end (last word/sentence clipped) — primary issue
2. While fixing, also apply same fix to tweet assembler (same bug)
3. Prepend `@username says:` to TTS script for tweet videos

</domain>

<decisions>
## Implementation Decisions

### Cutoff fix (both assemblers)
Add `+ 0.5` buffer to `adjusted_duration` in both assemblers:
- `formats/storytelling/assembler.py` — lines where `adjusted_duration = duration / AUDIO_SPEED` or `duration_seconds / AUDIO_SPEED`
- `formats/tweets/assembler.py` — same pattern

Root cause: `adjusted_duration = duration / AUDIO_SPEED` can be fractionally shorter than the actual sped-up audio output, causing FFmpeg's `-t` to clip the last word.

### Tweet voiceover intro
Prepend `@{username} says: ` to the TTS script in `main.py` at all tweet TTS call sites:
- `_scrape_tweets`: `tweet["text"]` → `f"@{tweet['username']} says: {tweet['text']}"`
- `_run_tweet_pipeline`: `tweet["tweet_text"]` → `f"@{tweet.get('username', '')} says: {tweet['tweet_text']}"`

### Claude's Discretion
- Exact buffer amount: +0.5s
- Intro wording: "says:" (lowercase, colon, space before tweet text)

</decisions>

<specifics>
## Specific Ideas

- Do NOT change to `-shortest` — keep `-t` with buffer
- Apply buffer to all `-t` usages derived from `adjusted_duration` in both files
- Do not change anything else in assembler logic

</specifics>

<canonical_refs>
## Canonical References

No external specs — requirements fully captured in decisions above.
</canonical_refs>
