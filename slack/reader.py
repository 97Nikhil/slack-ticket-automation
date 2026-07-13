# slack/reader.py

import os
import re
import requests
from typing import Optional
from datetime import datetime
from slack_sdk import WebClient
from slack_sdk.errors import SlackApiError

from config import SLACK_TOKEN, SLACK_CHANNEL_IDS
from models.ticket import Ticket


class SlackReader:
    """
    Handles all communication with the Slack API.

    Responsibilities:
    - Connect to Slack using bot token
    - Fetch today's messages from 2 channels
    - Fetch thread replies for each message
    - Download images/screenshots from threads
    - Create a Ticket object for each thread

    Usage:
        reader = SlackReader()
        tickets = reader.get_today_tickets()
    """

    def __init__(self):
        """
        Initializes the Slack client with your bot token.
        Also creates a folder to store downloaded images.
        """
        self.client = WebClient(token=SLACK_TOKEN)

        # Folder where screenshots will be saved locally
        self.image_folder = "downloads/images"
        os.makedirs(self.image_folder, exist_ok=True)
        # exist_ok=True means don't crash if folder already exists


    def _get_today_start_timestamp(self) -> str:
        """
        Returns today's midnight as a Unix timestamp string.
        Slack API uses Unix timestamps to filter messages by time.

        Example:
            Today is 2026-07-12
            Returns "1752278400.0" (midnight of that day)

        The underscore prefix means private — only used internally.
        """
        today = datetime.now().replace(
            hour=0, minute=0, second=0, microsecond=0
        )
        return str(today.timestamp())


    def _is_bot_message(self, message: dict) -> bool:
        """
        Checks if a message was sent by a bot (not a real person).
        We skip bot messages — they're not real tickets.

        Slack marks bot messages with a "subtype" or "bot_id" field.
        """
        return (
            message.get("subtype") is not None or
            message.get("bot_id") is not None
        )


    def _extract_text(self, message: dict) -> str:
        """
        Extracts clean text from a Slack message dictionary.
        Slack sometimes puts text in different places depending
        on message type — this handles all cases.
        """
        # Standard text field
        text = message.get("text", "")

        # Sometimes Slack puts content in "blocks" (rich text format)
        # We extract text from blocks if main text is empty
        if not text and "blocks" in message:
            for block in message["blocks"]:
                if block.get("type") == "rich_text":
                    for element in block.get("elements", []):
                        for item in element.get("elements", []):
                            if item.get("type") == "text":
                                text += item.get("text", "")

        return text.strip()


    def _download_image(self, file_info: dict, thread_ts: str) -> Optional[str]:
        """
        Downloads an image from Slack and saves it locally.

        Slack images need your bot token to download —
        they're not publicly accessible URLs.

        Returns the local file path, or None if download failed.
        """
        try:
            # Get the download URL from file info
            url = file_info.get("url_private_download")
            if not url:
                return None

            # Only download actual images, skip other file types
            mimetype = file_info.get("mimetype", "")
            if not mimetype.startswith("image/"):
                return None

            # Create a unique filename using thread_ts + original name
            filename  = file_info.get("name", "image.png")
            safe_name = f"{thread_ts}_{filename}".replace("/", "_")
            filepath  = os.path.join(self.image_folder, safe_name)

            # Skip if already downloaded (script ran before)
            if os.path.exists(filepath):
                return filepath

            # Download with auth header — Slack requires your token
            response = requests.get(
                url,
                headers={"Authorization": f"Bearer {SLACK_TOKEN}"},
                timeout=30
            )

            if response.status_code == 200:
                with open(filepath, "wb") as f:
                    f.write(response.content)
                return filepath

        except Exception as e:
            print(f"    ⚠️  Image download failed: {e}")

        return None


    def _get_thread_replies(self, channel_id: str, thread_ts: str) -> list:
        """
        Fetches all replies in a message thread.

        Returns a list of reply texts (strings only, no images).
        Images in replies are also downloaded.

        thread_ts is both the timestamp AND the unique ID
        of the parent message in Slack.
        """
        replies_text = []

        try:
            response = self.client.conversations_replies(
                channel=channel_id,
                ts=thread_ts
            )

            messages = response["messages"]

            # messages[0] is always the parent message — skip it
            # messages[1:] are the actual replies
            for reply in messages[1:]:
                text = self._extract_text(reply)
                if text:
                    replies_text.append(text)

        except SlackApiError as e:
            # Thread might have no replies — that's normal, not an error
            if e.response["error"] != "thread_not_found":
                print(f"    ⚠️  Could not fetch replies: {e.response['error']}")

        return replies_text


    def _get_images_from_message(self, message: dict, thread_ts: str) -> list:
        """
        Extracts and downloads all images from a message.
        Also fetches images from thread replies.

        Slack stores file attachments in message["files"] list.
        Each file has metadata including the download URL.

        Returns list of local file paths.
        """
        image_paths = []

        # Images in the parent message
        files = message.get("files", [])
        for file_info in files:
            path = self._download_image(file_info, thread_ts)
            if path:
                image_paths.append(path)
                print(f"    📸 Image downloaded: {path}")

        return image_paths


    def _build_slack_url(self, channel_id: str, thread_ts: str) -> str:
        """
        Builds a direct URL to the Slack thread.
        Useful for clicking directly to the thread from your terminal output.

        Format: https://app.slack.com/client/WORKSPACE_ID/CHANNEL_ID/p1234567890
        The thread_ts has a dot that needs to be removed for the URL.
        """
        ts_clean = thread_ts.replace(".", "")
        return f"https://app.slack.com/client/{channel_id}/p{ts_clean}"


    def get_today_tickets(self) -> list[Ticket]:
        """
        Main method — fetches all today's messages from both channels
        and returns a list of Ticket objects ready for processing.

        This is the only method called from outside this class.

        Flow:
        1. Loop through 2 channels
        2. Fetch messages sent after midnight today
        3. Skip bot messages
        4. For each real message → fetch replies + images
        5. Create a Ticket object
        6. Return list of all tickets
        """
        all_tickets = []
        today_start = self._get_today_start_timestamp()

        for channel_id in SLACK_CHANNEL_IDS:
            print(f"\n📡 Reading channel: {channel_id}")

            try:
                # Fetch messages from this channel since midnight
                response = self.client.conversations_history(
                    channel=channel_id,
                    oldest=today_start,    # only today's messages
                    limit=200              # max 200 messages per call
                )

                messages = response.get("messages", [])
                print(f"   Found {len(messages)} messages today")

                for message in messages:

                    # Skip bot messages
                    if self._is_bot_message(message):
                        continue

                    # Skip messages with no text
                    text = self._extract_text(message)
                    if not text:
                        continue

                    thread_ts = message["ts"]

                    print(f"\n   Processing thread: {thread_ts}")

                    # Fetch thread replies
                    replies = self._get_thread_replies(channel_id, thread_ts)
                    print(f"   Found {len(replies)} replies in thread")

                    # Download images from message
                    image_paths = self._get_images_from_message(message, thread_ts)

                    # Also get images from replies
                    # (sometimes screenshots are posted in replies)
                    try:
                        reply_response = self.client.conversations_replies(
                            channel=channel_id,
                            ts=thread_ts
                        )
                        for reply in reply_response["messages"][1:]:
                            reply_images = self._get_images_from_message(reply, thread_ts)
                            image_paths.extend(reply_images)
                    except SlackApiError:
                        pass

                    # Build Slack URL for this thread
                    slack_url = self._build_slack_url(channel_id, thread_ts)

                    # Create Ticket object with everything we have so far
                    # Other fields (brand_name, query_type etc) filled later
                    ticket = Ticket(
                        thread_ts=thread_ts,
                        channel_id=channel_id,
                        slack_url=slack_url,
                        original_message=text,
                        thread_replies=replies,
                        image_paths=image_paths,
                        date=datetime.now().strftime("%Y-%m-%d"),
                    )

                    all_tickets.append(ticket)
                    print(f"   ✅ Ticket created: {thread_ts}")

            except SlackApiError as e:
                print(f"❌ Error reading channel {channel_id}: {e.response['error']}")

        print(f"\n📋 Total tickets fetched today: {len(all_tickets)}")
        return all_tickets