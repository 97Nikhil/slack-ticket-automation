# main.py

import sys
import time
from datetime import datetime

from config import validate_config, SLACK_CHANNEL_IDS
from models.ticket import Ticket, TicketStatus
from database.db import Database
from slack.reader import SlackReader
from extractors.url_extractor import URLExtractor
from extractors.admin_scraper import AdminScraper
from ai.gemini_processor import GeminiProcessor
from browser.form_filler import FormFiller


def print_banner():
    """
    Prints a startup banner so you know the script is running.
    Just cosmetic — makes terminal output easier to read.
    """
    print(f"""
╔══════════════════════════════════════════════════╗
║       ConvertWay Ticket Automation v1.0          ║
║       Phase 1 — Google Form Auto-Filler          ║
╚══════════════════════════════════════════════════╝
  Started at: {datetime.now().strftime("%Y-%m-%d %H:%M:%S")}
  Channels  : {len(SLACK_CHANNEL_IDS)} configured
""")


def print_ticket_summary(ticket: Ticket, index: int, total: int):
    """
    Prints a clean summary of one ticket before processing.
    Helps you track progress when multiple tickets run.
    """
    print(f"""
┌─────────────────────────────────────────────────┐
│  Ticket {index} of {total}
│  Thread  : {ticket.thread_ts}
│  Store   : {ticket.store_url or "Not detected yet"}
│  Replies : {len(ticket.thread_replies)}
│  Images  : {len(ticket.image_paths)}
└─────────────────────────────────────────────────┘""")


class AutomationPipeline:
    """
    The main pipeline that coordinates all components.

    Each component is initialized once and reused
    for all tickets — no reconnecting on every ticket.

    Flow per ticket:
    1. Check if already processed (database)
    2. Extract store URL (url_extractor)
    3. Scrape admin panel + brand name (admin_scraper)
    4. Process with Gemini (gemini_processor)
    5. Save to database (database)
    6. Fill and submit form (form_filler)
    """

    def __init__(self):
        """
        Initializes all components.
        Called once when script starts.
        """
        print("🔧 Initializing components...")

        # Database — check processed tickets, save new ones
        self.db = Database()
        self.db.setup()

        # Slack — fetch today's messages
        self.slack_reader = SlackReader()

        # URL extractor — regex to pull store URL
        self.url_extractor = URLExtractor()

        # Admin scraper — Selenium for admin panel + store page
        self.admin_scraper = AdminScraper()

        # Gemini — AI processing
        self.gemini = GeminiProcessor()

        # Form filler — initialized after Selenium connects
        # because it needs the driver from admin_scraper
        self.form_filler = None

        print("✅ All components ready\n")


    def connect_browser(self):
        """
        Connects Selenium to your existing Chrome browser.
        Also initializes FormFiller with the same driver.

        Called once at startup — before processing any tickets.

        IMPORTANT: Before running the script, make sure:
        1. Chrome is open with remote debugging port 9222
        2. Admin panel tab is open and logged in
        3. Google Form tab is open
        """
        print("🌐 Connecting to Chrome browser...")
        self.admin_scraper.connect()

        # FormFiller reuses the same Selenium driver
        # so both components share one Chrome connection
        self.form_filler = FormFiller(self.admin_scraper.driver)
        self.form_filler._find_form_tab()

        print("✅ Browser connected\n")


    def process_ticket(self, ticket: Ticket, index: int, total: int) -> bool:
        """
        Runs one ticket through the complete pipeline.

        Returns True if successfully submitted, False otherwise.
        Even if it returns False, the ticket is saved to DB
        so it won't be reprocessed next run.
        """
        print_ticket_summary(ticket, index, total)

        # ── Step 1: Extract Store URL ──────────────────────
        print("\n📍 Step 1: Extracting store URL...")
        ticket = self.url_extractor.process(ticket)

        if ticket.needs_manual_review:
            print(f"   ⚠️  Flagged: {ticket.flag_reason}")
            self.db.save_ticket(ticket)
            return False

        # ── Step 2: Scrape Admin Panel + Brand Name ────────
        print("\n🖥️  Step 2: Scraping admin panel...")
        ticket = self.admin_scraper.process(ticket)

        # Don't stop if admin scraping partially failed —
        # some fields might still be filled
        if ticket.needs_manual_review:
            print(f"   ⚠️  Warning: {ticket.flag_reason}")
            # Reset flag — we continue processing, just note the issue
            ticket.needs_manual_review = False
            flag_note = ticket.flag_reason
            ticket.flag_reason = None
        else:
            flag_note = None

        # ── Step 3: Gemini Processing ──────────────────────
        print("\n🤖 Step 3: Processing with Gemini AI...")
        ticket = self.gemini.process(ticket)

        # Restore flag note if admin scraping had issues
        if flag_note and not ticket.needs_manual_review:
            ticket.flag_reason = flag_note

        # ── Step 4: Save to Database ───────────────────────
        print("\n💾 Step 4: Saving to database...")
        self.db.save_ticket(ticket)

        # ── Step 5: Fill and Submit Form ───────────────────
        print("\n📋 Step 5: Opening Google Form...")

        if ticket.needs_manual_review:
            print(f"   ⚠️  Ticket flagged — skipping form submission")
            print(f"   Reason: {ticket.flag_reason}")
            return False

        submitted = self.form_filler.process(ticket, self.db)

        if submitted:
            print(f"\n   🎉 Ticket complete: {ticket.thread_ts}")
        else:
            print(f"\n   ⚠️  Ticket not submitted: {ticket.thread_ts}")

        return submitted


    def run(self):
        """
        Main run method — the full end-to-end flow.

        1. Validate config (check no missing credentials)
        2. Connect to Chrome
        3. Fetch today's Slack tickets
        4. Filter out already processed ones
        5. Process each new ticket
        6. Print final summary
        """

        # ── Validate config ────────────────────────────────
        print("🔍 Validating configuration...")
        try:
            validate_config()
            print("✅ Config valid\n")
        except ValueError as e:
            print(f"❌ Config error: {e}")
            sys.exit(1)   # stop script if config is broken

        # ── Connect browser ────────────────────────────────
        self.connect_browser()

        # ── Fetch today's tickets from Slack ───────────────
        print("📡 Fetching today's Slack messages...")
        all_tickets = self.slack_reader.get_today_tickets()

        if not all_tickets:
            print("\n✅ No new messages found today. All done!")
            self.db.print_summary()
            return

        # ── Filter already processed tickets ───────────────
        new_tickets = []
        skipped = 0

        for ticket in all_tickets:
            if self.db.is_processed(ticket.thread_ts):
                print(f"   ⏭️  Already processed: {ticket.thread_ts} — skipping")
                skipped += 1
            else:
                new_tickets.append(ticket)

        print(f"\n📊 {len(all_tickets)} total | "
              f"{skipped} already processed | "
              f"{len(new_tickets)} new to process\n")

        if not new_tickets:
            print("✅ All tickets already processed. Nothing new to do!")
            self.db.print_summary()
            return

        # ── Process each new ticket ────────────────────────
        submitted_count = 0
        flagged_count   = 0

        for index, ticket in enumerate(new_tickets, start=1):

            try:
                success = self.process_ticket(ticket, index, len(new_tickets))

                if success:
                    submitted_count += 1
                elif ticket.needs_manual_review:
                    flagged_count += 1

            except KeyboardInterrupt:
                # If you press Ctrl+C during processing
                print("\n\n⚠️  Script interrupted by user")
                print("   Progress saved to database")
                print("   Run again to continue from where you left off")
                break

            except Exception as e:
                # Unexpected error on one ticket — log it and continue
                # Never let one bad ticket crash the whole run
                print(f"\n❌ Unexpected error on ticket {ticket.thread_ts}: {e}")
                print("   Saving ticket as flagged and continuing...")
                ticket.flag(f"Unexpected error: {e}")
                self.db.save_ticket(ticket)
                flagged_count += 1
                continue

            # Small pause between tickets so Chrome doesn't feel rushed
            if index < len(new_tickets):
                print("\n⏸️  Pausing 2 seconds before next ticket...")
                time.sleep(2)

        # ── Final summary ──────────────────────────────────
        self.db.print_summary()

        print(f"""
╔══════════════════════════════════════════════════╗
║  Run Complete
║  ✅ Submitted : {submitted_count}
║  ⚠️  Flagged   : {flagged_count}
║  ⏭️  Skipped   : {skipped}
╚══════════════════════════════════════════════════╝
        """)

        # ── Disconnect browser ─────────────────────────────
        self.admin_scraper.disconnect()


# ── Entry Point ────────────────────────────────────────────
# This block only runs when you execute: python main.py
# It does NOT run if this file is imported by another file

if __name__ == "__main__":
    print_banner()
    pipeline = AutomationPipeline()
    pipeline.run()