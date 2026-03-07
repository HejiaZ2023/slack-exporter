# slack-exporter

A Slack bot and standalone script for exporting messages and file attachments from public and private channels, using Slack's new Conversations API.

A similar service is provided by Slack for workspace admins at [https://my.slack.com/services/export](https://my.slack.com/services/export) (where `my` can be replaced with your full workspace name to refer to a workspace different than your default). However, it can only access public channels, while `slack-exporter` can retrieve data from any channel accessible to your user account.

## Authentication with Slack

There are two ways to use `slack-exporter` (detailed below). Both require a Slack API token to be able to communicate with your workspace.

1. Visit [https://api.slack.com/apps/](https://api.slack.com/apps/) and sign in to your workspace.
2. Click `Create New App`. If prompted to select "how you'd like to configure your app's scopes", choose the `App Manifest` option. You can configure the app manually instead, but you will be prompted to enter an app name and additional steps to set up permissions instead of the single step below. Once created, select your workspace.
3. You should then be prompted for an app manifest. Paste the contents of the `slack.yaml` file (in the root of this repo) into the YAML box.
4. Select `Install App` in the side bar, then `Install to Workspace` (or `Reinstall to Workspace` if you have done this previously) and accept at the prompt.
5. Copy the `OAuth Access Token` (which will generally start with `xoxp` for user-level permissions and may be located in a section like "OAuth & Permissions" in the sidebar).

## Usage

### As a standalone script

`exporter.py` can create an archive of all conversation history in your workspace which is accessible to your user account.

1. Either add 

    ```text
    SLACK_USER_TOKEN = xoxp-xxxxxxxxxxxxx...
    ```
    
    to a file named `.env` in the same directory as `exporter.py`, or run the following in your shell (replacing the value with the user token you obtained in the [Authentication with Slack](#authentication-with-slack) section above).

    ```shell script
    export SLACK_USER_TOKEN=xoxp-xxxxxxxxxxxxx...
    ```

2. If you cloned this repo, make sure that dependencies are installed by running `pip install -r requirements.txt` in the repo root directory.
3. Run `python exporter.py --help` to view the available export options. You can test that access to Slack is working by listing available conversations: `python exporter.py --lc`.

### As a Slack bot

`bot.py` is a Slack bot that responds to "slash commands" in Slack channels (e.g., `/export-channel`). To connect the bot to the Slack app generated in [Authentication with Slack](#authentication-with-slack), create a file named `.env` in the root directory of this repo, and add the following line:

```text
SLACK_USER_TOKEN = xoxp-xxxxxxxxxxxxx...
```

Save this file and run the Flask application in `bot.py` such that the application is exposed to the Internet. This can be done via a web server (e.g., Heroku), as well as via the ngrok service, which assigns your `localhost` server a public URL.

To use the ngrok method:

1. [Download](https://ngrok.com/download) the appropriate binary.
2. Run `python bot.py`
3. Run the ngrok binary with `path/to/ngrok http 5000`, where `5000` is the port on which the Flask application (step 2) is running. Copy the forwarding HTTPS address provided.

4. Create the following slash commands will be created (one for each applicable Flask route in `bot.py`):

    | Command         | Request URL                               | Arguments    | Example Usage        |
    |-----------------|-------------------------------------------|--------------|----------------------|
    | /export-channel | https://`[host_url]`/slack/export-channel | json \| text | /export-channel text |
    | /export-replies | https://`[host_url]`/slack/export-replies | json \| text | /export-replies json |

    To do this, uncomment the `slash-commands` section in `slack.yaml` and replace `YOUR_HOST_URL_HERE` with something like `https://xxxxxxxxxxxx.ngrok.io` (if using ngrok). Then navigate back to `OAuth & Permissions` and click `(Re)install to Workspace` to add these slash commands to the workspace (ensure the OAuth token in your `.env` file is still correct).

### CSV export

Use `--csv` with the exporter to output in CSV format instead of plain text:

```
python exporter.py --csv -c -o ./exports
```

Each channel is written to a separate `.csv` file with columns: `timestamp`, `user`, `text`, `thread_ts`, `reply_count`, and `media_data`. Attached files and images are downloaded and embedded as base64 data URIs in the `media_data` column.

To convert existing JSON exports to CSV after the fact, you can use `converter_to_csv.py`:

```
python converter_to_csv.py exports/slack_export_2024-01-01_120000
```

Pass `--user-list` with a user list JSON (from `python exporter.py --lu --json -o ./exports`) to resolve user IDs to display names.

## Testing

> [!WARNING]
> The test suite creates channels, posts messages, archives/unarchives channels, and
> performs other **write operations** in your Slack workspace. **Only run these tests
> against a dedicated test workspace.** Do not run them against a production workspace.

### Setup

1. **Add write scopes** to your Slack app manifest. In `slack.yaml` (or in your app settings at <https://api.slack.com/apps/>), paste the following scopes under `oauth_config.scopes.user` alongside the existing read scopes:

    ```yaml
    - channels:write
    - chat:write
    - groups:write
    - im:write
    - mpim:write
    ```

    After updating scopes, click **Reinstall to Workspace** (under *OAuth & Permissions*) and update the token in your `.env` file if it has changed.

2. **Install test dependencies:**

    ```shell
    pip install -r requirements-test.txt
    ```

3. **Run the tests:**

    ```shell
    pytest tests/ -v
    ```

    Before any tests execute you will be shown the workspace name and prompted to confirm.
    To skip the interactive prompt (e.g., in CI), pass `--force`:

    ```shell
    pytest tests/ --force -v
    ```

### What the tests do

| File | Scope | Description |
|------|-------|-------------|
| `test_parsing.py` | Unit | Parsing helpers, name lookups, rate-limit retry, download (mocked HTTP) |
| `test_api_integration.py` | Integration | Channel list/history, user list, replies, time-range filters, archived-channel access against the real Slack API |
| `test_bot.py` | Unit | Flask route logic with mocked exporter functions, file download/cleanup |

The integration tests create temporary channels whose names start with `_test_` (e.g., `_test_pub_a1b2c3d4`). These are archived automatically when the test session ends. Deletion is restricted to the `admin` scope, which requires an Enterprise plan, so we can't fully clean up automatically.

> **Note:** Integration tests make real API calls and may be slow if rate-limited. The concurrency group ensures only one test run executes at a time to avoid channel-name collisions or conflicting state.

## Contributors

- [Seb Seager](https://github.com/sebseager) - original author
- [Gregor Kobilarov](https://github.com/g8rdier) - CSV export functionality and media file support

## License

This software is available under the [GPL](LICENSE).
