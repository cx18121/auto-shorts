---
phase: quick-6
plan: 1
type: execute
wave: 1
depends_on: []
files_modified:
  - main.py
  - pipeline/upload.py
autonomous: true
requirements: [QUICK-6]
must_haves:
  truths:
    - "run-cycle with --publish-at uploads YouTube video as private with publishAt set"
    - "run-cycle without --publish-at uploads YouTube video as public (existing behavior)"
    - "run-cycle with --publish-at skips Instagram upload with a log warning"
  artifacts:
    - path: "main.py"
      provides: "--publish-at CLI argument and plumbing to upload_to_youtube"
    - path: "pipeline/upload.py"
      provides: "upload_to_youtube accepts optional publish_at and sets privacyStatus/publishAt"
  key_links:
    - from: "main.py (run-cycle subparser)"
      to: "main.py (cmd_run_cycle)"
      via: "args.publish_at passed as parameter"
      pattern: "publish_at"
    - from: "main.py (cmd_run_cycle)"
      to: "pipeline/upload.py (upload_to_youtube)"
      via: "publish_at kwarg"
      pattern: "publish_at"
---

<objective>
Add a --publish-at flag to the run-cycle command so YouTube videos are uploaded as private and scheduled to go public at the specified ISO 8601 datetime. Instagram upload is skipped when scheduling.

Purpose: Enable cron-based scheduling where videos are uploaded ahead of time and go public at the desired hour.
Output: Updated main.py and pipeline/upload.py
</objective>

<execution_context>
@/home/cx3429/.claude/get-shit-done/workflows/execute-plan.md
@/home/cx3429/.claude/get-shit-done/templates/summary.md
</execution_context>

<context>
@main.py
@pipeline/upload.py
</context>

<tasks>

<task type="auto">
  <name>Task 1: Add publish_at parameter to upload_to_youtube</name>
  <files>pipeline/upload.py</files>
  <action>
Update the `upload_to_youtube` function signature to accept an optional `publish_at: str | None = None` parameter (ISO 8601 datetime string, e.g. "2026-03-13T09:00:00Z").

In the function body, change the `body["status"]` dict construction:
- When `publish_at` is None (default): keep existing behavior (`"privacyStatus": "public"`).
- When `publish_at` is provided: set `"privacyStatus": "private"` and `"publishAt": publish_at`.

Add a log line when scheduling: `logger.info("upload_to_youtube: scheduling publish at %s", publish_at)`.

Update the docstring to document the new parameter.
  </action>
  <verify>python -c "from pipeline.upload import upload_to_youtube; import inspect; sig = inspect.signature(upload_to_youtube); assert 'publish_at' in sig.parameters; print('OK')"</verify>
  <done>upload_to_youtube accepts publish_at, sets privacyStatus to private and publishAt when provided, keeps public when not</done>
</task>

<task type="auto">
  <name>Task 2: Add --publish-at CLI arg and wire through cmd_run_cycle</name>
  <files>main.py</files>
  <action>
1. In the run-cycle subparser (around line 124-130), add an argument:
   ```python
   p_run = sub.add_parser("run-cycle", help="...")
   p_run.add_argument(
       "--publish-at",
       default=None,
       help="ISO 8601 datetime to schedule YouTube publish (e.g. 2026-03-13T09:00:00Z). "
            "Video uploads as private and goes public at this time. Instagram upload is skipped.",
   )
   ```
   Note: the existing code uses `sub.add_parser(...)` without assigning to a variable. Assign it to `p_run` so we can call `p_run.add_argument(...)`.

2. In the CLI dispatch section (around line 1283), pass `publish_at` to `cmd_run_cycle`:
   Change `cmd_run_cycle(channel_cfg)` to `cmd_run_cycle(channel_cfg, publish_at=getattr(args, "publish_at", None))`.

3. Update `cmd_run_cycle` signature (line 984) to accept `publish_at: str | None = None`.

4. In cmd_run_cycle, pass `publish_at` to the `upload_to_youtube` call (around line 1137):
   Add `publish_at=publish_at` as a keyword argument.

5. For the Instagram upload section (around line 1154-1187): When `publish_at` is set, skip the entire Instagram block with a log warning:
   ```python
   if publish_at:
       logger.info("run-cycle: --publish-at set — skipping Instagram upload (not supported)")
       ig_status = "skipped"
   elif not channel_cfg.instagram_user_id or not ig_token_path.exists():
       ...
   ```

6. Update the cmd_run_cycle docstring to mention the publish_at parameter.
  </action>
  <verify>python main.py --channel hypothetical-scenarios run-cycle --help 2>&1 | grep -q "publish-at" && echo "OK" || echo "FAIL"</verify>
  <done>--publish-at appears in run-cycle --help, value flows through cmd_run_cycle to upload_to_youtube, Instagram is skipped when publish_at is set</done>
</task>

</tasks>

<verification>
python main.py --channel hypothetical-scenarios run-cycle --help
# Should show --publish-at with description

python -c "
from pipeline.upload import upload_to_youtube
import inspect
sig = inspect.signature(upload_to_youtube)
p = sig.parameters['publish_at']
assert p.default is None, 'Default should be None'
print('upload_to_youtube signature OK')
"
</verification>

<success_criteria>
- run-cycle --help shows --publish-at argument with clear description
- upload_to_youtube sets privacyStatus=private + publishAt when publish_at provided
- upload_to_youtube keeps privacyStatus=public when publish_at is None
- Instagram upload skipped with log warning when --publish-at is set
- No behavioral change when --publish-at is omitted (full backward compatibility)
</success_criteria>

<output>
After completion, create `.planning/quick/6-add-scheduled-publish-time-to-run-cycle-/6-SUMMARY.md`
</output>
