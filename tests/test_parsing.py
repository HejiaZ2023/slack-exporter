"""Unit tests for exporter parsing and utility functions.

These tests use mocked data and do not make actual Slack API calls.
"""

from unittest import mock
import pytest

from exporter import (
    handle_print,
    name_from_uid,
    name_from_ch_id,
    parse_channel_list,
    parse_user_list,
    parse_channel_history,
    parse_replies,
    download_file,
    _rate_limit_retry,
)

# ---------------------------------------------------------------------------
# shared mock data
# ---------------------------------------------------------------------------

MOCK_USERS = [
    {
        "id": "U001",
        "name": "alice",
        "profile": {"real_name": "Alice Smith", "display_name": "alice"},
        "tz": "America/New_York",
        "is_admin": True,
        "is_owner": False,
        "is_primary_owner": False,
        "is_restricted": False,
        "is_ultra_restricted": False,
        "is_bot": False,
        "is_app_user": False,
    },
    {
        "id": "U002",
        "name": "bob",
        "profile": {"real_name": "Bob Jones", "display_name": "bob"},
        "tz": "Europe/London",
        "is_admin": False,
        "is_owner": False,
        "is_primary_owner": False,
        "is_restricted": False,
        "is_ultra_restricted": False,
        "is_bot": True,
        "is_app_user": False,
    },
    {
        "id": "U003",
        "name": "charlie",
        "profile": {"real_name": "Charlie Brown", "display_name": "charlie"},
        "tz": "Asia/Tokyo",
        "is_admin": False,
        "is_owner": True,
        "is_primary_owner": True,
        "is_restricted": False,
        "is_ultra_restricted": False,
        "is_bot": False,
        "is_app_user": False,
    },
]

MOCK_CHANNELS = [
    {
        "id": "C001",
        "name": "general",
        "is_private": False,
        "is_im": False,
        "is_mpim": False,
        "is_group": False,
        "creator": "U001",
    },
    {
        "id": "C002",
        "name": "secret",
        "is_private": True,
        "is_im": False,
        "is_mpim": False,
        "is_group": False,
        "creator": "U002",
    },
    {
        "id": "D001",
        "name": "",
        "is_private": False,
        "is_im": True,
        "is_mpim": False,
        "is_group": False,
        "user": "U003",
    },
    {
        "id": "G001",
        "name": "group-chat",
        "is_private": False,
        "is_im": False,
        "is_mpim": True,
        "is_group": False,
        "creator": "U001",
    },
]


def _msg(user_id, text, ts, **extra):
    """Helper to build a Slack-style message dict."""
    msg = {"type": "message", "user": user_id, "text": text, "ts": ts}
    msg.update(extra)
    return msg


# ---------------------------------------------------------------------------
# handle_print
# ---------------------------------------------------------------------------


class TestHandlePrint:
    def test_prints_to_stdout(self, capsys):
        handle_print("hello")
        assert "hello" in capsys.readouterr().out

    @mock.patch("exporter.requests.post")
    def test_posts_to_response_url(self, mock_post):
        handle_print("hello", response_url="https://hooks.example.com/resp")
        mock_post.assert_called_once_with(
            "https://hooks.example.com/resp", json={"text": "hello"}
        )


# ---------------------------------------------------------------------------
# name_from_uid / name_from_ch_id
# ---------------------------------------------------------------------------


class TestNameFromUid:
    def test_display_name(self):
        assert name_from_uid("U001", MOCK_USERS) == "alice"

    def test_real_name(self):
        assert name_from_uid("U001", MOCK_USERS, real=True) == "Alice Smith"

    def test_missing_user(self):
        assert name_from_uid("U999", MOCK_USERS) == "[null user]"

    def test_real_fallback_to_display_name(self):
        users = [{"id": "U010", "name": "x", "profile": {"display_name": "disp"}}]
        assert name_from_uid("U010", users, real=True) == "disp"

    def test_real_no_name_at_all(self):
        users = [{"id": "U010", "name": "x", "profile": {}}]
        assert name_from_uid("U010", users, real=True) == "[no full name]"


class TestNameFromChId:
    def test_channel(self):
        name, typ = name_from_ch_id("C001", MOCK_CHANNELS)
        assert name == "general"
        assert typ == "Channel"

    def test_direct_message(self):
        name, typ = name_from_ch_id("D001", MOCK_CHANNELS)
        assert name == "U003"
        assert typ == "Direct Message"

    def test_missing_channel(self):
        assert name_from_ch_id("X999", MOCK_CHANNELS) == "[null channel]"


# ---------------------------------------------------------------------------
# parse_channel_list
# ---------------------------------------------------------------------------


class TestParseChannelList:
    def test_contains_channel_ids(self):
        result = parse_channel_list(MOCK_CHANNELS, MOCK_USERS)
        assert "C001" in result
        assert "C002" in result
        assert "D001" in result
        assert "G001" in result

    def test_channel_names(self):
        result = parse_channel_list(MOCK_CHANNELS, MOCK_USERS)
        assert "general" in result
        assert "secret" in result

    def test_private_label(self):
        result = parse_channel_list(MOCK_CHANNELS, MOCK_USERS)
        assert "private" in result

    def test_type_labels(self):
        result = parse_channel_list(MOCK_CHANNELS, MOCK_USERS)
        assert "channel" in result
        assert "direct_message" in result
        assert "multiparty-direct_message" in result

    def test_creator_attribution(self):
        result = parse_channel_list(MOCK_CHANNELS, MOCK_USERS)
        assert "created by alice" in result

    def test_dm_user_attribution(self):
        result = parse_channel_list(MOCK_CHANNELS, MOCK_USERS)
        assert "with charlie" in result


# ---------------------------------------------------------------------------
# parse_user_list
# ---------------------------------------------------------------------------


class TestParseUserList:
    def test_contains_user_ids(self):
        result = parse_user_list(MOCK_USERS)
        assert "U001" in result
        assert "U002" in result
        assert "U003" in result

    def test_display_names(self):
        result = parse_user_list(MOCK_USERS)
        assert "alice" in result
        assert "bob" in result

    def test_real_names(self):
        result = parse_user_list(MOCK_USERS)
        assert "Alice Smith" in result

    def test_timezone(self):
        result = parse_user_list(MOCK_USERS)
        assert "America/New_York" in result
        assert "Europe/London" in result

    def test_admin_flag(self):
        result = parse_user_list(MOCK_USERS)
        assert "admin" in result

    def test_bot_flag(self):
        result = parse_user_list(MOCK_USERS)
        assert "bot" in result

    def test_owner_flags(self):
        result = parse_user_list(MOCK_USERS)
        assert "owner" in result
        assert "primary_owner" in result

    def test_trailing_pipe_stripped(self):
        result = parse_user_list(MOCK_USERS)
        for line in result.strip().split("\n"):
            assert not line.rstrip().endswith("|")


# ---------------------------------------------------------------------------
# parse_channel_history
# ---------------------------------------------------------------------------


class TestParseChannelHistory:
    def test_basic_message(self):
        msgs = [_msg("U001", "Hello world", "1609459200.000100")]
        result = parse_channel_history(msgs, MOCK_USERS)
        assert "Hello world" in result
        assert "alice" in result
        assert "Alice Smith" in result

    def test_empty_text(self):
        msgs = [_msg("U001", "   ", "1609459200.000100")]
        result = parse_channel_history(msgs, MOCK_USERS)
        assert "[no message content]" in result

    def test_timestamp_formatting(self):
        msgs = [_msg("U001", "hi", "1609459200.000100")]
        result = parse_channel_history(msgs, MOCK_USERS)
        assert "Message at " in result

    def test_user_mention_expansion(self):
        msgs = [_msg("U001", "Hey <@U002> check this", "1609459200.000100")]
        result = parse_channel_history(msgs, MOCK_USERS)
        assert "<@U002> (bob)" in result

    def test_reactions(self):
        msgs = [
            _msg(
                "U001",
                "react test",
                "1609459200.000100",
                reactions=[{"name": "thumbsup", "users": ["U001", "U002"]}],
            )
        ]
        result = parse_channel_history(msgs, MOCK_USERS)
        assert "Reactions:" in result
        assert "thumbsup" in result
        assert "alice" in result
        assert "bob" in result

    def test_files(self):
        msgs = [
            _msg(
                "U001",
                "file test",
                "1609459200.000100",
                files=[
                    {
                        "id": "F001",
                        "name": "report.pdf",
                        "url_private_download": "https://files.slack.com/report.pdf",
                    }
                ],
            )
        ]
        result = parse_channel_history(msgs, MOCK_USERS)
        assert "Files:" in result
        assert "report.pdf" in result
        assert "F001" in result

    def test_deleted_files(self):
        msgs = [
            _msg(
                "U001",
                "deleted file",
                "1609459200.000100",
                files=[{"id": "F002"}],
            )
        ]
        result = parse_channel_history(msgs, MOCK_USERS)
        assert "deleted, oversize, or unavailable" in result

    def test_thread_indentation(self):
        msgs = [_msg("U001", "thread msg", "1609459200.000100", parent_user_id="U002")]
        result = parse_channel_history(msgs, MOCK_USERS, check_thread=True)
        assert "\t" in result

    def test_no_thread_indentation_without_flag(self):
        msgs = [_msg("U001", "thread msg", "1609459200.000100", parent_user_id="U002")]
        result = parse_channel_history(msgs, MOCK_USERS, check_thread=False)
        lines = [l for l in result.split("\n") if l.strip()]
        assert all(not l.startswith("\t") for l in lines)

    def test_message_without_user(self):
        msgs = [{"type": "message", "text": "system msg", "ts": "1609459200.000100"}]
        result = parse_channel_history(msgs, MOCK_USERS)
        assert "system msg" in result

    def test_messages_dict_wrapper(self):
        """Accepts a dict with a 'messages' key."""
        msgs = {"messages": [_msg("U001", "wrapped", "1609459200.000100")]}
        result = parse_channel_history(msgs, MOCK_USERS)
        assert "wrapped" in result

    def test_separator_between_messages(self):
        msgs = [
            _msg("U001", "first", "1609459200.000100"),
            _msg("U002", "second", "1609459201.000100"),
        ]
        result = parse_channel_history(msgs, MOCK_USERS)
        assert "************************" in result

    def test_non_message_types_filtered(self):
        msgs = [
            _msg("U001", "real msg", "1609459200.000100"),
            {"type": "channel_join", "user": "U001", "text": "joined", "ts": "100.0"},
        ]
        result = parse_channel_history(msgs, MOCK_USERS)
        assert "real msg" in result
        # channel_join is not type "message", so it should be filtered out


# ---------------------------------------------------------------------------
# parse_replies
# ---------------------------------------------------------------------------


class TestParseReplies:
    def test_basic_threads(self):
        threads = [
            [
                _msg("U001", "parent", "100.0"),
                _msg("U002", "reply", "101.0"),
            ],
        ]
        result = parse_replies(threads, MOCK_USERS)
        assert "parent" in result
        assert "reply" in result

    def test_multiple_threads(self):
        threads = [
            [_msg("U001", "thread-1-parent", "100.0")],
            [_msg("U002", "thread-2-parent", "200.0")],
        ]
        result = parse_replies(threads, MOCK_USERS)
        assert "thread-1-parent" in result
        assert "thread-2-parent" in result

    def test_empty_threads(self):
        result = parse_replies([], MOCK_USERS)
        assert result == ""


# ---------------------------------------------------------------------------
# download_file (mocked HTTP)
# ---------------------------------------------------------------------------


class TestDownloadFile:
    def test_skips_existing_file(self, tmp_path, capsys):
        dest = tmp_path / "existing.txt"
        dest.write_text("already here")
        result = download_file(str(dest), "https://example.com/f")
        assert result is True
        assert "Skipping" in capsys.readouterr().out

    @mock.patch("exporter.requests.get")
    def test_successful_download(self, mock_get, tmp_path):
        dest = tmp_path / "new.bin"
        mock_get.return_value.content = b"file-content-bytes"
        result = download_file(str(dest), "https://example.com/f")
        assert result is True
        assert dest.read_bytes() == b"file-content-bytes"

    @mock.patch("exporter.requests.get", side_effect=ConnectionError("fail"))
    def test_failed_download(self, mock_get, tmp_path):
        dest = tmp_path / "fail.bin"
        result = download_file(str(dest), "https://example.com/f")
        assert result is False


# ---------------------------------------------------------------------------
# _rate_limit_retry (mocked)
# ---------------------------------------------------------------------------


class TestRateLimitRetry:
    def test_immediate_success(self):
        resp = mock.Mock(status_code=200)
        result = _rate_limit_retry(lambda: resp)
        assert result.status_code == 200

    @mock.patch("exporter.sleep")
    def test_retries_on_429(self, mock_sleep):
        rate_resp = mock.Mock(status_code=429, headers={"Retry-After": "1"})
        ok_resp = mock.Mock(status_code=200)
        calls = {"n": 0}

        def fn():
            calls["n"] += 1
            return rate_resp if calls["n"] == 1 else ok_resp

        result = _rate_limit_retry(fn)
        assert result.status_code == 200
        mock_sleep.assert_called_once()

    @mock.patch("exporter.sleep")
    def test_sleep_duration_includes_buffer(self, mock_sleep):
        rate_resp = mock.Mock(status_code=429, headers={"Retry-After": "3"})
        ok_resp = mock.Mock(status_code=200)
        calls = {"n": 0}

        def fn():
            calls["n"] += 1
            return rate_resp if calls["n"] == 1 else ok_resp

        _rate_limit_retry(fn)
        # ADDITIONAL_SLEEP_TIME=2, so total sleep should be 5
        mock_sleep.assert_called_once_with(5)
