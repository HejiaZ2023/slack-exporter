"""Tests for CSV export functionality (parse_to_csv, save_as_csv).

Unit tests mock HTTP for file/attachment downloads.
Integration tests use real Slack API data via session fixtures.
"""

import csv
import io
from unittest import mock

import pytest

from exporter import (
    parse_to_csv,
    save_as_csv,
    channel_history,
    user_list,
)


# ---------------------------------------------------------------------------
# shared mock data
# ---------------------------------------------------------------------------

MOCK_USERS = [
    {
        "id": "U001",
        "name": "alice",
        "profile": {"real_name": "Alice Smith", "display_name": "alice"},
    },
    {
        "id": "U002",
        "name": "bob",
        "profile": {"real_name": "Bob Jones", "display_name": "bob"},
    },
]


def _msg(user_id, text, ts, **extra):
    msg = {"type": "message", "user": user_id, "text": text, "ts": ts}
    msg.update(extra)
    return msg


# ---------------------------------------------------------------------------
# parse_to_csv — unit tests
# ---------------------------------------------------------------------------


class TestParseToCsv:
    def test_headers(self):
        headers, _ = parse_to_csv([], MOCK_USERS)
        assert headers == [
            "timestamp",
            "user",
            "text",
            "thread_ts",
            "reply_count",
            "media_data",
        ]

    def test_basic_message(self):
        msgs = [_msg("U001", "hello", "1700000000.000100")]
        headers, rows = parse_to_csv(msgs, MOCK_USERS)
        assert len(rows) == 1
        row = rows[0]
        assert row["timestamp"] == "1700000000.000100"
        assert row["user"] == "alice"
        assert row["text"] == "hello"
        assert row["media_data"] == ""

    def test_message_without_user(self):
        msgs = [{"type": "message", "text": "system", "ts": "100.0"}]
        _, rows = parse_to_csv(msgs, MOCK_USERS)
        assert rows[0]["user"] == ""

    def test_message_without_text(self):
        msgs = [{"type": "message", "user": "U001", "ts": "100.0"}]
        _, rows = parse_to_csv(msgs, MOCK_USERS)
        assert rows[0]["text"] == ""

    def test_thread_metadata(self):
        msgs = [
            _msg("U001", "parent", "100.0", thread_ts="100.0", reply_count=3),
        ]
        _, rows = parse_to_csv(msgs, MOCK_USERS)
        assert rows[0]["thread_ts"] == "100.0"
        assert rows[0]["reply_count"] == 3

    def test_thread_metadata_defaults(self):
        msgs = [_msg("U001", "no thread", "100.0")]
        _, rows = parse_to_csv(msgs, MOCK_USERS)
        assert rows[0]["thread_ts"] == ""
        assert rows[0]["reply_count"] == 0

    def test_multiple_messages_order(self):
        msgs = [
            _msg("U001", "first", "100.0"),
            _msg("U002", "second", "101.0"),
        ]
        _, rows = parse_to_csv(msgs, MOCK_USERS)
        assert len(rows) == 2
        assert rows[0]["text"] == "first"
        assert rows[1]["text"] == "second"

    @mock.patch("exporter.requests.get")
    def test_file_attachment_media(self, mock_get):
        mock_resp = mock.Mock(status_code=200, content=b"fakepng")
        mock_get.return_value = mock_resp

        msgs = [
            _msg(
                "U001",
                "see file",
                "100.0",
                files=[
                    {"url_private": "https://files.slack.com/f.png", "name": "f.png"}
                ],
            )
        ]
        _, rows = parse_to_csv(msgs, MOCK_USERS)
        media = rows[0]["media_data"]
        assert media.startswith("data:image/png;base64,")
        assert "ZmFrZXBuZw==" in media  # base64 of b"fakepng"

    @mock.patch("exporter.requests.get")
    def test_multiple_files_joined(self, mock_get):
        mock_get.return_value = mock.Mock(status_code=200, content=b"x")

        msgs = [
            _msg(
                "U001",
                "files",
                "100.0",
                files=[
                    {"url_private": "https://example.com/a.txt", "name": "a.txt"},
                    {"url_private": "https://example.com/b.txt", "name": "b.txt"},
                ],
            )
        ]
        _, rows = parse_to_csv(msgs, MOCK_USERS)
        parts = rows[0]["media_data"].split("||")
        assert len(parts) == 2

    @mock.patch("exporter.requests.get")
    def test_file_download_failure_skipped(self, mock_get):
        mock_get.return_value = mock.Mock(status_code=403, content=b"")

        msgs = [
            _msg(
                "U001",
                "denied",
                "100.0",
                files=[{"url_private": "https://example.com/x.bin", "name": "x.bin"}],
            )
        ]
        _, rows = parse_to_csv(msgs, MOCK_USERS)
        assert rows[0]["media_data"] == ""

    @mock.patch("exporter.requests.get")
    def test_file_download_exception_skipped(self, mock_get):
        mock_get.side_effect = ConnectionError("boom")

        msgs = [
            _msg(
                "U001",
                "err",
                "100.0",
                files=[{"url_private": "https://example.com/x.bin", "name": "x.bin"}],
            )
        ]
        _, rows = parse_to_csv(msgs, MOCK_USERS)
        assert rows[0]["media_data"] == ""

    @mock.patch("exporter.requests.get")
    def test_image_attachment(self, mock_get):
        mock_get.return_value = mock.Mock(status_code=200, content=b"jpg")

        msgs = [
            _msg(
                "U001",
                "img",
                "100.0",
                attachments=[{"image_url": "https://example.com/pic.jpg"}],
            )
        ]
        _, rows = parse_to_csv(msgs, MOCK_USERS)
        assert rows[0]["media_data"].startswith("data:image/jpeg;base64,")

    @mock.patch("exporter.requests.get")
    def test_attachment_without_image_url_ignored(self, mock_get):
        msgs = [
            _msg(
                "U001",
                "link",
                "100.0",
                attachments=[{"title": "A link", "text": "description"}],
            )
        ]
        _, rows = parse_to_csv(msgs, MOCK_USERS)
        assert rows[0]["media_data"] == ""
        mock_get.assert_not_called()

    def test_file_without_url_private_skipped(self):
        msgs = [
            _msg(
                "U001",
                "no url",
                "100.0",
                files=[{"name": "orphan.txt"}],
            )
        ]
        _, rows = parse_to_csv(msgs, MOCK_USERS)
        assert rows[0]["media_data"] == ""

    def test_unknown_user_falls_back(self):
        msgs = [_msg("UUNKNOWN", "hi", "100.0")]
        _, rows = parse_to_csv(msgs, MOCK_USERS)
        assert rows[0]["user"] == "[null user]"


# ---------------------------------------------------------------------------
# save_as_csv — unit tests
# ---------------------------------------------------------------------------


class TestSaveAsCsv:
    @mock.patch("exporter.requests.get")
    def test_writes_valid_csv(self, mock_get, tmp_path):
        msgs = [
            _msg("U001", "hello", "100.0"),
            _msg("U002", "world", "101.0"),
        ]
        filepath = str(tmp_path / "out.csv")
        save_as_csv(msgs, filepath, MOCK_USERS)

        with open(filepath, newline="", encoding="utf-8") as f:
            reader = csv.DictReader(f)
            rows = list(reader)

        assert len(rows) == 2
        assert rows[0]["user"] == "alice"
        assert rows[0]["text"] == "hello"
        assert rows[1]["user"] == "bob"

    @mock.patch("exporter.requests.get")
    def test_csv_has_correct_headers(self, mock_get, tmp_path):
        msgs = [_msg("U001", "x", "100.0")]
        filepath = str(tmp_path / "out.csv")
        save_as_csv(msgs, filepath, MOCK_USERS)

        with open(filepath, newline="", encoding="utf-8") as f:
            reader = csv.reader(f)
            header_row = next(reader)

        assert header_row == [
            "timestamp",
            "user",
            "text",
            "thread_ts",
            "reply_count",
            "media_data",
        ]

    @mock.patch("exporter.requests.get")
    def test_empty_messages(self, mock_get, tmp_path):
        filepath = str(tmp_path / "empty.csv")
        save_as_csv([], filepath, MOCK_USERS)

        with open(filepath, newline="", encoding="utf-8") as f:
            reader = csv.DictReader(f)
            rows = list(reader)

        assert rows == []


# ---------------------------------------------------------------------------
# Integration: parse_to_csv with real API data
# ---------------------------------------------------------------------------


class TestCsvIntegration:
    def test_parse_real_channel_history(self, populated_public_channel):
        ch_id = populated_public_channel["channel"]["id"]
        history = channel_history(ch_id)
        users = user_list()

        headers, rows = parse_to_csv(history, users)

        assert len(rows) >= 3
        texts = [r["text"] for r in rows]
        assert "Test message one" in texts
        assert "Test message two" in texts
        assert "Test message three" in texts

    def test_user_resolved_to_name(self, populated_public_channel, workspace_info):
        ch_id = populated_public_channel["channel"]["id"]
        history = channel_history(ch_id)
        users = user_list()

        _, rows = parse_to_csv(history, users)

        # all rows from our test channel should have a resolved user name
        user_names = {r["user"] for r in rows}
        assert "[null user]" not in user_names
        # the bot user that posted should be the current test user
        assert workspace_info["user"] in user_names

    def test_timestamps_present(self, populated_public_channel):
        ch_id = populated_public_channel["channel"]["id"]
        history = channel_history(ch_id)
        users = user_list()

        _, rows = parse_to_csv(history, users)

        for row in rows:
            assert row["timestamp"] != ""
            # Slack timestamps are "epoch.sequence"
            assert "." in row["timestamp"]

    def test_save_real_data_to_file(self, populated_public_channel, tmp_path):
        ch_id = populated_public_channel["channel"]["id"]
        history = channel_history(ch_id)
        users = user_list()

        filepath = str(tmp_path / "integration.csv")
        save_as_csv(history, filepath, users)

        with open(filepath, newline="", encoding="utf-8") as f:
            reader = csv.DictReader(f)
            rows = list(reader)

        assert len(rows) >= 3
        texts = [r["text"] for r in rows]
        assert "Test message one" in texts
