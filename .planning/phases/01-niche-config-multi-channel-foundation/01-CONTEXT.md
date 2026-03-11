# Phase 1: Niche Config + Multi-Channel Foundation - Context

**Gathered:** 2026-03-11
**Status:** Ready for planning

<domain>
## Phase Boundary

Wire per-channel configuration so scrapers, voice selection, and upload credentials all route through the correct niche. This phase delivers the configuration layer and CLI routing only — no scraping, no upload automation, no video generation changes. Those are Phases 2–4.

</domain>

<decisions>
## Implementation Decisions

### Config storage format
- Niche configs live in a single `channels.yaml` in the project root (alongside `config.py` and `main.py`)
- `channels.yaml` is committed to the repo but gitignored — a `channels.yaml.example` ships with the schema and placeholder values
- Channel slugs are hyphenated: `hypothetical-scenarios`, `relationships`, `finance-hustle`
- `config.py` loads and validates `channels.yaml` at startup, making channels available as a dict

### Credential isolation
- Per-channel upload credentials (YouTube OAuth, Instagram tokens) live in `.env` as per-channel vars
- Naming convention: Claude's discretion (e.g. `HYPOTHETICAL_SCENARIOS_YOUTUBE_CLIENT_ID` or similar consistent pattern)
- Phase 1 defines placeholder credential fields in `channels.yaml` (e.g. `youtube_client_id`, `instagram_access_token`) so the schema is clear, even if blank — Phase 4 fills them in

### Voice & content source coupling
- Each channel's `voice_id` lives inside its block in `channels.yaml` — YAML is the single source of truth for all niche-specific config
- Subreddit lists and Twitter account lists are hardcoded defaults in `channels.yaml`, editable by hand — no runtime override needed
- Each niche has one format: `hypothetical-scenarios` → storytelling, `relationships` → storytelling, `finance-hustle` → tweets (or Claude's discretion if not specified — check roadmap intent)
- Format field (`format: storytelling|tweets`) is a field in each channel's YAML block

### CLI --channel flag
- `--channel` is a global flag before the subcommand: `python main.py --channel relationships generate --format tweets`
- Omitting `--channel` is an error — channel is always required, no default
- `--channel all` runs all channels sequentially (hypothetical-scenarios → relationships → finance-hustle)

### Claude's Discretion
- Exact `.env` var naming convention for per-channel credentials (just be consistent)
- Whether `config.py` raises at import time or at command time when `channels.yaml` is missing/malformed
- Internal structure of the channel config dataclass or dict
- Whether to use `pyyaml` or `ruamel.yaml` for YAML loading

</decisions>

<specifics>
## Specific Ideas

- The three channels should ship with their subreddit and Twitter account lists pre-populated in `channels.yaml.example` — not empty placeholders. User should be able to `cp channels.yaml.example channels.yaml` and have something real immediately.
- `config.py` already creates output dirs at import time — same pattern can validate/create per-channel directories (e.g. backlog partition) at startup.

</specifics>

<code_context>
## Existing Code Insights

### Reusable Assets
- `config.py`: Already loads env vars and creates directories — extend it to load `channels.yaml` and expose a `get_channel(slug)` function
- `main.py` `argparse` setup: Existing subcommand structure just needs a global `--channel` argument added to the root parser

### Established Patterns
- All external config via `.env` + `python-dotenv` — per-channel credentials follow the same pattern, just prefixed
- Functions over classes throughout — channel config can be a plain dict or simple dataclass, no need for a class hierarchy
- Type hints on all functions — `get_channel()` should return a typed dataclass or TypedDict

### Integration Points
- `main.py` `main()`: Root `argparse` parser needs `--channel` added; each command handler receives the loaded channel config
- `config.py`: New `CHANNELS` dict (loaded from `channels.yaml`) replaces single global voice/credential vars for niche operations
- `pipeline/tts.py`: Currently uses global `ELEVENLABS_VOICE_ID` — will need to accept voice_id as parameter once channel config is wired in (Phase 2+ concern, but channel config must expose it)

</code_context>

<deferred>
## Deferred Ideas

None — discussion stayed within phase scope.

</deferred>

---

*Phase: 01-niche-config-multi-channel-foundation*
*Context gathered: 2026-03-11*
