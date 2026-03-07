"""Shared fixtures for the slack-exporter test suite.

This module loads .env and ensures SLACK_USER_TOKEN is available before
any test module imports the exporter (which checks the token at module level).
"""

import os
import sys
import uuid
import time
import requests
import pytest
from dotenv import load_dotenv

# ---------------------------------------------------------------------------
# load .env and fix sys.path BEFORE any test module imports exporter
# ---------------------------------------------------------------------------
_repo_root = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
_env_file = os.path.join(_repo_root, ".env")
if os.path.isfile(_env_file):
    load_dotenv(_env_file)

if _repo_root not in sys.path:
    sys.path.insert(0, _repo_root)

if not os.environ.get("SLACK_USER_TOKEN"):
    sys.exit(
        "SLACK_USER_TOKEN is not set.\n"
        "Add it to a .env file or export it in your shell. See README for details."
    )


# ---------------------------------------------------------------------------
# pytest options
# ---------------------------------------------------------------------------


def pytest_addoption(parser):
    parser.addoption(
        "--force",
        action="store_true",
        default=False,
        help="Skip interactive workspace confirmation prompt",
    )


# ---------------------------------------------------------------------------
# session-scoped fixtures
# ---------------------------------------------------------------------------


@pytest.fixture(scope="session")
def slack_headers():
    """Authorization headers for direct Slack API calls in fixtures."""
    token = os.environ["SLACK_USER_TOKEN"]
    return {"Authorization": f"Bearer {token}"}


@pytest.fixture(scope="session")
def workspace_info(slack_headers):
    """Fetch workspace and user info via auth.test."""
    r = requests.get("https://slack.com/api/auth.test", headers=slack_headers)
    data = r.json()
    if not data.get("ok"):
        pytest.exit(f"Slack auth.test failed: {data.get('error')}")
    return {
        "team": data.get("team", "unknown"),
        "team_id": data.get("team_id"),
        "user": data.get("user", "unknown"),
        "user_id": data.get("user_id"),
    }


@pytest.fixture(scope="session", autouse=True)
def confirm_workspace(request, workspace_info):
    """Print workspace info and prompt for confirmation (unless --force)."""
    force = request.config.getoption("--force")
    ws = workspace_info

    print(f"\n{'=' * 60}")
    print(f"  Slack Exporter Test Suite")
    print(f"  Workspace : {ws['team']}")
    print(f"  User      : {ws['user']}")
    print(f"{'=' * 60}")

    if not force:
        # addopts = -s in pytest.ini ensures we see the prompt
        answer = input(f"\nRun tests in workspace '{ws['team']}'? [y/N] ")
        if answer.lower() != "y":
            pytest.exit("Test run cancelled by user.")


# ---------------------------------------------------------------------------
# helpers
# ---------------------------------------------------------------------------


def _slack_post(headers, url, json_data):
    return requests.post(url, headers=headers, json=json_data)


# ---------------------------------------------------------------------------
# channel fixtures
# ---------------------------------------------------------------------------


@pytest.fixture(scope="session")
def public_channel(slack_headers):
    """Create a temporary public channel; archive it after all tests."""
    suffix = uuid.uuid4().hex[:8]
    name = f"_test_pub_{suffix}"

    r = _slack_post(
        slack_headers,
        "https://slack.com/api/conversations.create",
        {"name": name, "is_private": False},
    )
    data = r.json()
    assert data["ok"], f"Failed to create public channel '{name}': {data.get('error')}"
    channel = data["channel"]

    yield channel

    _slack_post(
        slack_headers,
        "https://slack.com/api/conversations.archive",
        {"channel": channel["id"]},
    )


@pytest.fixture(scope="session")
def private_channel(slack_headers):
    """Create a temporary private channel; archive it after all tests."""
    suffix = uuid.uuid4().hex[:8]
    name = f"_test_priv_{suffix}"

    r = _slack_post(
        slack_headers,
        "https://slack.com/api/conversations.create",
        {"name": name, "is_private": True},
    )
    data = r.json()
    assert data["ok"], f"Failed to create private channel '{name}': {data.get('error')}"
    channel = data["channel"]

    yield channel

    _slack_post(
        slack_headers,
        "https://slack.com/api/conversations.archive",
        {"channel": channel["id"]},
    )


@pytest.fixture(scope="session")
def populated_public_channel(slack_headers, public_channel):
    """Post known messages (including a thread) to the public test channel."""
    ch_id = public_channel["id"]
    messages = []

    for text in [
        "Test message one",
        "Test message two",
        "Test message three",
    ]:
        r = _slack_post(
            slack_headers,
            "https://slack.com/api/chat.postMessage",
            {"channel": ch_id, "text": text},
        )
        data = r.json()
        assert data["ok"], f"Failed to post message: {data.get('error')}"
        messages.append(data["message"])
        time.sleep(0.5)  # small delay so timestamps are well-separated

    # thread reply on the first message
    r = _slack_post(
        slack_headers,
        "https://slack.com/api/chat.postMessage",
        {
            "channel": ch_id,
            "text": "Thread reply to message one",
            "thread_ts": messages[0]["ts"],
        },
    )
    data = r.json()
    assert data["ok"], f"Failed to post thread reply: {data.get('error')}"
    thread_reply = data["message"]

    return {
        "channel": public_channel,
        "messages": messages,
        "thread_reply": thread_reply,
    }


@pytest.fixture(scope="session")
def populated_private_channel(slack_headers, private_channel):
    """Post a known message to the private test channel."""
    ch_id = private_channel["id"]

    r = _slack_post(
        slack_headers,
        "https://slack.com/api/chat.postMessage",
        {"channel": ch_id, "text": "Private channel test message"},
    )
    data = r.json()
    assert data["ok"], f"Failed to post message: {data.get('error')}"

    return {
        "channel": private_channel,
        "message": data["message"],
    }


@pytest.fixture(scope="session")
def archived_channel(slack_headers):
    """Create a channel, post a message, archive it. Used for unarchive tests."""
    suffix = uuid.uuid4().hex[:8]
    name = f"_test_arch_{suffix}"

    # create
    r = _slack_post(
        slack_headers,
        "https://slack.com/api/conversations.create",
        {"name": name, "is_private": False},
    )
    data = r.json()
    assert data["ok"], f"Failed to create channel '{name}': {data.get('error')}"
    channel = data["channel"]
    ch_id = channel["id"]

    # post a message so there is content to retrieve
    r = _slack_post(
        slack_headers,
        "https://slack.com/api/chat.postMessage",
        {"channel": ch_id, "text": "Message before archiving"},
    )
    assert r.json()["ok"], f"Failed to post message: {r.json().get('error')}"

    # archive
    r = _slack_post(
        slack_headers,
        "https://slack.com/api/conversations.archive",
        {"channel": ch_id},
    )
    assert r.json()["ok"], f"Failed to archive channel: {r.json().get('error')}"

    yield channel

    # ensure archived (in case a test unarchived it)
    _slack_post(
        slack_headers,
        "https://slack.com/api/conversations.archive",
        {"channel": ch_id},
    )
