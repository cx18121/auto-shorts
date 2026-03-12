"""
tests/test_upload.py — Unit tests for pipeline/upload.py

Covers: YouTube OAuth setup, YouTube upload with retry, Instagram upload/publish,
Instagram token refresh, Claude Haiku metadata generation, SQLite DB logging,
upload history query, and retry/backoff behavior.

Standalone: python -m pytest tests/test_upload.py -x -q
"""
from __future__ import annotations

import json
import sqlite3
import sys
import unittest
from datetime import datetime, timezone, timedelta
from pathlib import Path
from unittest.mock import MagicMock, patch, call, mock_open

PROJECT_ROOT = Path(__file__).parent.parent
sys.path.insert(0, str(PROJECT_ROOT))

# RED: ImportError expected until pipeline/upload.py is implemented
from pipeline.upload import (  # noqa: E402
    init_upload_table,
    log_upload,
    get_upload_history,
    setup_youtube_oauth,
    upload_to_youtube,
    upload_to_instagram,
    refresh_instagram_token_if_needed,
    generate_upload_metadata,
)


def _make_conn() -> sqlite3.Connection:
    """In-memory SQLite connection with uploads table."""
    conn = sqlite3.connect(":memory:")
    conn.row_factory = sqlite3.Row
    init_upload_table(conn)
    return conn


# ---------------------------------------------------------------------------
# TestUploadLogging
# ---------------------------------------------------------------------------

class TestUploadLogging(unittest.TestCase):
    """init_upload_table creates schema; log_upload inserts correct row."""

    def test_init_creates_uploads_table(self):
        conn = _make_conn()
        tables = conn.execute(
            "SELECT name FROM sqlite_master WHERE type='table' AND name='uploads'"
        ).fetchone()
        self.assertIsNotNone(tables)

    def test_uploads_table_has_expected_columns(self):
        conn = _make_conn()
        info = conn.execute("PRAGMA table_info(uploads)").fetchall()
        cols = [row[1] for row in info]
        for expected in ("id", "channel", "platform", "video_id", "title", "status",
                         "error_msg", "uploaded_at"):
            self.assertIn(expected, cols)

    def test_log_upload_inserts_row(self):
        conn = _make_conn()
        log_upload(conn, "relationships", "youtube", "yt-abc123", "My Title", "success")
        row = conn.execute("SELECT * FROM uploads").fetchone()
        self.assertIsNotNone(row)
        self.assertEqual(row["channel"], "relationships")
        self.assertEqual(row["platform"], "youtube")
        self.assertEqual(row["video_id"], "yt-abc123")
        self.assertEqual(row["title"], "My Title")
        self.assertEqual(row["status"], "success")
        self.assertIsNone(row["error_msg"])
        self.assertIsNotNone(row["uploaded_at"])

    def test_log_upload_stores_error_msg(self):
        conn = _make_conn()
        log_upload(conn, "finance", "instagram", "ig-999", "Finance tip", "error",
                   error_msg="403 Forbidden")
        row = conn.execute("SELECT * FROM uploads").fetchone()
        self.assertEqual(row["error_msg"], "403 Forbidden")

    def test_log_upload_uploaded_at_is_iso_utc(self):
        conn = _make_conn()
        log_upload(conn, "relationships", "youtube", "yt-001", "Title", "success")
        row = conn.execute("SELECT uploaded_at FROM uploads").fetchone()
        # Should parse without exception
        dt = datetime.fromisoformat(row["uploaded_at"])
        self.assertIsNotNone(dt)


# ---------------------------------------------------------------------------
# TestUploadHistory
# ---------------------------------------------------------------------------

class TestUploadHistory(unittest.TestCase):
    """get_upload_history returns records filtered by channel, newest first."""

    def test_returns_empty_list_when_no_uploads(self):
        conn = _make_conn()
        result = get_upload_history(conn, "relationships")
        self.assertEqual(result, [])

    def test_returns_records_for_channel(self):
        conn = _make_conn()
        log_upload(conn, "relationships", "youtube", "yt-001", "Title 1", "success")
        log_upload(conn, "relationships", "youtube", "yt-002", "Title 2", "success")
        log_upload(conn, "finance", "youtube", "yt-003", "Other", "success")
        result = get_upload_history(conn, "relationships")
        self.assertEqual(len(result), 2)
        channels = [r["channel"] for r in result]
        self.assertTrue(all(c == "relationships" for c in channels))

    def test_filters_by_channel(self):
        conn = _make_conn()
        log_upload(conn, "relationships", "youtube", "yt-001", "Title 1", "success")
        log_upload(conn, "finance", "youtube", "yt-002", "Title 2", "success")
        result = get_upload_history(conn, "finance")
        self.assertEqual(len(result), 1)
        self.assertEqual(result[0]["channel"], "finance")

    def test_respects_limit_parameter(self):
        conn = _make_conn()
        for i in range(25):
            log_upload(conn, "relationships", "youtube", f"yt-{i:03d}", f"Title {i}", "success")
        result = get_upload_history(conn, "relationships", limit=10)
        self.assertEqual(len(result), 10)

    def test_returns_dicts(self):
        conn = _make_conn()
        log_upload(conn, "relationships", "youtube", "yt-001", "Title", "success")
        result = get_upload_history(conn, "relationships")
        self.assertIsInstance(result[0], dict)
        self.assertIn("channel", result[0])


# ---------------------------------------------------------------------------
# TestYouTubeSetup
# ---------------------------------------------------------------------------

class TestYouTubeSetup(unittest.TestCase):
    """setup_youtube_oauth calls InstalledAppFlow and saves token."""

    def _make_channel_cfg(self):
        cfg = MagicMock()
        cfg.youtube_client_id = "fake-client-id"
        cfg.youtube_client_secret = "fake-client-secret"
        return cfg

    @patch("pipeline.upload.InstalledAppFlow")
    def test_calls_from_client_config(self, mock_flow_cls):
        mock_flow = MagicMock()
        mock_flow_cls.from_client_config.return_value = mock_flow
        mock_creds = MagicMock()
        mock_creds.to_json.return_value = '{"token": "abc"}'
        mock_flow.run_local_server.return_value = mock_creds

        token_path = Path("/tmp/test_token.json")
        cfg = self._make_channel_cfg()

        with patch("builtins.open", mock_open()) as mocked_file:
            setup_youtube_oauth(cfg, token_path)

        mock_flow_cls.from_client_config.assert_called_once()
        args = mock_flow_cls.from_client_config.call_args
        # First arg is client config dict
        client_config = args[0][0]
        self.assertIn("installed", client_config)
        self.assertEqual(client_config["installed"]["client_id"], "fake-client-id")
        self.assertEqual(client_config["installed"]["client_secret"], "fake-client-secret")

    @patch("pipeline.upload.InstalledAppFlow")
    def test_uses_youtube_upload_scope(self, mock_flow_cls):
        mock_flow = MagicMock()
        mock_flow_cls.from_client_config.return_value = mock_flow
        mock_creds = MagicMock()
        mock_creds.to_json.return_value = '{"token": "abc"}'
        mock_flow.run_local_server.return_value = mock_creds

        cfg = self._make_channel_cfg()
        with patch("builtins.open", mock_open()):
            setup_youtube_oauth(cfg, Path("/tmp/tok.json"))

        # Check scopes argument
        _, kwargs = mock_flow_cls.from_client_config.call_args
        scopes = kwargs.get("scopes") or mock_flow_cls.from_client_config.call_args[0][1]
        self.assertIn("https://www.googleapis.com/auth/youtube.upload", scopes)

    @patch("pipeline.upload.InstalledAppFlow")
    def test_saves_token_to_path(self, mock_flow_cls):
        mock_flow = MagicMock()
        mock_flow_cls.from_client_config.return_value = mock_flow
        mock_creds = MagicMock()
        mock_creds.to_json.return_value = '{"token": "abc"}'
        mock_flow.run_local_server.return_value = mock_creds

        cfg = self._make_channel_cfg()
        with patch("builtins.open", mock_open()) as mocked_file:
            setup_youtube_oauth(cfg, Path("/tmp/tok.json"))

        mocked_file.assert_called()


# ---------------------------------------------------------------------------
# TestYouTubeUpload
# ---------------------------------------------------------------------------

class TestYouTubeUpload(unittest.TestCase):
    """upload_to_youtube loads creds, builds service, calls videos().insert()."""

    def _make_creds_json(self, expired=False):
        expiry = "2020-01-01T00:00:00Z" if expired else "2099-01-01T00:00:00Z"
        return json.dumps({
            "token": "ya29.test",
            "refresh_token": "1//test_refresh",
            "token_uri": "https://oauth2.googleapis.com/token",
            "client_id": "fake-client-id",
            "client_secret": "fake-client-secret",
            "scopes": ["https://www.googleapis.com/auth/youtube.upload"],
            "expiry": expiry,
        })

    @patch("pipeline.upload.build")
    @patch("pipeline.upload.Credentials")
    def test_calls_videos_insert(self, mock_creds_cls, mock_build):
        mock_creds = MagicMock()
        mock_creds.expired = False
        mock_creds.refresh_token = "1//test_refresh"
        mock_creds_cls.from_authorized_user_file.return_value = mock_creds

        mock_youtube = MagicMock()
        mock_build.return_value = mock_youtube
        mock_request = MagicMock()
        mock_youtube.videos.return_value.insert.return_value = mock_request

        with patch("pipeline.upload._resumable_upload") as mock_resumable:
            mock_resumable.return_value = {"id": "yt-video-123"}
            result = upload_to_youtube(
                video_path=Path("/tmp/test.mp4"),
                title="Test Video",
                description="A test description",
                tags=["tag1", "tag2"],
                token_path=Path("/tmp/token.json"),
                client_id="fake-client-id",
                client_secret="fake-client-secret",
            )

        self.assertEqual(result, "yt-video-123")
        mock_youtube.videos.return_value.insert.assert_called_once()

    @patch("pipeline.upload.build")
    @patch("pipeline.upload.Credentials")
    def test_snippet_has_correct_category(self, mock_creds_cls, mock_build):
        mock_creds = MagicMock()
        mock_creds.expired = False
        mock_creds_cls.from_authorized_user_file.return_value = mock_creds

        mock_youtube = MagicMock()
        mock_build.return_value = mock_youtube
        mock_request = MagicMock()
        mock_youtube.videos.return_value.insert.return_value = mock_request

        with patch("pipeline.upload._resumable_upload") as mock_resumable:
            mock_resumable.return_value = {"id": "yt-video-xyz"}
            upload_to_youtube(
                video_path=Path("/tmp/test.mp4"),
                title="Test Video",
                description="desc",
                tags=[],
                token_path=Path("/tmp/token.json"),
                client_id="cid",
                client_secret="csec",
            )

        _, kwargs = mock_youtube.videos.return_value.insert.call_args
        body = kwargs.get("body") or mock_youtube.videos.return_value.insert.call_args[0][0]
        # body is passed as keyword
        call_kwargs = mock_youtube.videos.return_value.insert.call_args[1]
        self.assertEqual(call_kwargs["body"]["snippet"]["categoryId"], "22")
        self.assertEqual(call_kwargs["body"]["status"]["privacyStatus"], "public")

    @patch("pipeline.upload.build")
    @patch("pipeline.upload.Credentials")
    @patch("pipeline.upload.Request")
    def test_refreshes_expired_credentials(self, mock_request_cls, mock_creds_cls, mock_build):
        mock_creds = MagicMock()
        mock_creds.expired = True
        mock_creds.refresh_token = "1//test_refresh"
        mock_creds_cls.from_authorized_user_file.return_value = mock_creds

        mock_youtube = MagicMock()
        mock_build.return_value = mock_youtube

        with patch("pipeline.upload._resumable_upload") as mock_resumable:
            mock_resumable.return_value = {"id": "yt-refreshed"}
            with patch("builtins.open", mock_open()):
                upload_to_youtube(
                    video_path=Path("/tmp/test.mp4"),
                    title="Test",
                    description="desc",
                    tags=[],
                    token_path=Path("/tmp/token.json"),
                    client_id="cid",
                    client_secret="csec",
                )

        mock_creds.refresh.assert_called_once()


# ---------------------------------------------------------------------------
# TestRetryBehavior
# ---------------------------------------------------------------------------

class TestRetryBehavior(unittest.TestCase):
    """_resumable_upload retries on 5xx HttpError with exponential backoff."""

    @patch("pipeline.upload.time.sleep")
    def test_retries_on_500_error(self, mock_sleep):
        from googleapiclient.errors import HttpError
        from pipeline.upload import _resumable_upload

        mock_request = MagicMock()
        http_error_500 = HttpError(
            resp=MagicMock(status=500, reason="Internal Server Error"),
            content=b"Server Error",
        )
        # Fail twice with 500, then succeed
        mock_request.next_chunk.side_effect = [
            http_error_500,
            http_error_500,
            (None, {"id": "yt-retry-success"}),
        ]

        result = _resumable_upload(mock_request)
        self.assertEqual(result["id"], "yt-retry-success")
        self.assertEqual(mock_sleep.call_count, 2)

    @patch("pipeline.upload.time.sleep")
    def test_raises_on_non_retriable_error(self, mock_sleep):
        from googleapiclient.errors import HttpError
        from pipeline.upload import _resumable_upload

        mock_request = MagicMock()
        http_error_403 = HttpError(
            resp=MagicMock(status=403, reason="Forbidden"),
            content=b"Forbidden",
        )
        mock_request.next_chunk.side_effect = http_error_403

        with self.assertRaises(HttpError):
            _resumable_upload(mock_request)

    @patch("pipeline.upload.time.sleep")
    def test_raises_after_max_retries(self, mock_sleep):
        from googleapiclient.errors import HttpError
        from pipeline.upload import _resumable_upload

        mock_request = MagicMock()
        http_error_503 = HttpError(
            resp=MagicMock(status=503, reason="Service Unavailable"),
            content=b"Unavailable",
        )
        mock_request.next_chunk.side_effect = http_error_503

        with self.assertRaises(HttpError):
            _resumable_upload(mock_request)

        # Should have retried MAX_RETRIES times
        self.assertGreaterEqual(mock_request.next_chunk.call_count, 2)

    @patch("pipeline.upload.time.sleep")
    def test_returns_response_on_success(self, mock_sleep):
        from pipeline.upload import _resumable_upload

        mock_request = MagicMock()
        mock_request.next_chunk.return_value = (None, {"id": "yt-direct"})

        result = _resumable_upload(mock_request)
        self.assertEqual(result["id"], "yt-direct")


# ---------------------------------------------------------------------------
# TestInstagramUpload
# ---------------------------------------------------------------------------

class TestInstagramUpload(unittest.TestCase):
    """upload_to_instagram creates container, polls status, publishes reel."""

    @patch("pipeline.upload.requests.get")
    @patch("pipeline.upload.requests.post")
    def test_successful_upload_returns_media_id(self, mock_post, mock_get):
        # First POST: create container
        container_resp = MagicMock()
        container_resp.json.return_value = {"id": "container-abc"}
        container_resp.raise_for_status = MagicMock()
        # Second POST: publish
        publish_resp = MagicMock()
        publish_resp.json.return_value = {"id": "ig-media-xyz"}
        publish_resp.raise_for_status = MagicMock()
        mock_post.side_effect = [container_resp, publish_resp]

        # GET: poll container status — returns FINISHED immediately
        status_resp = MagicMock()
        status_resp.json.return_value = {"status_code": "FINISHED"}
        status_resp.raise_for_status = MagicMock()
        mock_get.return_value = status_resp

        with patch("pipeline.upload.time.sleep"):
            result = upload_to_instagram(
                video_url="https://example.com/video.mp4",
                caption="Test caption",
                ig_user_id="123456789",
                access_token="IG_TOKEN",
            )

        self.assertEqual(result, "ig-media-xyz")

    @patch("pipeline.upload.requests.get")
    @patch("pipeline.upload.requests.post")
    def test_raises_on_error_status(self, mock_post, mock_get):
        container_resp = MagicMock()
        container_resp.json.return_value = {"id": "container-err"}
        container_resp.raise_for_status = MagicMock()
        mock_post.return_value = container_resp

        status_resp = MagicMock()
        status_resp.json.return_value = {"status_code": "ERROR"}
        status_resp.raise_for_status = MagicMock()
        mock_get.return_value = status_resp

        with patch("pipeline.upload.time.sleep"):
            with self.assertRaises(RuntimeError) as ctx:
                upload_to_instagram(
                    video_url="https://example.com/video.mp4",
                    caption="caption",
                    ig_user_id="123456789",
                    access_token="IG_TOKEN",
                )
        self.assertIn("ERROR", str(ctx.exception))

    @patch("pipeline.upload.requests.get")
    @patch("pipeline.upload.requests.post")
    def test_raises_on_timeout(self, mock_post, mock_get):
        container_resp = MagicMock()
        container_resp.json.return_value = {"id": "container-timeout"}
        container_resp.raise_for_status = MagicMock()
        mock_post.return_value = container_resp

        # Always return IN_PROGRESS — never finishes
        status_resp = MagicMock()
        status_resp.json.return_value = {"status_code": "IN_PROGRESS"}
        status_resp.raise_for_status = MagicMock()
        mock_get.return_value = status_resp

        with patch("pipeline.upload.time.sleep"):
            with self.assertRaises(RuntimeError) as ctx:
                upload_to_instagram(
                    video_url="https://example.com/video.mp4",
                    caption="caption",
                    ig_user_id="123456789",
                    access_token="IG_TOKEN",
                )
        self.assertIn("timeout", str(ctx.exception).lower())

    @patch("pipeline.upload.requests.get")
    @patch("pipeline.upload.requests.post")
    def test_posts_to_correct_endpoints(self, mock_post, mock_get):
        container_resp = MagicMock()
        container_resp.json.return_value = {"id": "container-ep"}
        container_resp.raise_for_status = MagicMock()
        publish_resp = MagicMock()
        publish_resp.json.return_value = {"id": "ig-ep-result"}
        publish_resp.raise_for_status = MagicMock()
        mock_post.side_effect = [container_resp, publish_resp]

        status_resp = MagicMock()
        status_resp.json.return_value = {"status_code": "FINISHED"}
        status_resp.raise_for_status = MagicMock()
        mock_get.return_value = status_resp

        with patch("pipeline.upload.time.sleep"):
            upload_to_instagram(
                video_url="https://example.com/video.mp4",
                caption="caption",
                ig_user_id="999",
                access_token="TOKEN",
            )

        # First POST should hit /999/media
        first_post_url = mock_post.call_args_list[0][0][0]
        self.assertIn("999", first_post_url)
        self.assertIn("media", first_post_url)
        # Second POST should hit /999/media_publish
        second_post_url = mock_post.call_args_list[1][0][0]
        self.assertIn("media_publish", second_post_url)


# ---------------------------------------------------------------------------
# TestInstagramTokenRefresh
# ---------------------------------------------------------------------------

class TestInstagramTokenRefresh(unittest.TestCase):
    """refresh_instagram_token_if_needed refreshes within 7 days of expiry."""

    def _make_token_data(self, days_until_expiry: int) -> dict:
        expires_at = (datetime.now(timezone.utc) + timedelta(days=days_until_expiry)).isoformat()
        return {
            "access_token": "IG_OLD_TOKEN",
            "expires_at": expires_at,
        }

    @patch("pipeline.upload.requests.get")
    def test_refreshes_when_expiring_soon(self, mock_get):
        token_data = self._make_token_data(days_until_expiry=3)  # < 7 days
        token_json = json.dumps(token_data)

        # Mock the refresh API response
        refresh_resp = MagicMock()
        refresh_resp.json.return_value = {
            "access_token": "IG_NEW_TOKEN",
            "expires_in": 5184000,  # 60 days in seconds
        }
        refresh_resp.raise_for_status = MagicMock()
        mock_get.return_value = refresh_resp

        with patch("builtins.open", mock_open(read_data=token_json)) as mocked_open:
            token = refresh_instagram_token_if_needed(Path("/tmp/instagram_token.json"))

        mock_get.assert_called_once()
        # Should return the new token
        self.assertEqual(token, "IG_NEW_TOKEN")

    @patch("pipeline.upload.requests.get")
    def test_does_not_refresh_when_not_expiring_soon(self, mock_get):
        token_data = self._make_token_data(days_until_expiry=30)  # > 7 days
        token_json = json.dumps(token_data)

        with patch("builtins.open", mock_open(read_data=token_json)):
            token = refresh_instagram_token_if_needed(Path("/tmp/instagram_token.json"))

        mock_get.assert_not_called()
        self.assertEqual(token, "IG_OLD_TOKEN")

    @patch("pipeline.upload.requests.get")
    def test_returns_current_token_when_not_refreshing(self, mock_get):
        token_data = self._make_token_data(days_until_expiry=60)
        token_json = json.dumps(token_data)

        with patch("builtins.open", mock_open(read_data=token_json)):
            token = refresh_instagram_token_if_needed(Path("/tmp/instagram_token.json"))

        self.assertEqual(token, "IG_OLD_TOKEN")


# ---------------------------------------------------------------------------
# TestMetadataGeneration
# ---------------------------------------------------------------------------

class TestMetadataGeneration(unittest.TestCase):
    """generate_upload_metadata calls Claude Haiku and returns title + hashtags."""

    def _make_anthropic_response(self, title: str, hashtags: list[str]) -> MagicMock:
        content_block = MagicMock()
        content_block.text = json.dumps({"title": title, "hashtags": hashtags})
        response = MagicMock()
        response.content = [content_block]
        return response

    @patch("pipeline.upload.anthropic.Anthropic")
    def test_returns_title_and_hashtags(self, mock_anthropic_cls):
        mock_client = MagicMock()
        mock_anthropic_cls.return_value = mock_client
        mock_client.messages.create.return_value = self._make_anthropic_response(
            title="This Investment Will Change Your Life",
            hashtags=["investing", "wealth"],
        )

        result = generate_upload_metadata(
            content_text="A story about investing and financial freedom.",
            niche_hashtags=["finance", "money"],
            format_type="storytelling",
        )

        self.assertIn("title", result)
        self.assertIn("hashtags", result)
        self.assertIsInstance(result["title"], str)
        self.assertIsInstance(result["hashtags"], list)

    @patch("pipeline.upload.anthropic.Anthropic")
    def test_merges_niche_hashtags(self, mock_anthropic_cls):
        mock_client = MagicMock()
        mock_anthropic_cls.return_value = mock_client
        mock_client.messages.create.return_value = self._make_anthropic_response(
            title="Test Title",
            hashtags=["investing"],
        )

        result = generate_upload_metadata(
            content_text="About money.",
            niche_hashtags=["finance", "money"],
            format_type="storytelling",
        )

        # Both Claude hashtags and niche_hashtags should be present
        self.assertIn("finance", result["hashtags"])
        self.assertIn("money", result["hashtags"])
        self.assertIn("investing", result["hashtags"])

    @patch("pipeline.upload.anthropic.Anthropic")
    def test_calls_claude_haiku(self, mock_anthropic_cls):
        mock_client = MagicMock()
        mock_anthropic_cls.return_value = mock_client
        mock_client.messages.create.return_value = self._make_anthropic_response(
            title="Test", hashtags=[]
        )

        generate_upload_metadata(
            content_text="Some content",
            niche_hashtags=[],
            format_type="tweets",
        )

        call_kwargs = mock_client.messages.create.call_args[1]
        self.assertIn("haiku", call_kwargs["model"].lower())
        self.assertEqual(call_kwargs["temperature"], 0.85)
        self.assertIn("max_tokens", call_kwargs)

    @patch("pipeline.upload.anthropic.Anthropic")
    def test_title_present_in_result(self, mock_anthropic_cls):
        mock_client = MagicMock()
        mock_anthropic_cls.return_value = mock_client
        mock_client.messages.create.return_value = self._make_anthropic_response(
            title="Compelling Video Title Here",
            hashtags=["tag1"],
        )

        result = generate_upload_metadata(
            content_text="Content text here",
            niche_hashtags=[],
            format_type="storytelling",
        )

        self.assertEqual(result["title"], "Compelling Video Title Here")


if __name__ == "__main__":
    unittest.main()
