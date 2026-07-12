# database/db.py

import sqlite3
import json
from datetime import datetime
from typing import Optional
from models.ticket import Ticket, TicketStatus, TicketPriority


class Database:
    """
    Handles all SQLite operations for the project.

    Responsibilities:
    - Create tables on first run
    - Check if a ticket was already processed
    - Save new tickets
    - Update ticket after form submission
    - Fetch flagged tickets for review

    Usage:
        db = Database()
        db.setup()                          # creates tables if not exist
        db.is_processed("172345.000100")    # True or False
        db.save_ticket(ticket)              # saves to DB
        db.mark_submitted("172345.000100")  # updates after form submit
    """

    def __init__(self, db_path: str = "database/tickets.db"):
        """
        __init__ runs automatically when you do db = Database()
        db_path is where the SQLite file lives on your machine.
        """
        self.db_path = db_path


    def _connect(self):
        """
        Creates and returns a database connection.
        The underscore prefix means this is a private method —
        only used internally by other methods in this class.
        Not meant to be called from outside.
        """
        return sqlite3.connect(self.db_path)


    def setup(self):
        """
        Creates all tables if they don't exist yet.
        Safe to call every time the script runs —
        'CREATE TABLE IF NOT EXISTS' never overwrites existing data.
        """
        conn = self._connect()
        cursor = conn.cursor()

        # Main tickets table
        # Each row = one Slack thread = one ticket
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS tickets (

                -- Identity
                thread_ts       TEXT PRIMARY KEY,    -- Slack message ID, unique per ticket
                channel_id      TEXT,                -- Which Slack channel
                slack_url       TEXT,                -- Direct link to thread

                -- Raw content (stored as-is for future AI search)
                original_message    TEXT,
                thread_replies      TEXT,            -- stored as JSON string
                image_paths         TEXT,            -- stored as JSON string

                -- Extracted fields
                store_url       TEXT,
                date            TEXT,

                -- Admin panel fields
                brand_name          TEXT,
                order_count         INTEGER,
                install_date        TEXT,
                used_amount         REAL,
                average_consumption REAL,

                -- AI generated
                query_type      TEXT,
                remarks         TEXT,

                -- Status
                status          TEXT,
                status_source   TEXT,               -- "keyword", "gemini", or "manual"

                -- Form fields
                channel         TEXT,
                aging           TEXT,
                priority        TEXT,

                -- Processing metadata
                created_at          TEXT,
                is_submitted        INTEGER DEFAULT 0,   -- 0=False, 1=True (SQLite has no bool)
                needs_manual_review INTEGER DEFAULT 0,
                flag_reason         TEXT
            )
        """)

        # Flagged tickets view — makes it easy to query tickets needing attention
        # A VIEW is like a saved query — not a real table, just a shortcut
        cursor.execute("""
            CREATE VIEW IF NOT EXISTS flagged_tickets AS
            SELECT
                thread_ts,
                store_url,
                status,
                flag_reason,
                created_at
            FROM tickets
            WHERE needs_manual_review = 1
            AND   is_submitted = 0
        """)

        conn.commit()
        conn.close()
        print("✅ Database ready")


    def is_processed(self, thread_ts: str) -> bool:
        """
        Checks if a Slack thread was already processed.

        This is the key method that prevents double-processing.
        Called for every message before doing any work.

        Returns:
            True  → already in DB, skip this thread
            False → new thread, process it
        """
        conn = self._connect()
        cursor = conn.cursor()

        cursor.execute(
            "SELECT thread_ts FROM tickets WHERE thread_ts = ?",
            (thread_ts,)    # the comma makes it a tuple — required by sqlite3
        )

        result = cursor.fetchone()
        conn.close()

        return result is not None   # None means not found = not processed


    def save_ticket(self, ticket: Ticket):
        """
        Saves a Ticket object to the database.

        Called after the ticket is fully processed by Gemini
        but before form submission — so even if Selenium crashes,
        the ticket data is not lost.

        Lists (thread_replies, image_paths) are converted to
        JSON strings because SQLite can't store Python lists directly.
        """
        conn = self._connect()
        cursor = conn.cursor()

        try:
            cursor.execute("""
                INSERT OR REPLACE INTO tickets (
                    thread_ts, channel_id, slack_url,
                    original_message, thread_replies, image_paths,
                    store_url, date,
                    brand_name, order_count, install_date,
                    used_amount, average_consumption,
                    query_type, remarks,
                    status, status_source,
                    channel, aging, priority,
                    created_at, is_submitted,
                    needs_manual_review, flag_reason
                ) VALUES (
                    ?, ?, ?,
                    ?, ?, ?,
                    ?, ?,
                    ?, ?, ?,
                    ?, ?,
                    ?, ?,
                    ?, ?,
                    ?, ?, ?,
                    ?, ?,
                    ?, ?
                )
            """, (
                ticket.thread_ts,
                ticket.channel_id,
                ticket.slack_url,

                ticket.original_message,
                json.dumps(ticket.thread_replies),   # list → JSON string
                json.dumps(ticket.image_paths),      # list → JSON string

                ticket.store_url,
                ticket.date,

                ticket.brand_name,
                ticket.order_count,
                ticket.install_date,
                ticket.used_amount,
                ticket.average_consumption,

                ticket.query_type,
                ticket.remarks,

                ticket.status.value,                 # Enum → string
                ticket.status_source,

                ticket.channel.value,                # Enum → string
                ticket.aging.value,                  # Enum → string
                ticket.priority.value,               # Enum → string

                ticket.created_at,
                int(ticket.is_submitted),            # bool → 0 or 1

                int(ticket.needs_manual_review),     # bool → 0 or 1
                ticket.flag_reason,
            ))

            conn.commit()
            print(f"  💾 Ticket saved: {ticket.thread_ts}")

        except Exception as e:
            print(f"  ❌ Failed to save ticket {ticket.thread_ts}: {e}")

        finally:
            conn.close()   # always close connection even if error occurs


    def mark_submitted(self, thread_ts: str):
        """
        Updates is_submitted to True after you press
        the submit button on the Google Form.

        Called by the form filler after successful submission.
        """
        conn = self._connect()
        cursor = conn.cursor()

        cursor.execute(
            "UPDATE tickets SET is_submitted = 1 WHERE thread_ts = ?",
            (thread_ts,)
        )

        conn.commit()
        conn.close()
        print(f"  ✅ Ticket marked as submitted: {thread_ts}")


    def get_flagged_tickets(self) -> list:
        """
        Returns all tickets that need manual review.
        Printed at the end of the run so you know what to handle.
        """
        conn = self._connect()
        cursor = conn.cursor()

        cursor.execute("SELECT * FROM flagged_tickets")
        rows = cursor.fetchall()
        conn.close()

        return rows


    def get_unsubmitted_tickets(self) -> list:
        """
        Returns tickets that were processed but not yet submitted.
        Useful if Selenium crashed mid-run — these can be retried.
        """
        conn = self._connect()
        cursor = conn.cursor()

        cursor.execute("""
            SELECT thread_ts, store_url, query_type, status
            FROM tickets
            WHERE is_submitted = 0
            AND   needs_manual_review = 0
        """)

        rows = cursor.fetchall()
        conn.close()

        return rows


    def print_summary(self):
        """
        Prints a summary of today's processing at the end of the run.
        Shows submitted count, flagged count, pending count.
        """
        conn = self._connect()
        cursor = conn.cursor()

        today = datetime.now().strftime("%Y-%m-%d")

        cursor.execute(
            "SELECT COUNT(*) FROM tickets WHERE created_at LIKE ? AND is_submitted = 1",
            (f"{today}%",)
        )
        submitted = cursor.fetchone()[0]

        cursor.execute(
            "SELECT COUNT(*) FROM tickets WHERE created_at LIKE ? AND needs_manual_review = 1",
            (f"{today}%",)
        )
        flagged = cursor.fetchone()[0]

        cursor.execute(
            "SELECT COUNT(*) FROM tickets WHERE created_at LIKE ? AND is_submitted = 0 AND needs_manual_review = 0",
            (f"{today}%",)
        )
        pending = cursor.fetchone()[0]

        conn.close()

        print(f"""
{'='*50}
📊 Today's Summary ({today})
{'='*50}
  ✅ Submitted:        {submitted}
  ⚠️  Flagged:          {flagged}
  ⏳ Pending submit:   {pending}
{'='*50}
        """)

        # Print flagged tickets in detail
        flagged_rows = self.get_flagged_tickets()
        if flagged_rows:
            print("⚠️  Flagged Tickets (need manual review):")
            for row in flagged_rows:
                print(f"""
  Thread:     {row[0]}
  Store:      {row[1]}
  Status:     {row[2]}
  Reason:     {row[3]}
  Created:    {row[4]}
                """)