import argparse
import logging
import os

from google.oauth2 import service_account
from googleapiclient.discovery import build
from selenium import webdriver
from selenium.webdriver.common.by import By
from selenium.webdriver.common.keys import Keys
from selenium.webdriver.support import expected_conditions as EC
from selenium.webdriver.support.wait import WebDriverWait

def main() -> None:
    parser = argparse.ArgumentParser(formatter_class=argparse.ArgumentDefaultsHelpFormatter)
    parser.add_argument("-a", "--service_account_file", default="service_account.json", help="path of google service account json file")
    parser.add_argument("-i", "--spreadsheet_id", default=os.getenv("GOOGLE_SPREADSHEET_ID"), help="id of google spreadsheet; required if GOOGLE_SPREADSHEET_ID environment variable is not specified")
    # parser.add_argument("-s", "--sheet", default="Sheet1", help="name of google sheet to write the data to")
    # TODO: driver wait arg

    args = parser.parse_args()

    credentials = service_account.Credentials.from_service_account_file(args.service_account_file, scopes=["https://www.googleapis.com/auth/spreadsheets"])
    sheets = build("sheets", "v4", credentials=credentials)

    options = webdriver.ChromeOptions()
    options.add_argument("--headless=new")
    options.add_argument("--window-size=1920,1080")
    options.add_argument("--log-level=3")

    teams = [
        value
        for value in sheets.spreadsheets().values().get(
            spreadsheetId=args.spreadsheet_id,
            range="Genius Names List!A2:A",
            majorDimension="COLUMNS"
        ).execute()["values"][0]
        if value not in {"Self Scout", "TBD (MTE)", "TBD"}
    ]

    with webdriver.Chrome(options) as driver:
        wait = WebDriverWait(driver, 10)

        for team in teams:
            driver.get("https://www.google.com")
            driver.find_element(By.NAME, "q").send_keys(f"{team} Men's Basketball Roster{Keys.RETURN}")
            # espn, nba, basketball.*, maxpreps
            # no / and /2025-26 at end
            # 2025-26 at middle of url replaced by {season}
            result = wait.until(EC.presence_of_element_located((By.CSS_SELECTOR, "div#search a:has(h3)")))
            print(result.get_attribute("href"))

if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO)
    main()