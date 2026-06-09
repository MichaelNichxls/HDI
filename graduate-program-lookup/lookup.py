import argparse
import csv
import json
import logging
import os
import textwrap
from typing import Any
from urllib.parse import quote_plus

from google.oauth2 import service_account
from googleapiclient.discovery import build
from playwright.sync_api import BrowserContext, sync_playwright
from tenacity import retry, stop_after_attempt

LOGGER = logging.getLogger(__name__)
RESPONSE_FORMAT = {
    "sports_analytics": bool.__name__,
    "data_analytics": bool.__name__,
    "data_science": bool.__name__,
    "business_analytics": bool.__name__,
}


@retry(stop=stop_after_attempt(5), reraise=True)
def get_ai_search_result(context: BrowserContext, query: str, format: dict[str, Any]) -> dict[str, Any]:
    with context.new_page() as page:
        q = textwrap.dedent(f"""
            QUERY: {query}
            FORMAT: {json.dumps(format)}
            RESPONSE: JSON
        """)
        page.goto(f"https://google.com/search?q={quote_plus(q)}")
        page.wait_for_url("**/search?**", timeout=0)
        page.get_by_role("link", name="AI Mode").click()
        page.wait_for_url("**/search?**", timeout=0)
        return json.loads(page.locator("pre code").text_content())


def main() -> None:
    parser = argparse.ArgumentParser(formatter_class=argparse.ArgumentDefaultsHelpFormatter)
    # fmt: off
    parser.add_argument("-i", "--id", default=os.getenv("GOOGLE_SPREADSHEET_ID"), help="id of google spreadsheet; required if GOOGLE_SPREADSHEET_ID environment variable is not specified")
    parser.add_argument("-c", "--credentials", default="service_account.json", metavar="PATH", help="path of google service account json file")
    parser.add_argument("-r", "--range", default="Sheet1!A1", metavar="RANGE", help="range within google spreadsheet to write the data to")
    parser.add_argument("--clear", action="store_true", help="clears range within google spreadsheet before writing the data; ranges are specified via the '-r, --range' flag")
    # fmt: on
    args = parser.parse_args()

    credentials = service_account.Credentials.from_service_account_file(args.credentials, scopes=["https://www.googleapis.com/auth/spreadsheets"])
    sheets = build("sheets", "v4", credentials=credentials)

    if args.clear:
        clear = sheets.spreadsheets().values().clear(spreadsheetId=args.id, range=args.range).execute()
        LOGGER.info("cleared %s", clear["clearedRange"])

    with open("institutions.csv", encoding="utf-8-sig") as f:
        institutions = [*csv.DictReader(f)]

    with (
        sync_playwright() as p,
        p.chromium.launch(headless=False, args=["--disable-blink-features=AutomationControlled"]) as browser,
        browser.new_context() as context,
    ):
        context.set_default_timeout(10_000)
        for institution in institutions:
            result = get_ai_search_result(context, f"Does {institution['Institution']} contain a master's degree for: {', '.join(RESPONSE_FORMAT)}", RESPONSE_FORMAT)
            append = (
                sheets.spreadsheets()
                .values()
                .append(
                    spreadsheetId=args.id,
                    range=args.range,
                    valueInputOption="USER_ENTERED",
                    insertDataOption="OVERWRITE",
                    body={"values": [[institution["Institution"], *result.values()]]},
                )
                .execute()
            )
            LOGGER.info("updated %i rows in %s, %s", append["updates"]["updatedRows"], args.range, institution["Institution"])


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO)
    main()
