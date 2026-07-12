# extractors/admin_scraper.py

import time
import re
from typing import Optional
from datetime import datetime

from selenium import webdriver
from selenium.webdriver.common.by import By
from selenium.webdriver.common.keys import Keys
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC
from selenium.webdriver.chrome.options import Options
from selenium.webdriver.chrome.service import Service
from webdriver_manager.chrome import ChromeDriverManager
from selenium.common.exceptions import (
    TimeoutException,
    NoSuchElementException
)

from config import ADMIN_PANEL_URL
from models.ticket import Ticket


class AdminScraper:
    """
    Uses Selenium to connect to your already-open Chrome browser
    and scrape data from 3 tabs:

    Tab 1 — Admin Panel:
        Search store URL → scrape order count,
        install date, used amount

    Tab 2 — Store Page:
        Open store URL → scrape brand name

    Tab 3 — Google Form:
        Fill fields → wait for you to submit
        (handled by FormFiller, not this class)

    Usage:
        scraper = AdminScraper()
        scraper.connect()            # connects to your Chrome
        scraper.process(ticket)      # fills ticket fields
        scraper.disconnect()         # releases Chrome connection
    """

    # How long to wait for page elements before giving up (seconds)
    WAIT_TIMEOUT = 15


    def __init__(self):
        self.driver = None      # Selenium WebDriver instance
        self.admin_tab = None   # Window handle for admin panel tab
        self.store_tab = None   # Window handle for store URL tab


    def connect(self):
        """
        Connects Selenium to your already-open Chrome browser
        using remote debugging port 9222.

        This does NOT open a new Chrome window.
        It attaches to the Chrome you already have open.

        Call this once at the start of the script,
        before processing any tickets.
        """
        options = Options()

        # Tell Selenium to connect to existing Chrome
        # instead of opening a new one
        options.add_experimental_option(
            "debuggerAddress", "127.0.0.1:9222"
        )

        self.driver = webdriver.Chrome(
            service=Service(ChromeDriverManager().install()),
            options=options
        )
        print("✅ Connected to Chrome browser")

        # Find and store tab handles for admin panel
        self._identify_tabs()


    def _identify_tabs(self):
        """
        Loops through all open Chrome tabs and identifies
        which one is the admin panel.

        Stores the window handle so we can switch to it anytime.
        Window handles are like tab IDs in Selenium.
        """
        for handle in self.driver.window_handles:
            self.driver.switch_to.window(handle)
            current_url = self.driver.current_url

            if ADMIN_PANEL_URL.split("//")[1].split("/")[0] in current_url:
                self.admin_tab = handle
                print(f"✅ Admin panel tab found")

        if not self.admin_tab:
            print("⚠️  Admin panel tab not found")
            print(f"   Please open {ADMIN_PANEL_URL} in Chrome and run again")


    def _open_store_tab(self, store_url: str):
        """
        Opens the store URL in a new tab (or reuses existing).
        We reuse the same tab for every store — just navigate to new URL.
        This avoids opening 20+ tabs during a full day's run.
        """
        if self.store_tab:
            # Reuse existing store tab — just navigate to new URL
            self.driver.switch_to.window(self.store_tab)
            self.driver.get(store_url)
        else:
            # Open new tab for store URL
            self.driver.execute_script("window.open('');")
            # Switch to the newly opened tab (always the last handle)
            self.store_tab = self.driver.window_handles[-1]
            self.driver.switch_to.window(self.store_tab)
            self.driver.get(store_url)

        # Wait for page to load
        time.sleep(3)


    def _wait_for_element(self, by: By, selector: str) -> object:
        """
        Waits up to WAIT_TIMEOUT seconds for an element to appear.
        Much better than time.sleep() because it stops waiting
        the moment the element appears — faster and more reliable.

        Raises TimeoutException if element never appears.
        """
        wait = WebDriverWait(self.driver, self.WAIT_TIMEOUT)
        return wait.until(
            EC.presence_of_element_located((by, selector))
        )


    def _scrape_admin_panel(self, store_url: str) -> dict:
        """
        Searches for the store in admin panel and scrapes:
        - Order Count
        - Install Date
        - Used Amount

        Returns a dict with these values, or empty dict if failed.

        Looking at your admin panel screenshot:
        - Search dropdown is set to "Store URL"
        - There's an input field for the URL
        - Filter button submits the search
        - Results show in a table row under "Store Details"
        """
        result = {}

        try:
            # Switch to admin panel tab
            self.driver.switch_to.window(self.admin_tab)
            print(f"   🔍 Searching admin panel for: {store_url}")

            # Extract just the domain from full URL
            # https://myadira.myshopify.com → myadira.myshopify.com
            domain = store_url.replace("https://", "").replace("http://", "").rstrip("/")

            # ── Step 1: Make sure "Store URL" is selected in dropdown ──
            # Find the dropdown that switches between search types
            dropdown = self._wait_for_element(By.CSS_SELECTOR, "select")
            from selenium.webdriver.support.ui import Select
            select = Select(dropdown)
            select.select_by_visible_text("Store URL")

            # ── Step 2: Clear input and type store URL ──
            search_input = self._wait_for_element(
                By.CSS_SELECTOR, "input[type='text']"
            )
            search_input.clear()
            search_input.send_keys(domain)

            # ── Step 3: Click Filter button ──
            filter_button = self._wait_for_element(
                By.XPATH, "//button[contains(text(), 'Filter')]"
            )
            filter_button.click()

            # ── Step 4: Wait for results to load ──
            time.sleep(2)

            # ── Step 5: Scrape Store Details column ──
            # From your screenshot, store details are in a cell
            # containing text like:
            # "Order Count: 7640"
            # "Used Amount: $7327.74"
            # "Install Date: 2026-03-30"

            store_details = self._wait_for_element(
                By.XPATH,
                "//td[contains(@class, 'store-details') or .//text()[contains(., 'Order Count')]]"
            )

            details_text = store_details.text
            print(f"   📋 Raw details: {details_text}")

            # ── Step 6: Parse the scraped text ──
            # Extract Order Count
            order_match = re.search(r'Order Count[:\s]+([0-9,]+)', details_text)
            if order_match:
                # Remove commas from numbers like "7,640" → 7640
                result["order_count"] = int(order_match.group(1).replace(",", ""))

            # Extract Used Amount (remove $ and convert to float)
            used_match = re.search(r'Used Amount[:\s]+\$?([0-9,\.]+)', details_text)
            if used_match:
                result["used_amount"] = float(used_match.group(1).replace(",", ""))

            # Extract Install Date
            date_match = re.search(r'Install Date[:\s]+(\d{4}-\d{2}-\d{2})', details_text)
            if date_match:
                result["install_date"] = date_match.group(1)

            print(f"   ✅ Admin data: {result}")

        except TimeoutException:
            print(f"   ⚠️  Admin panel timeout — store may not exist in system")
        except Exception as e:
            print(f"   ⚠️  Admin panel scraping failed: {e}")

        return result


    def _scrape_brand_name(self, store_url: str) -> Optional[str]:
        """
        Opens the store URL in Tab 3 and scrapes the brand name
        from the page title or header.

        From your Koala Inspector screenshot, the brand name
        (e.g. "ADIRA") appears as the main store name.

        In the actual store HTML, this is usually in:
        - <title>Brand Name – Store tagline</title>
        - <h1> or <h2> in the header
        - meta og:site_name tag

        We try multiple selectors in order.
        """
        try:
            self._open_store_tab(store_url)
            print(f"   🔍 Scraping brand name from: {store_url}")

            # Strategy 1 — og:site_name meta tag
            # Most Shopify stores have this
            # <meta property="og:site_name" content="Adira">
            try:
                meta = self.driver.find_element(
                    By.XPATH,
                    "//meta[@property='og:site_name']"
                )
                brand = meta.get_attribute("content")
                if brand and len(brand) > 1:
                    print(f"   ✅ Brand from og:site_name: {brand}")
                    return brand.strip()
            except NoSuchElementException:
                pass

            # Strategy 2 — Page title
            # Usually "Brand Name | Store tagline"
            # We take everything before the first | or –
            title = self.driver.title
            if title:
                brand = re.split(r'[|–\-]', title)[0].strip()
                if brand and len(brand) > 1:
                    print(f"   ✅ Brand from page title: {brand}")
                    return brand

            # Strategy 3 — Header logo alt text
            # <img class="logo" alt="Brand Name">
            try:
                logo = self.driver.find_element(
                    By.XPATH,
                    "//img[contains(@class, 'logo') or contains(@alt, 'logo')]"
                )
                brand = logo.get_attribute("alt")
                if brand and len(brand) > 1:
                    print(f"   ✅ Brand from logo alt: {brand}")
                    return brand.strip()
            except NoSuchElementException:
                pass

            print("   ⚠️  Could not detect brand name from store page")
            return None

        except Exception as e:
            print(f"   ⚠️  Brand name scraping failed: {e}")
            return None


    def process(self, ticket: Ticket) -> Ticket:
        """
        Main method — processes one ticket.
        Fills: brand_name, order_count, install_date,
               used_amount, average_consumption, priority

        Called from main.py for each ticket after
        URL extraction is done.
        """
        if not ticket.store_url:
            ticket.flag("Cannot scrape admin panel — no store URL")
            return ticket

        # ── Scrape Admin Panel ──
        admin_data = self._scrape_admin_panel(ticket.store_url)

        if admin_data:
            ticket.order_count  = admin_data.get("order_count")
            ticket.install_date = admin_data.get("install_date")
            ticket.used_amount  = admin_data.get("used_amount")

            # Calculate derived fields
            ticket.calculate_average_consumption()
            ticket.calculate_priority()
        else:
            ticket.flag("Admin panel returned no data for this store URL")

        # ── Scrape Brand Name ──
        brand_name = self._scrape_brand_name(ticket.store_url)

        if brand_name:
            ticket.brand_name = brand_name
        else:
            ticket.flag("Could not detect brand name from store page")

        return ticket


    def disconnect(self):
        """
        Releases the Selenium connection to Chrome.
        Does NOT close Chrome — your browser stays open.
        Called once at the very end of the script.
        """
        if self.driver:
            self.driver.quit()
            print("✅ Selenium disconnected from Chrome")