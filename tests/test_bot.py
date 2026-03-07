"""Tests for the Flask bot routes.

These tests use Flask's test client with mocked exporter functions,
so they exercise the bot's routing and file-handling logic without
making real Slack API calls.
"""

import json
import os
from unittest import mock
import pytest

import bot


@pytest.fixture
def client():
    """Flask test client."""
    bot.app.config["TESTING"] = True
    with bot.app.test_client() as c:
        yield c


@pytest.fixture(autouse=True)
def exports_dir():
    """Ensure the exports directory exists and clean up leftover files after each test."""
    d = os.path.join(bot.app.root_path, "exports")
    os.makedirs(d, exist_ok=True)
    yield d
    for f in os.listdir(d):
        try:
            os.remove(os.path.join(d, f))
        except OSError:
            pass


FORM_BASE = {
    "team_id": "T001",
    "team_domain": "testworkspace",
    "channel_id": "C001",
    "channel_name": "general",
    "response_url": "https://hooks.example.com/response",
}

MOCK_HISTORY = [
    {"type": "message", "user": "U001", "text": "Hello", "ts": "1609459200.000100"},
    {"type": "message", "user": "U001", "text": "World", "ts": "1609459201.000100"},
]

MOCK_USERS = [
    {
        "id": "U001",
        "name": "alice",
        "profile": {"real_name": "Alice Smith", "display_name": "alice"},
    }
]


# ---------------------------------------------------------------------------
# /slack/events/export-channel
# ---------------------------------------------------------------------------


class TestExportChannel:
    @mock.patch("bot.post_response")
    @mock.patch("bot.user_list", return_value=MOCK_USERS)
    @mock.patch("bot.channel_history", return_value=MOCK_HISTORY)
    def test_text_mode(self, mock_hist, mock_users, mock_post, client, exports_dir):
        form = {**FORM_BASE, "text": "text"}
        resp = client.post("/slack/events/export-channel", data=form)
        assert resp.status_code == 200

        txt_files = [f for f in os.listdir(exports_dir) if f.endswith(".txt")]
        assert len(txt_files) == 1

        with open(os.path.join(exports_dir, txt_files[0])) as fh:
            content = fh.read()
        assert "Channel Name: general" in content
        assert "Hello" in content

    @mock.patch("bot.post_response")
    @mock.patch("bot.channel_history", return_value=MOCK_HISTORY)
    def test_json_mode(self, mock_hist, mock_post, client, exports_dir):
        form = {**FORM_BASE, "text": "json"}
        resp = client.post("/slack/events/export-channel", data=form)
        assert resp.status_code == 200

        json_files = [f for f in os.listdir(exports_dir) if f.endswith(".json")]
        assert len(json_files) == 1

        with open(os.path.join(exports_dir, json_files[0])) as fh:
            data = json.load(fh)
        assert isinstance(data, list)
        assert data[0]["text"] == "Hello"

    @mock.patch("bot.post_response")
    def test_missing_form_field(self, mock_post, client):
        resp = client.post(
            "/slack/events/export-channel", data={"team_id": "T001"}
        )
        # Bot returns 200 with error text even on bad input
        assert resp.status_code == 200


# ---------------------------------------------------------------------------
# /slack/events/export-replies
# ---------------------------------------------------------------------------


class TestExportReplies:
    @mock.patch("bot.post_response")
    @mock.patch("bot.user_list", return_value=MOCK_USERS)
    @mock.patch(
        "bot.channel_replies",
        return_value=[
            [
                {"type": "message", "user": "U001", "text": "parent", "ts": "100.0"},
                {"type": "message", "user": "U001", "text": "reply", "ts": "101.0"},
            ]
        ],
    )
    @mock.patch("bot.channel_history", return_value=MOCK_HISTORY)
    def test_text_mode(
        self, mock_hist, mock_replies, mock_users, mock_post, client, exports_dir
    ):
        form = {**FORM_BASE, "text": "text"}
        resp = client.post("/slack/events/export-replies", data=form)
        assert resp.status_code == 200

        txt_files = [f for f in os.listdir(exports_dir) if f.endswith(".txt")]
        assert len(txt_files) == 1

        with open(os.path.join(exports_dir, txt_files[0])) as fh:
            content = fh.read()
        assert "Threads in:" in content

    @mock.patch("bot.post_response")
    @mock.patch(
        "bot.channel_replies",
        return_value=[
            [
                {"type": "message", "user": "U001", "text": "parent", "ts": "100.0"},
            ]
        ],
    )
    @mock.patch("bot.channel_history", return_value=MOCK_HISTORY)
    def test_json_mode(
        self, mock_hist, mock_replies, mock_post, client, exports_dir
    ):
        form = {**FORM_BASE, "text": "json"}
        resp = client.post("/slack/events/export-replies", data=form)
        assert resp.status_code == 200

        json_files = [f for f in os.listdir(exports_dir) if f.endswith(".json")]
        assert len(json_files) == 1

        with open(os.path.join(exports_dir, json_files[0])) as fh:
            data = json.load(fh)
        assert isinstance(data, list)

    @mock.patch("bot.post_response")
    def test_missing_form_field(self, mock_post, client):
        resp = client.post(
            "/slack/events/export-replies", data={"team_id": "T001"}
        )
        assert resp.status_code == 200


# ---------------------------------------------------------------------------
# /download/<filename>
# ---------------------------------------------------------------------------


class TestDownloadRoute:
    def test_download_text_file(self, client, exports_dir):
        filepath = os.path.join(exports_dir, "testfile.txt")
        with open(filepath, "w") as f:
            f.write("hello world")

        resp = client.get("/download/testfile.txt")
        assert resp.status_code == 200
        assert b"hello world" in resp.data
        assert resp.content_type.startswith("text/plain")
        # File is deleted after download
        assert not os.path.exists(filepath)

    def test_download_json_file(self, client, exports_dir):
        filepath = os.path.join(exports_dir, "data.json")
        with open(filepath, "w") as f:
            f.write('{"key": "value"}')

        resp = client.get("/download/data.json")
        assert resp.status_code == 200
        assert resp.content_type.startswith("application/json")
        assert not os.path.exists(filepath)

    def test_content_disposition_header(self, client, exports_dir):
        filepath = os.path.join(exports_dir, "export.txt")
        with open(filepath, "w") as f:
            f.write("data")

        resp = client.get("/download/export.txt")
        assert "attachment" in resp.headers.get("Content-Disposition", "")
