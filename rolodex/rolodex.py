import argparse
import json
import logging
import os
import re
from typing import Generator
from urllib.parse import urlparse

from google.oauth2 import service_account
from googleapiclient.discovery import build
from selenium import webdriver
# TODO: all
from selenium.common.exceptions import ElementClickInterceptedException, StaleElementReferenceException, TimeoutException
from selenium.webdriver.common.by import By
from selenium.webdriver.support import expected_conditions as EC
from selenium.webdriver.support.wait import WebDriverWait
from tenacity import *

LOGGER = logging.getLogger(__name__)
RETRY_KWARGS = {
    "stop": stop_after_attempt(3),
    "retry": retry_if_exception_type((ElementClickInterceptedException, StaleElementReferenceException, TimeoutException)),
    "after": after_log(LOGGER, logging.ERROR),
    "reraise": True
}
REGEXES = {
    "name": re.compile(r"""
        ^.*?
        (?=$
            |\(.*\)
            |\[.*\]
            |'\d+
            |(?![IVX]+\b)[A-Z]{2,}
            |,\s+(?!Jr\.)
        )
    """, re.X),
    "email": re.compile(r"""
        [\w.%+-]+
        @[\w.-]+
        \.[a-zA-Z]{2,}
    """, re.X),
    "phone": re.compile(r"""
        (?:\+\d{1,2}\s?)?
        \(?\d{3}\)?[\s.-]?
        \d{3}[\s.-]?\d{4}
        (?:\s?(?:[Ee]xt[:.]?|[Xx])\s?\d{1,5})?
    """, re.X)
}
LOCATORS = {
    "mbb": [
        (By.XPATH, """//li[@data-v-63fd466b]"""), # NOTE: arizona state fix
        (By.XPATH, """//tbody[tr[1][count(td) = 1][contains(., "Men's Basketball") or contains(., "MEN'S BASKETBALL") or contains(., "Basketball (Men's)")]]/tr[position() > 1]"""),
        (By.XPATH, """//table[contains(thead, "Men's Basketball")]/tbody/tr"""),
        (By.XPATH, """//*[contains(., "Coaching Staff") or contains(., "Support Staff")]//following::table[1]/tbody/tr"""),
        (By.XPATH, """(//*[contains(text(), "Men's Basketball")]//following::table)[1]/tbody/tr""")
    ],
    "wbb": [
        (By.XPATH, """//li[@data-v-63fd466b]"""), # NOTE: arizona state fix
        (By.XPATH, """//tbody[tr[1][count(td) = 1][contains(., "Women's Basketball") or contains(., "WOMEN'S BASKETBALL") or contains(., "Basketball (Women's)")]]/tr[position() > 1]"""),
        (By.XPATH, """//table[contains(thead, "Women's Basketball")]/tbody/tr"""),
        (By.XPATH, """//*[contains(., "Coaching Staff") or contains(., "Support Staff")]//following::table[1]/tbody/tr"""),
        (By.XPATH, """(//h3[contains(text(), "Women's Basketball")]//following::table)[1]/tbody/tr"""), # NOTE: temp clemson fix
        (By.XPATH, """(//*[contains(text(), "Women's Basketball")]//following::table)[1]/tbody/tr""")
    ]
}

def main() -> None:
    parser = argparse.ArgumentParser(formatter_class=argparse.ArgumentDefaultsHelpFormatter)
    parser.add_argument("sport", choices=["mbb", "wbb"], help="sport to scrape college basketball contact information from")
    parser.add_argument("-a", "--service_account_file", default="service_account.json", help="path of google service account json file")
    parser.add_argument("-i", "--spreadsheet_id", default=os.getenv("GOOGLE_SPREADSHEET_ID"), help="id of google spreadsheet; required if GOOGLE_SPREADSHEET_ID environment variable is not specified")
    parser.add_argument("-s", "--sheet", default="Sheet1", help="name of google sheet to write the data to")

    args = parser.parse_args()

    credentials = service_account.Credentials.from_service_account_file(args.service_account_file, scopes=["https://www.googleapis.com/auth/spreadsheets"])
    sheets = build("sheets", "v4", credentials=credentials)

    options = webdriver.ChromeOptions()
    options.add_argument("--headless=new")
    options.add_argument("--window-size=1920,1080")
    options.add_argument("--log-level=3")

    with webdriver.Chrome(options) as driver:
        wait = WebDriverWait(driver, 4)

        with open("metadata.json") as file:
            metadata: dict = json.load(file)

        def _get_contacts(url: str) -> Generator[dict[str, str], None, None]:
            driver.get(url)
            
            for contact in wait.until(EC.any_of(*[EC.presence_of_all_elements_located(LOCATOR) for LOCATOR in LOCATORS[args.sport]])):
                if not (names := contact.find_elements(By.XPATH, """.//a[normalize-space()]""")):
                    continue

                # TODO: make config json file
                if not (positions := contact.find_elements(By.XPATH, f"""
                    *
                    [not(.//a)]
                    [not({" or ".join(
                        f"""contains(., "{pos}")"""
                        for pos in ["Student", "Team", "Graduate", "Equipment", "Social", "Creative", "Media", "Academic", "Nutrition"]
                    )})]
                    [{" or ".join(
                        f"""contains(., "{pos}")"""
                        for pos in ["Head", "Coach", "Associate", "Director", "Coordinator", "Manager", "Special", "Personnel", "President", "Chief", "Admin", "Recruiting", "Executive"]
                    )}]
                """)):
                    continue

                # TODO: run href and text through regex
                # TODO: TEST
                yield {
                    "name": names[0].get_attribute("innerText").strip(),
                    "position": positions[0].get_attribute("innerText").replace("\n", " ").strip(),
                    "phone": REGEXES["phone"].match(contact.get_attribute("innerText"))
                        or phones[0].get_attribute("href").removeprefix("tel:")
                            if (phones := contact.find_elements(By.XPATH, """.//a[contains(@href, "tel:")]"""))
                            else None,
                    "email": f"""=HYPERLINK("mailto:{email}", "{email}")"""
                        if (email := REGEXES["email"].match(contact.get_attribute("innerText")))
                        else f"""=HYPERLINK("{emails[0].get_attribute("href")}", "{emails[0].get_attribute("href").removeprefix("mailto:")}")"""
                            if (emails := contact.find_elements(By.XPATH, """.//a[contains(@href, "mailto:")]"""))
                            else None,
                    "twitter": f"""=HYPERLINK("{twitters[0].get_attribute("href")}", "@{urlparse(twitters[0].get_attribute("href")).path.lstrip("/@")}")"""
                        if (twitters := contact.find_elements(By.XPATH, """.//a[contains(@href, "twitter.com/") or contains(@href, "x.com/")]"""))
                        else None
                }

        @retry(**RETRY_KWARGS)
        def get_contacts(url: str) -> list[dict[str, str]]:
            return [*_get_contacts(url)]
        
        sheets.spreadsheets().values().clear(spreadsheetId=args.spreadsheet_id, range=f"{args.sheet}!A2:J").execute()
        LOGGER.info("cleared %s", args.sheet)

        # TODO: error handling
        # TODO: remove duplicates; notre dame
        # TODO: conference
        for data in metadata[args.sport]:
            LOGGER.info("found %s", data["url"])
            response = sheets.spreadsheets().values().append(
                spreadsheetId=args.spreadsheet_id,
                range=f"{args.sheet}!A2",
                valueInputOption="USER_ENTERED",
                insertDataOption="OVERWRITE",
                body={"values": [
                    [
                        f"""=HYPERLINK("{data["url"]}", "{data["team"]}")""",
                        data["conference"],
                        data["client"],
                        data["level"],
                        *contact.values()
                    ]
                    for contact in get_contacts(data["url"])
                ]}
            ).execute()
            LOGGER.info("updated %i rows in %s", response["updates"]["updatedRows"], args.sheet)

if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO)
    main()