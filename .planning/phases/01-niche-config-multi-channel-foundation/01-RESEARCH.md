# Phase 1: Niche Config + Multi-Channel Foundation - Research

**Researched:** 2026-03-11
**Domain:** Python config management (YAML), argparse global flags, dataclasses/TypedDict, per-channel directory isolation
**Confidence:** HIGH

---

<user_constraints>
## User Constraints (from CONTEXT.md)

### Locked Decisions
- Niche configs live in a single `channels.yaml` in the project root (alongside `config.py` and `main.py`)
- `channels.yaml` is committed to the repo but gitignored — a `channels.yaml.example` ships with the schema and placeholder values
- Channel slugs are hyphenated: `hypothetical-scenarios`, `relationships`, `finance-hustle`
- `config.py` loads and validates `channels.yaml` at startup, making channels available as a dict
- Per-channel upload credentials (YouTube OAuth, Instagram tokens) live in `.env` as per-channel vars
- Naming convention for credentials: Claude's discretion (e.g. `HYPOTHETICAL_SCENARIOS_YOUTUBE_CLIENT_ID` or similar consistent pattern)
- Phase 1 defines placeholder credential fields in `channels.yaml` (e.g. `youtube_client_id`, `instagram_access_token`) so the schema is clear, even if blank — Phase 4 fills them in
- Each channel's `voice_id` lives inside its block in `channels.yaml` — YAML is the single source of truth for all niche-specific config
- Subreddit lists and Twitter account lists are hardcoded defaults in `channels.yaml`, editable by hand — no runtime override needed
- Format field (`format: storytelling|tweets`) is a field in each channel's YAML block
- `--channel` is a global flag before the subcommand: `python main.py --channel relationships generate --format tweets`
- Omitting `--channel` is an error — channel is always required, no default
- `--channel all` runs all channels sequentially (hypothetical-scenarios → relationships → finance-hustle)

### Claude's Discretion
- Exact `.env` var naming convention for per-channel credentials (just be consistent)
- Whether `config.py` raises at import time or at command time when `channels.yaml` is missing/malformed
- Internal structure of the channel config dataclass or dict
- Whether to use `pyyaml` or `ruamel.yaml` for YAML loading

### Deferred Ideas (OUT OF SCOPE)
None — discussion stayed within phase scope.
</user_constraints>

---

<phase_requirements>
## Phase Requirements

| ID | Description | Research Support |
|----|-------------|-----------------|
| NICHE-01 | Each niche is defined in config with: name, subreddits, twitter accounts, voice ID, posting accounts | YAML schema design, ChannelConfig dataclass fields |
| NICHE-02 | Three niches configured out of the box: hypothetical-scenarios, relationships, finance-hustle | Pre-populated `channels.yaml.example` with real subreddits and Twitter accounts |
| NICHE-03 | Niche config drives which content is scraped, generated, and which channel it posts to | `get_channel(slug)` function wires config to downstream operations |
| MULTI-01 | Each niche channel operates with its own isolated backlog, config, and upload credentials | Per-channel output/backlog directories created at startup; credentials namespaced in .env |
| MULTI-02 | A single scheduler process manages all channels | Out of scope for Phase 1 — Phase 4 concern. Phase 1 only seeds the config `--channel all` iterates over |
| MULTI-03 | CLI can target a specific channel or run all channels | `--channel` global flag on root argparse parser; `all` iterates CHANNELS dict |
</phase_requirements>

---

## Summary

This phase is purely a configuration and routing layer — no scraping, generation, or upload logic. The work
is: define a YAML schema for three niche channels, load and validate it in `config.py`, and add a `--channel`
global flag to `main.py`'s argparse root parser that threads the loaded channel config through to every
subcommand handler.

The entire stack is already present in the repo. `pyyaml` 6.0.1 is installed (confirmed). Python's stdlib
`dataclasses` and `TypedDict` handle typed config objects without new dependencies. `argparse`'s
`add_argument` on the root parser (before `add_subparsers`) naturally produces a global flag accessible
regardless of which subcommand is invoked — this is the established argparse pattern for global options.

**Primary recommendation:** Extend `config.py` with a `load_channels()` function that reads `channels.yaml`,
validates required fields, returns a `dict[str, ChannelConfig]`, and creates per-channel directories. Add
`--channel` to the root argparse parser and pass `get_channel(args.channel)` into each command handler.

---

## Standard Stack

### Core
| Library | Version | Purpose | Why Standard |
|---------|---------|---------|--------------|
| pyyaml | 6.0.1 (installed) | Parse `channels.yaml` | Already in environment; PyYAML is the de-facto standard for YAML in Python |
| python-dotenv | installed | Load per-channel `.env` vars | Already the project pattern for all credentials |
| dataclasses (stdlib) | Python 3.10+ | Typed, lightweight config objects | Project already uses type hints everywhere; no new deps |
| argparse (stdlib) | Python 3.x | Global `--channel` flag | Already used in `main.py` |

### Supporting
| Library | Version | Purpose | When to Use |
|---------|---------|---------|-------------|
| pathlib (stdlib) | Python 3.x | Per-channel directory creation | Already used in `config.py` for `OUTPUT_DIR` etc. |

### Alternatives Considered
| Instead of | Could Use | Tradeoff |
|------------|-----------|----------|
| pyyaml | ruamel.yaml | ruamel preserves comments on round-trip write — not needed here since we only read, never write back |
| dataclasses | TypedDict | TypedDict works with `**kwargs` spreading but gives no runtime validation; dataclass with `__post_init__` is cleaner for required-field checking |
| dataclasses | Pydantic | Pydantic gives strict validation with good errors, but it's a heavyweight new dependency for what is 10 fields per channel |

**Installation:**
```bash
# Nothing new required — pyyaml and python-dotenv are already installed
```

---

## Architecture Patterns

### Recommended Project Structure
No new directories needed at the source level. Per-channel data directories are created at runtime:
```
auto-shorts/
├── channels.yaml           # gitignored — user's real config
├── channels.yaml.example   # committed — template with real defaults
├── config.py               # extended to load channels.yaml
├── main.py                 # extended with --channel global flag
└── data/
    ├── pipeline.db
    ├── channels/           # created at startup by config.py
    │   ├── hypothetical-scenarios/   # isolated backlog partition per channel
    │   ├── relationships/
    │   └── finance-hustle/
```

### Pattern 1: Global argparse flag before subparsers
**What:** Add `--channel` to the root parser before `add_subparsers()`. `parse_args()` populates `args.channel` regardless of which subcommand is invoked.
**When to use:** Any flag that must be available to all subcommands without repeating it on each subparser.
**Example:**
```python
# Source: Python argparse docs — parent parsers / global options pattern
def main() -> None:
    parser = argparse.ArgumentParser(...)
    parser.add_argument(
        "--channel",
        required=True,
        metavar="SLUG",
        help="Channel slug (e.g. hypothetical-scenarios) or 'all'",
    )
    sub = parser.add_subparsers(dest="command", required=True)
    # ... existing subcommands unchanged ...
    args = parser.parse_args()
    channel_cfg = config.get_channel(args.channel)   # None = "all"
    if args.command == "analyze":
        cmd_analyze(args.channels, args.visual, args.max_videos, channel_cfg)
    # ...
```

### Pattern 2: YAML schema for channel config
**What:** Top-level keys are channel slugs; each block holds all niche-specific values.
**When to use:** Multiple named entities with the same field structure.
**Example:**
```yaml
# channels.yaml.example
hypothetical-scenarios:
  name: "Hypothetical Scenarios"
  format: storytelling
  voice_id: "REPLACE_WITH_ELEVENLABS_VOICE_ID"
  subreddits:
    - hypothetical
    - AskReddit
    - WouldYouRather
  twitter_accounts:
    - WhatIfAlt
    - HypotheticalQ
  youtube_client_id: ""
  youtube_client_secret: ""
  instagram_access_token: ""

relationships:
  name: "Relationships"
  format: storytelling
  voice_id: "REPLACE_WITH_ELEVENLABS_VOICE_ID"
  subreddits:
    - relationship_advice
    - AITAH
    - AmItheAsshole
    - tifu
  twitter_accounts:
    - RelationshipTips
    - DearAbby
  youtube_client_id: ""
  youtube_client_secret: ""
  instagram_access_token: ""

finance-hustle:
  name: "Finance & Hustle"
  format: tweets
  voice_id: "REPLACE_WITH_ELEVENLABS_VOICE_ID"
  subreddits:
    - personalfinance
    - financialindependence
    - Entrepreneur
    - passive_income
  twitter_accounts:
    - NavalRavikant
    - morganhousel
    - SahilBloom
    - dickiebush
  youtube_client_id: ""
  youtube_client_secret: ""
  instagram_access_token: ""
```

### Pattern 3: ChannelConfig dataclass with validation
**What:** A `dataclasses.dataclass` with `__post_init__` that checks required fields and normalizes slug.
**When to use:** Structured config objects that are passed through the call stack.
**Example:**
```python
# Source: Python docs — dataclasses
from dataclasses import dataclass, field

VALID_FORMATS = {"storytelling", "tweets"}

@dataclass
class ChannelConfig:
    slug: str
    name: str
    format: str
    voice_id: str
    subreddits: list[str]
    twitter_accounts: list[str]
    youtube_client_id: str = ""
    youtube_client_secret: str = ""
    instagram_access_token: str = ""

    def __post_init__(self) -> None:
        if self.format not in VALID_FORMATS:
            raise ValueError(f"Channel '{self.slug}' format must be one of {VALID_FORMATS}, got '{self.format}'")
        if not self.voice_id:
            raise ValueError(f"Channel '{self.slug}' requires a voice_id")
        if not self.subreddits:
            raise ValueError(f"Channel '{self.slug}' requires at least one subreddit")
```

### Pattern 4: config.py load_channels() function
**What:** Reads `channels.yaml`, constructs `ChannelConfig` objects, creates per-channel directories.
**When to use:** At module import time in `config.py` — matching the existing pattern for directory creation.
**Example:**
```python
import yaml

CHANNELS_PATH: Path = BASE_DIR / "channels.yaml"
CHANNELS_DIR: Path = DATA_DIR / "channels"

def load_channels() -> dict[str, ChannelConfig]:
    if not CHANNELS_PATH.exists():
        raise FileNotFoundError(
            f"channels.yaml not found. Copy channels.yaml.example to channels.yaml and fill in voice IDs."
        )
    raw = yaml.safe_load(CHANNELS_PATH.read_text())
    if not isinstance(raw, dict):
        raise ValueError("channels.yaml must be a YAML mapping at the top level")
    channels: dict[str, ChannelConfig] = {}
    for slug, data in raw.items():
        try:
            cfg = ChannelConfig(slug=slug, **data)
        except (TypeError, ValueError) as e:
            raise ValueError(f"Invalid config for channel '{slug}': {e}") from e
        # Create isolated per-channel data directory
        (CHANNELS_DIR / slug).mkdir(parents=True, exist_ok=True)
        channels[slug] = cfg
    return channels

CHANNELS: dict[str, ChannelConfig] = load_channels()

def get_channel(slug: str) -> ChannelConfig:
    if slug not in CHANNELS:
        raise SystemExit(
            f"Unknown channel: '{slug}'. Available: {', '.join(CHANNELS)}"
        )
    return CHANNELS[slug]
```

### Pattern 5: "all" channels iteration in main.py
**What:** When `--channel all` is passed, iterate `config.CHANNELS` in definition order and call the command handler for each.
**When to use:** Batch operations across all channels.
**Example:**
```python
if args.channel == "all":
    for slug, channel_cfg in config.CHANNELS.items():
        logger.info("=" * 60)
        logger.info("CHANNEL: %s", slug)
        _dispatch_command(args, channel_cfg)
else:
    channel_cfg = config.get_channel(args.channel)
    _dispatch_command(args, channel_cfg)
```

### Anti-Patterns to Avoid
- **Lazy loading channels:** Do NOT defer `load_channels()` to first use. The existing `config.py` creates dirs at import time — match that pattern so startup errors are immediate.
- **Mutating global CHANNELS dict at runtime:** `CHANNELS` is read-only after import. Downstream code receives a `ChannelConfig` instance, never writes back.
- **Using yaml.load() without Loader:** Always use `yaml.safe_load()`. `yaml.load()` without an explicit Loader triggers a warning in PyYAML 6.x and is a security risk.
- **Storing secrets in channels.yaml:** Upload credentials (OAuth tokens) belong in `.env` only. `channels.yaml` stores placeholder field names as documentation; actual values are loaded from env at channel init time or Phase 4.

---

## Don't Hand-Roll

| Problem | Don't Build | Use Instead | Why |
|---------|-------------|-------------|-----|
| YAML parsing | Custom file parser | `yaml.safe_load()` (pyyaml) | Handles multiline strings, lists, nested dicts, encoding |
| Config validation | Manual key existence checks | `dataclass.__post_init__` | Catches missing/wrong-type fields with clear error messages |
| Per-channel directory creation | Manual `os.makedirs` guards | `pathlib.Path.mkdir(parents=True, exist_ok=True)` | Already the project pattern in config.py |
| CLI subcommand global options | Duplicating `--channel` on every subparser | Root parser `add_argument` before `add_subparsers` | argparse propagates the flag naturally |

**Key insight:** This phase is configuration plumbing, not business logic. Every problem here is solved by stdlib + already-installed libraries.

---

## Common Pitfalls

### Pitfall 1: channels.yaml missing at import causes cryptic error
**What goes wrong:** If `config.py` calls `load_channels()` at module level (import time) and `channels.yaml` is absent, every `import config` in tests or other modules raises `FileNotFoundError` with a confusing traceback.
**Why it happens:** Following the existing pattern of running setup code at module level.
**How to avoid:** Two options — (a) raise a `SystemExit` with a clear human-readable message from `load_channels()` so it looks like a startup error, not a Python crash; or (b) make load deferred (at command time). Recommendation: option (a) — raise at import time with a clear message. Matches how the project handles missing `.env` keys (they resolve to empty strings, which fail fast on first use). A missing `channels.yaml` should fail immediately with "Copy channels.yaml.example to channels.yaml".
**Warning signs:** Tests importing `config` suddenly fail if channels.yaml is absent.

### Pitfall 2: argparse global flag placement
**What goes wrong:** Adding `--channel` to a subparser instead of the root parser means it must be placed after the subcommand: `python main.py generate --channel foo` instead of `python main.py --channel foo generate`. This breaks the agreed CLI contract.
**Why it happens:** Easy to accidentally add to `p_gen` or `p_analyze` instead of `parser`.
**How to avoid:** Add `parser.add_argument("--channel", ...)` to the root `parser` object before `sub = parser.add_subparsers(...)`.
**Warning signs:** `args.channel` raises `AttributeError` for some subcommands.

### Pitfall 3: yaml.safe_load returns None for empty file
**What goes wrong:** `yaml.safe_load("")` returns `None`. If `channels.yaml` is empty or contains only comments, `load_channels()` will try to iterate `None` and raise `TypeError`.
**Why it happens:** PyYAML returns None for empty/comment-only documents.
**How to avoid:** Add `if not isinstance(raw, dict): raise ValueError(...)` after loading.

### Pitfall 4: Channel slug in YAML key vs runtime slug mismatch
**What goes wrong:** YAML key is `hypothetical_scenarios` (underscore) but code expects `hypothetical-scenarios` (hyphen). User edits the YAML and the CLI rejects a valid slug.
**Why it happens:** YAML keys have no format constraint by default.
**How to avoid:** In `__post_init__` or `load_channels()`, assert that slugs match `re.fullmatch(r'[a-z0-9-]+', slug)` and raise a clear error otherwise.

### Pitfall 5: Per-channel .env credential naming collision
**What goes wrong:** Using `YOUTUBE_CLIENT_ID` (no channel prefix) makes it impossible to have multiple channels with different credentials.
**Why it happens:** Reusing existing env var names.
**How to avoid:** Prefix every per-channel credential with the screaming-snake slug: `HYPOTHETICAL_SCENARIOS_YOUTUBE_CLIENT_ID`. In `ChannelConfig.__post_init__` or a separate `load_channel_credentials(slug)` function, derive the env var name from the slug: `slug.upper().replace("-", "_") + "_YOUTUBE_CLIENT_ID"`.

---

## Code Examples

Verified patterns from Python stdlib and pyyaml 6.x official docs:

### PyYAML safe_load (HIGH confidence — pyyaml 6.0.1 installed)
```python
import yaml

with open("channels.yaml") as f:
    data = yaml.safe_load(f)
# data is a dict[str, Any] matching the YAML structure
```

### argparse global flag before subcommands (HIGH confidence — stdlib)
```python
parser = argparse.ArgumentParser()
parser.add_argument("--channel", required=True)          # global
sub = parser.add_subparsers(dest="command", required=True)
p_gen = sub.add_parser("generate")
p_gen.add_argument("--format", ...)                       # subcommand-specific
args = parser.parse_args()
print(args.channel)    # accessible regardless of subcommand
print(args.command)
print(args.format)
```

### dataclass with post_init validation (HIGH confidence — stdlib)
```python
from dataclasses import dataclass

@dataclass
class ChannelConfig:
    slug: str
    name: str
    format: str
    voice_id: str
    subreddits: list[str]
    twitter_accounts: list[str]
    youtube_client_id: str = ""
    youtube_client_secret: str = ""
    instagram_access_token: str = ""

    def __post_init__(self) -> None:
        if self.format not in {"storytelling", "tweets"}:
            raise ValueError(f"Unknown format: {self.format}")
```

### Per-channel env var derivation
```python
import os

def _env_prefix(slug: str) -> str:
    """'hypothetical-scenarios' -> 'HYPOTHETICAL_SCENARIOS'"""
    return slug.upper().replace("-", "_")

def load_channel_credentials(slug: str) -> dict[str, str]:
    prefix = _env_prefix(slug)
    return {
        "youtube_client_id": os.getenv(f"{prefix}_YOUTUBE_CLIENT_ID", ""),
        "youtube_client_secret": os.getenv(f"{prefix}_YOUTUBE_CLIENT_SECRET", ""),
        "instagram_access_token": os.getenv(f"{prefix}_INSTAGRAM_ACCESS_TOKEN", ""),
    }
```

---

## State of the Art

| Old Approach | Current Approach | When Changed | Impact |
|--------------|------------------|--------------|--------|
| `yaml.load(f)` (unsafe) | `yaml.safe_load(f)` | PyYAML 5.1 (2019) | `yaml.load` now warns without Loader kwarg; always use safe_load for config files |
| Global single voice_id in .env | Per-channel voice_id in channels.yaml | This phase | Enables each niche to use a different ElevenLabs voice |

**Deprecated/outdated:**
- `yaml.load(f)` without Loader: triggers FullLoader warning in PyYAML 6.x, is a deserialization risk — use `yaml.safe_load(f)` always.

---

## Open Questions

1. **finance-hustle format assignment**
   - What we know: CONTEXT.md says `hypothetical-scenarios` and `relationships` are storytelling. `finance-hustle` is tweets "or Claude's discretion if not specified — check roadmap intent."
   - What's unclear: The roadmap says Phase 2 scrapes Reddit for storytelling niches and Twitter for tweets niches. The name "finance-hustle" + tweet format makes semantic sense (viral finance takes). No roadmap text contradicts this.
   - Recommendation: Assign `format: tweets` to `finance-hustle`. This aligns with the existing tweet scraper's viral-finance account list in `formats/tweets/scraper.py` and the roadmap's intent that finance content comes from Twitter.

2. **Error behavior when channels.yaml is missing**
   - What we know: CONTEXT.md leaves this to Claude's discretion ("raises at import time or at command time").
   - What's unclear: Import-time failure means `import config` in any test fails if channels.yaml is absent.
   - Recommendation: Raise `SystemExit` at import time with a clear message. Existing tests (`test_tts.py`, `test_assembler.py`) import from `pipeline.*` and `formats.*`, not from `config` directly — so this does not break current tests. New tests for config can use a fixture that creates a temp channels.yaml.

3. **Subreddit and Twitter account selections for channels.yaml.example**
   - What we know: CONTEXT.md requires pre-populated lists — "not empty placeholders."
   - What's unclear: Which specific accounts and subreddits are highest signal for each niche.
   - Recommendation: Use well-known, high-traffic options (documented in Code Examples above). These are editable by the user.

---

## Validation Architecture

### Test Framework
| Property | Value |
|----------|-------|
| Framework | None installed — existing tests are standalone `python tests/test_X.py` scripts |
| Config file | None (no pytest.ini, pyproject.toml, or setup.cfg) |
| Quick run command | `python3 tests/test_config_channels.py` |
| Full suite command | `python3 tests/test_tts.py && python3 tests/test_assembler.py && python3 tests/test_config_channels.py` |

### Phase Requirements → Test Map
| Req ID | Behavior | Test Type | Automated Command | File Exists? |
|--------|----------|-----------|-------------------|-------------|
| NICHE-01 | ChannelConfig has all required fields (name, subreddits, twitter_accounts, voice_id, posting accounts) | unit | `python3 tests/test_config_channels.py` | Wave 0 |
| NICHE-02 | All 3 niches load from channels.yaml.example without error | unit | `python3 tests/test_config_channels.py` | Wave 0 |
| NICHE-03 | `get_channel(slug)` returns correct config for each slug | unit | `python3 tests/test_config_channels.py` | Wave 0 |
| MULTI-01 | Per-channel directories are created under `data/channels/` | unit | `python3 tests/test_config_channels.py` | Wave 0 |
| MULTI-03 | `--channel hypothetical-scenarios generate --format storytelling` parses without error | smoke | `python3 tests/test_cli_channel_flag.py` | Wave 0 |
| MULTI-03 | `--channel all` resolves to all 3 channel configs | unit | `python3 tests/test_config_channels.py` | Wave 0 |

### Sampling Rate
- **Per task commit:** `python3 tests/test_config_channels.py`
- **Per wave merge:** `python3 tests/test_tts.py && python3 tests/test_assembler.py && python3 tests/test_config_channels.py && python3 tests/test_cli_channel_flag.py`
- **Phase gate:** Full suite green before `/gsd:verify-work`

### Wave 0 Gaps
- [ ] `tests/test_config_channels.py` — covers NICHE-01, NICHE-02, NICHE-03, MULTI-01, MULTI-03 (config loading)
- [ ] `tests/test_cli_channel_flag.py` — covers MULTI-03 (argparse routing smoke test)
- [ ] `channels.yaml.example` — required before any test can load channels

*(Note: no pytest installation needed — follow existing project pattern of standalone `python3 tests/test_X.py` scripts)*

---

## Sources

### Primary (HIGH confidence)
- pyyaml 6.0.1 — confirmed installed via `python3 -c "import yaml; print(yaml.__version__)"`
- Python stdlib argparse docs — global flags before `add_subparsers` pattern
- Python stdlib dataclasses docs — `__post_init__` validation pattern
- Existing `config.py` — directory-creation-at-import pattern confirmed by reading source
- Existing `main.py` — argparse structure confirmed by reading source

### Secondary (MEDIUM confidence)
- PyYAML official docs (pyyaml.org) — `safe_load` requirement, None return for empty document

### Tertiary (LOW confidence)
- None

---

## Metadata

**Confidence breakdown:**
- Standard stack: HIGH — pyyaml confirmed installed, stdlib only for the rest
- Architecture: HIGH — patterns derived directly from existing codebase code (config.py, main.py)
- Pitfalls: HIGH — all pitfalls are testable Python behavior, not speculative

**Research date:** 2026-03-11
**Valid until:** Stable — these are stdlib and PyYAML 6.x patterns, valid for 12+ months
