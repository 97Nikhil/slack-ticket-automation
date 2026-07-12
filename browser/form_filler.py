# browser/form_filler.py

import time
from typing import Optional
from datetime import datetime

from selenium.webdriver.common.by import By
from selenium.webdriver.common.keys import Keys
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC
from selenium.webdriver.chrome.options import Options
from selenium.webdriver.chrome.service import Service
from selenium.common.exceptions import (
    TimeoutException,
    NoSuchElementException,
    ElementNotInteractableException
)
from selenium import webdriver
from webdriver_manager.chrome import ChromeDriverManager

from config import GOOGLE_FORM_URL, FORM_FIELDS
from models.ticket import Ticket
from database.db import Database


class FormFiller:
    """
    Uses Selenium to fill and submit the Google Form.

    Connects to your existing Chrome browser (same connection
    as AdminScraper), switches to the Google Form tab, fills
    every field, then waits for YOU to press Submit.

    After you press Submit, it marks the ticket as submitted
    in the database and moves to the next ticket.

    Usage:
        filler = FormFiller(driver)     # pass existing driver
        filler.process(ticket, db)      # fills form, waits for submit
    """

    WAIT_TIMEOUT = 15   # seconds to wait for elements


    def __init__(self, driver):
        """
        Takes the existing Selenium driver from AdminScraper.
        We reuse the same driver — same Chrome window,
        same session, same tabs.

        This is why AdminScraper and FormFiller share one driver
        instance created in main.py.
        """
        self.driver = driver
        self.form_tab = None
        self.db = Database()


    def _find_form_tab(self):
        """
        Finds the Google Form tab among all open Chrome tabs.
        Stores the window handle for switching later.
        """
        for handle in self.driver.window_handles:
            self.driver.switch_to.window(handle)
            if "docs.google.com/forms" in self.driver.current_url:
                self.form_tab = handle
                print("✅ Google Form tab found")
                return

        print("⚠️  Google Form tab not found")
        print(f"   Please open {GOOGLE_FORM_URL} in Chrome")


    def _switch_to_form(self):
        """
        Switches Selenium focus to the Google Form tab.
        Called before any form interaction.
        """
        if self.form_tab:
            self.driver.switch_to.window(self.form_tab)
        else:
            self._find_form_tab()


    def _wait_for_element(self, by: By, selector: str):
        """
        Waits for an element to be clickable before interacting.
        More reliable than time.sleep() — stops waiting the
        moment the element is ready.
        """
        wait = WebDriverWait(self.driver, self.WAIT_TIMEOUT)
        return wait.until(EC.element_to_be_clickable((by, selector)))


    def _refresh_form(self):
        """
        Refreshes the Google Form page before filling each ticket.
        This resets all fields to empty — critical when processing
        multiple tickets in one run.

        Without this, previous ticket's data might remain in fields.
        """
        self._switch_to_form()
        self.driver.refresh()
        time.sleep(3)   # wait for form to fully reload
        print("   🔄 Form refreshed")


    def _fill_text_field(self, entry_id: str, value: str):
        """
        Fills a text input or textarea field in Google Forms.

        Google Forms text fields are found by their entry ID
        which appears in the field's name attribute.

        entry_id example: "entry.123456789"
        """
        if not value:
            return

        try:
            field = self._wait_for_element(
                By.NAME, entry_id
            )
            field.clear()
            field.send_keys(str(value))

        except TimeoutException:
            print(f"   ⚠️  Text field not found: {entry_id}")
        except Exception as e:
            print(f"   ⚠️  Could not fill text field {entry_id}: {e}")


    def _fill_date_field(self, entry_id: str, date_str: str):
        """
        Fills a date field in Google Forms.

        Date fields are special — you can't just type in them
        normally. We need to:
        1. Click the field
        2. Clear it completely
        3. Type date in MM/DD/YYYY format (Google Forms format)

        date_str comes in as "2026-07-12" (YYYY-MM-DD)
        we convert to "07/12/2026" (MM/DD/YYYY)
        """
        if not date_str:
            return

        try:
            # Convert date format
            date_obj = datetime.strptime(date_str, "%Y-%m-%d")
            formatted = date_obj.strftime("%m/%d/%Y")

            field = self._wait_for_element(By.NAME, entry_id)
            field.click()

            # Select all existing text and delete it
            field.send_keys(Keys.CONTROL + "a")
            field.send_keys(Keys.DELETE)

            # Type the date
            field.send_keys(formatted)

        except TimeoutException:
            print(f"   ⚠️  Date field not found: {entry_id}")
        except Exception as e:
            print(f"   ⚠️  Could not fill date field {entry_id}: {e}")


    def _select_radio_button(self, option_text: str):
        """
        Clicks a radio button by its visible label text.

        Google Forms radio buttons look like:
        <div role="radio" data-value="Resolved">Resolved</div>

        We find the element whose text matches our value
        and click it.

        option_text must exactly match the form option text.
        """
        if not option_text:
            return

        try:
            # Find radio option by its exact text content
            radio = self._wait_for_element(
                By.XPATH,
                f"//div[@role='radio' and @data-value='{option_text}']"
            )
            radio.click()
            print(f"   ✅ Selected: {option_text}")

        except TimeoutException:
            # Try alternative selector — some forms use span text
            try:
                radio = self.driver.find_element(
                    By.XPATH,
                    f"//span[text()='{option_text}']/ancestor::div[@role='radio']"
                )
                radio.click()
                print(f"   ✅ Selected (alt): {option_text}")

            except NoSuchElementException:
                print(f"   ⚠️  Radio option not found: {option_text}")

        except Exception as e:
            print(f"   ⚠️  Could not select radio {option_text}: {e}")


    def _fill_all_fields(self, ticket: Ticket):
        """
        Fills every field in the Google Form with ticket data.

        Order matters — we fill top to bottom as they appear
        in the form to avoid any scroll issues.

        Each field type uses the appropriate fill method.
        """
        form_data = ticket.to_form_data()

        print("\n   📝 Filling form fields...")

        # ── Email ──────────────────────────────────────────
        # Google Forms auto-fills email if user is logged in
        # We skip this — it's handled by the form itself
        print(f"   ✓  Email: {form_data['email']} (auto-filled by Google)")

        # ── Date ───────────────────────────────────────────
        print(f"   ✓  Date: {form_data['date']}")
        self._fill_date_field(
            FORM_FIELDS["date"],
            form_data["date"]
        )
        time.sleep(0.5)

        # ── Brand Name ─────────────────────────────────────
        print(f"   ✓  Brand Name: {form_data['brand_name']}")
        self._fill_text_field(
            FORM_FIELDS["brand_name"],
            form_data["brand_name"]
        )
        time.sleep(0.5)

        # ── Store URL ──────────────────────────────────────
        print(f"   ✓  Store URL: {form_data['store_url']}")
        self._fill_text_field(
            FORM_FIELDS["store_url"],
            form_data["store_url"]
        )
        time.sleep(0.5)

        # ── Order Count ────────────────────────────────────
        print(f"   ✓  Order Count: {form_data['order_count']}")
        self._fill_text_field(
            FORM_FIELDS["order_count"],
            form_data["order_count"]
        )
        time.sleep(0.5)

        # ── Average Consumption ────────────────────────────
        print(f"   ✓  Avg Consumption: {form_data['average_consumption']}")
        self._fill_text_field(
            FORM_FIELDS["average_consumption"],
            form_data["average_consumption"]
        )
        time.sleep(0.5)

        # ── Query Type (radio button) ──────────────────────
        print(f"   ✓  Query Type: {form_data['query_type']}")
        self._select_radio_button(form_data["query_type"])
        time.sleep(0.5)

        # ── Status (radio button) ──────────────────────────
        print(f"   ✓  Status: {form_data['status']}")
        self._select_radio_button(form_data["status"])
        time.sleep(0.5)

        # ── Channel (radio button) ─────────────────────────
        print(f"   ✓  Channel: {form_data['channel']}")
        self._select_radio_button(form_data["channel"])
        time.sleep(0.5)

        # ── Priority (radio button) ────────────────────────
        print(f"   ✓  Priority: {form_data['priority']}")
        self._select_radio_button(form_data["priority"])
        time.sleep(0.5)

        # ── Aging (radio button) ───────────────────────────
        print(f"   ✓  Aging: {form_data['aging']}")
        self._select_radio_button(form_data["aging"])
        time.sleep(0.5)

        # ── Remarks ────────────────────────────────────────
        print(f"   ✓  Remarks: {form_data['remarks'][:60]}...")
        self._fill_text_field(
            FORM_FIELDS["remarks"],
            form_data["remarks"]
        )

        print("\n   ✅ All fields filled")


    def _wait_for_submission(self, ticket: Ticket) -> bool:
        """
        Waits for YOU to press the Submit button.

        How it detects submission:
        After you press Submit, Google Forms shows a
        confirmation page with text like "Your response has
        been recorded" — we watch for this text to appear.

        Returns True if submitted, False if timed out.

        Gives you 5 minutes per ticket to review and submit.
        """
        print("\n   ⏳ Waiting for you to press Submit...")
        print("   👆 Review the form and press Submit when ready")
        print("   ⏰ You have 5 minutes before this ticket is skipped\n")

        # Check every 2 seconds for up to 5 minutes
        max_wait = 300    # 5 minutes in seconds
        check_interval = 2
        elapsed = 0

        while elapsed < max_wait:
            try:
                # Google Forms shows this text after submission
                confirmation = self.driver.find_element(
                    By.XPATH,
                    "//*[contains(text(), 'Your response has been recorded') or "
                    "contains(text(), 'response was recorded')]"
                )
                if confirmation:
                    print("   ✅ Form submitted successfully!")
                    return True

            except NoSuchElementException:
                # Confirmation not found yet — still waiting
                pass

            time.sleep(check_interval)
            elapsed += check_interval

        print("   ⚠️  Timed out waiting for submission — ticket skipped")
        return False


    def process(self, ticket: Ticket, db: Database) -> bool:
        """
        Main method — processes one ticket through the form.

        Flow:
        1. Check ticket is ready for submission
        2. Switch to form tab
        3. Refresh form (clear previous data)
        4. Fill all fields
        5. Wait for you to press Submit
        6. Mark as submitted in database
        7. Return True/False for success

        Called from main.py for each ticket.
        """
        print(f"\n{'='*50}")
        print(f"📋 Opening form for ticket: {ticket.thread_ts}")
        print(f"   Store: {ticket.store_url}")
        print(f"{'='*50}")

        # ── Check readiness ────────────────────────────────
        if not ticket.is_ready_for_submission():
            print("   ⚠️  Ticket not ready — skipping form")
            return False

        # ── Switch to form tab ─────────────────────────────
        self._switch_to_form()

        # ── Refresh form ───────────────────────────────────
        self._refresh_form()

        # ── Fill all fields ────────────────────────────────
        try:
            self._fill_all_fields(ticket)
        except Exception as e:
            print(f"   ❌ Form filling failed: {e}")
            ticket.flag(f"Form filling error: {e}")
            return False

        # ── Wait for your submission ───────────────────────
        submitted = self._wait_for_submission(ticket)

        # ── Update database ────────────────────────────────
        if submitted:
            ticket.is_submitted = True
            db.mark_submitted(ticket.thread_ts)
            print(f"   💾 Database updated — ticket marked submitted")
            return True

        return False