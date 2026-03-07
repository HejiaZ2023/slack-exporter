"""Integration tests that hit the real Slack API.

WARNING: These tests require a valid SLACK_USER_TOKEN and create/archive
real channels in the workspace.  Only run in a dedicated test workspace!
"""

import pytest

from exporter import (
    channel_list,
    channel_history,
    channel_replies,
    user_list,
    get_file_list,
    get_data,
    parse_channel_list,
    parse_user_list,
    parse_channel_history,
    parse_replies,
    _ensure_channel_access,
    _restore_channel_archive,
)


# ---------------------------------------------------------------------------
# channel_list
# ---------------------------------------------------------------------------


class TestChannelList:
    def test_returns_list(self):
        result = channel_list()
        assert isinstance(result, list)
        assert len(result) > 0

    def test_includes_public_test_channel(self, populated_public_channel):
        ch_id = populated_public_channel["channel"]["id"]
        channels = channel_list()
        ids = [c["id"] for c in channels]
        assert ch_id in ids

    def test_includes_private_test_channel(self, populated_private_channel):
        ch_id = populated_private_channel["channel"]["id"]
        channels = channel_list()
        ids = [c["id"] for c in channels]
        assert ch_id in ids

    def test_channels_have_required_fields(self):
        channels = channel_list()
        ch = channels[0]
        assert "id" in ch

    def test_parse_channel_list_integration(self, populated_public_channel):
        """parse_channel_list works with real API data."""
        channels = channel_list()
        users = user_list()
        result = parse_channel_list(channels, users)
        assert isinstance(result, str)
        assert len(result) > 0
        # Our test channel should appear
        assert populated_public_channel["channel"]["id"] in result


# ---------------------------------------------------------------------------
# user_list
# ---------------------------------------------------------------------------


class TestUserList:
    def test_returns_list(self):
        result = user_list()
        assert isinstance(result, list)
        assert len(result) > 0

    def test_contains_current_user(self, workspace_info):
        users = user_list()
        user_ids = [u["id"] for u in users]
        assert workspace_info["user_id"] in user_ids

    def test_users_have_required_fields(self):
        users = user_list()
        u = users[0]
        assert "id" in u
        assert "name" in u

    def test_parse_user_list_integration(self, workspace_info):
        """parse_user_list works with real API data."""
        users = user_list()
        result = parse_user_list(users)
        assert isinstance(result, str)
        assert workspace_info["user_id"] in result


# ---------------------------------------------------------------------------
# channel_history
# ---------------------------------------------------------------------------


class TestChannelHistory:
    def test_returns_posted_messages(self, populated_public_channel):
        ch_id = populated_public_channel["channel"]["id"]
        history = channel_history(ch_id)
        assert isinstance(history, list)
        assert len(history) >= 3
        texts = [m.get("text", "") for m in history]
        assert "Test message one" in texts
        assert "Test message two" in texts
        assert "Test message three" in texts

    def test_time_filter_oldest(self, populated_public_channel):
        """oldest is exclusive — messages strictly after this timestamp."""
        msgs = populated_public_channel["messages"]
        oldest_ts = msgs[1]["ts"]
        ch_id = populated_public_channel["channel"]["id"]

        history = channel_history(ch_id, oldest=oldest_ts)
        texts = [m.get("text", "") for m in history]
        assert "Test message one" not in texts
        assert "Test message two" not in texts
        assert "Test message three" in texts

    def test_time_filter_latest(self, populated_public_channel):
        """latest is exclusive — messages strictly before this timestamp."""
        msgs = populated_public_channel["messages"]
        latest_ts = msgs[1]["ts"]
        ch_id = populated_public_channel["channel"]["id"]

        history = channel_history(ch_id, latest=latest_ts)
        texts = [m.get("text", "") for m in history]
        assert "Test message one" in texts
        assert "Test message two" not in texts
        assert "Test message three" not in texts

    def test_time_filter_range(self, populated_public_channel):
        """Combine oldest and latest to select a single message."""
        msgs = populated_public_channel["messages"]
        ch_id = populated_public_channel["channel"]["id"]

        history = channel_history(ch_id, oldest=msgs[0]["ts"], latest=msgs[2]["ts"])
        texts = [m.get("text", "") for m in history]
        assert "Test message one" not in texts
        assert "Test message two" in texts
        assert "Test message three" not in texts

    def test_private_channel_history(self, populated_private_channel):
        ch_id = populated_private_channel["channel"]["id"]
        history = channel_history(ch_id)
        assert isinstance(history, list)
        texts = [m.get("text", "") for m in history]
        assert "Private channel test message" in texts

    def test_parse_channel_history_integration(self, populated_public_channel):
        """parse_channel_history works with real messages."""
        ch_id = populated_public_channel["channel"]["id"]
        history = channel_history(ch_id)
        users = user_list()
        result = parse_channel_history(history, users)
        assert isinstance(result, str)
        assert "Test message one" in result

    def test_nonexistent_channel_returns_empty(self):
        result = channel_history("C000INVALID")
        assert result == []


# ---------------------------------------------------------------------------
# channel_replies
# ---------------------------------------------------------------------------


class TestChannelReplies:
    def test_returns_thread(self, populated_public_channel):
        ch_id = populated_public_channel["channel"]["id"]
        parent_ts = populated_public_channel["messages"][0]["ts"]

        replies = channel_replies([parent_ts], ch_id)
        assert isinstance(replies, list)
        assert len(replies) == 1

        thread = replies[0]
        assert len(thread) >= 2  # parent message + at least one reply
        texts = [m.get("text", "") for m in thread]
        assert "Thread reply to message one" in texts

    def test_empty_timestamps_returns_empty(self, populated_public_channel):
        ch_id = populated_public_channel["channel"]["id"]
        replies = channel_replies([], ch_id)
        assert replies == []

    def test_parse_replies_integration(self, populated_public_channel):
        """parse_replies works with real thread data."""
        ch_id = populated_public_channel["channel"]["id"]
        parent_ts = populated_public_channel["messages"][0]["ts"]
        replies = channel_replies([parent_ts], ch_id)
        users = user_list()
        result = parse_replies(replies, users)
        assert isinstance(result, str)
        assert "Thread reply to message one" in result


# ---------------------------------------------------------------------------
# Archived channel access
# ---------------------------------------------------------------------------


class TestArchivedChannelAccess:
    def test_ensure_access_and_restore(self, archived_channel):
        ch_id = archived_channel["id"]

        # Verify it starts archived
        info = get_data(
            "https://slack.com/api/conversations.info", {"channel": ch_id}
        ).json()
        assert info["ok"]
        assert info["channel"]["is_archived"] is True

        # _ensure_channel_access should unarchive it
        was_archived = _ensure_channel_access(ch_id)
        assert was_archived is True

        # Verify now unarchived
        info = get_data(
            "https://slack.com/api/conversations.info", {"channel": ch_id}
        ).json()
        assert info["ok"]
        assert info["channel"]["is_archived"] is False

        # _restore_channel_archive should re-archive it
        _restore_channel_archive(ch_id)

        # Verify archived again
        info = get_data(
            "https://slack.com/api/conversations.info", {"channel": ch_id}
        ).json()
        assert info["ok"]
        assert info["channel"]["is_archived"] is True


# ---------------------------------------------------------------------------
# get_file_list
# ---------------------------------------------------------------------------


class TestGetFileList:
    def test_runs_without_error(self):
        """get_file_list is a generator; consuming it should not error."""
        files = list(get_file_list())
        assert isinstance(files, list)  # may be empty
