#!/usr/bin/env python3
"""Convert JSON exports from exporter.py to CSV format.

Usage:
    python converter_to_csv.py <json_dir> [--user-list <user_list.json>]
"""

import json
import csv
import os
import argparse


def load_user_map(user_list_file):
    """Load user ID -> name mapping from an exporter.py user list JSON export."""
    with open(user_list_file, "r") as f:
        users = json.load(f)
    return {u["id"]: u.get("name", u["id"]) for u in users}


def replace_user_mentions(text, user_map):
    """Replace <@USER_ID> mentions with display names."""
    for user_id, name in user_map.items():
        text = text.replace(f"<@{user_id}>", f"@{name}")
    return text


def json_to_csv(json_file, csv_file, user_map):
    with open(json_file, "r") as f:
        data = json.load(f)

    channel = os.path.splitext(os.path.basename(json_file))[0]

    with open(csv_file, "w", newline="", encoding="utf-8") as f:
        writer = csv.writer(f)
        writer.writerow(["timestamp", "channel", "user", "text"])

        for msg in data:
            if msg.get("type") != "message":
                continue

            user_id = msg.get("user", "")
            user = user_map.get(user_id, user_id)
            text = replace_user_mentions(msg.get("text", ""), user_map)

            writer.writerow([msg.get("ts", ""), channel, user, text])


if __name__ == "__main__":
    parser = argparse.ArgumentParser(
        description="Convert JSON exports from exporter.py to CSV format"
    )
    parser.add_argument("json_dir", help="Directory containing JSON export files")
    parser.add_argument(
        "--user-list",
        help="Path to user list JSON file (from exporter.py --lu --json)",
    )
    args = parser.parse_args()

    user_map = load_user_map(args.user_list) if args.user_list else {}

    for filename in sorted(os.listdir(args.json_dir)):
        if not filename.endswith(".json"):
            continue
        json_path = os.path.join(args.json_dir, filename)
        csv_path = os.path.join(args.json_dir, filename.replace(".json", ".csv"))
        print(f"Converting {filename} to CSV...")
        json_to_csv(json_path, csv_path, user_map)

    print("Conversion complete!")
