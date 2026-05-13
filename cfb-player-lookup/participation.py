import argparse
import logging
import os
from typing import Generator

from google.oauth2 import service_account
from googleapiclient.discovery import build
from selenium import webdriver
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
# TODO: separate .json file
URLS = {
    "b10": [
        "https://fightingillini.com/sports/football/schedule",
        "https://iuhoosiers.com/sports/football/schedule",
        "https://hawkeyesports.com/sports/football/schedule",
        "https://umterps.com/sports/football/schedule",
        "https://mgoblue.com/sports/football/schedule",
        "https://msuspartans.com/sports/football/schedule",
        "https://gophersports.com/sports/football/schedule",
        "https://huskers.com/sports/football/schedule",
        "https://nusports.com/sports/football/schedule",
        "https://ohiostatebuckeyes.com/sports/football/schedule",
        "https://goducks.com/sports/football/schedule",
        "https://gopsusports.com/sports/football/schedule",
        "https://purduesports.com/sports/football/schedule",
        "https://scarletknights.com/sports/football/schedule",
        "https://usctrojans.com/sports/football/schedule",
        "https://uclabruins.com/sports/football/schedule",
        "https://gohuskies.com/sports/football/schedule",
        "https://uwbadgers.com/sports/football/schedule"
    ],
    "sec": [
        "https://rolltide.com/sports/football/schedule",
        "https://arkansasrazorbacks.com/sport/m-footbl/schedule",
        "https://auburntigers.com/sports/football/schedule",
        "https://floridagators.com/sports/football/schedule/2025",
        "https://georgiadogs.com/sports/football/schedule/2025",
        "https://www.secsports.com/schedule/football/university-of-kentucky?view=season" # NOTE: kentucky requires scraping from https://www.secsports.com/
        "https://lsusports.net/sports/fb/schedule",
        "https://olemisssports.com/sports/football/schedule",
        "https://hailstate.com/sports/football/schedule",
        "https://mutigers.com/sports/football/schedule",
        "https://soonersports.com/sports/football/schedule",
        "https://gamecocksonline.com/sports/football/schedule",
        "https://utsports.com/sports/football/schedule",
        "https://texaslonghorns.com/sports/football/schedule",
        "https://12thman.com/sports/football/schedule",
        "https://vucommodores.com/sports/football/schedule"
    ],
    "b12": [
        "https://arizonawildcats.com/sports/football/schedule",
        "https://thesundevils.com/sports/football/schedule",
        "https://baylorbears.com/sports/football/schedule",
        "https://byucougars.com/sports/football/schedule",
        "https://ucfknights.com/sports/football/schedule",
        "https://gobearcats.com/sports/football/schedule",
        "https://cubuffs.com/sports/football/schedule",
        "https://uhcougars.com/sports/football/schedule",
        "https://cyclones.com/sports/football/schedule",
        "https://kuathletics.com/sports/football/schedule",
        "https://www.kstatesports.com/sports/football/schedule",
        "https://okstate.com/sports/football/schedule",
        "https://gofrogs.com/sports/football/schedule",
        "https://texastech.com/sports/football/schedule",
        "https://utahutes.com/sports/football/schedule",
        "https://wvusports.com/sports/football/schedule"
    ],
    "acc": [
        "https://bceagles.com/sports/football/schedule",
        "https://calbears.com/sports/football/schedule",
        "https://clemsontigers.com/sports/football/schedule",
        "https://goduke.com/sports/football/schedule",
        "https://seminoles.com/sports/football/schedule",
        "https://ramblinwreck.com/sports/m-footbl/schedule",
        "https://gocards.com/sports/football/schedule",
        "https://miamihurricanes.com/sports/football/schedule",
        "https://goheels.com/sports/football/schedule",
        "https://gopack.com/sports/football/schedule",
        "https://fightingirish.com/sports/football/schedule",
        "https://pittsburghpanthers.com/sports/football/schedule",
        "https://smumustangs.com/sports/football/schedule",
        "https://gostanford.com/sports/football/schedule",
        "https://cuse.com/sports/football/schedule",
        "https://virginiasports.com/sports/football/schedule",
        "https://hokiesports.com/sports/football/schedule",
        "https://godeacs.com/sports/football/schedule"
    ]
}

def main() -> None:
    parser = argparse.ArgumentParser(formatter_class=argparse.ArgumentDefaultsHelpFormatter)
    parser.add_argument("conference", choices=["b10", "sec", "b12", "acc"], help="conference to scrape college football participation from")
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
        # TODO: const
        wait = WebDriverWait(driver, 4)

        def _get_boxscore_urls(url: str) -> Generator[str, None, None]:
            driver.get(url)
            try:
                wait.until(EC.element_to_be_clickable((By.XPATH, """//button[contains(., "Reject")]"""))).click()
            except TimeoutException:
                pass
            
            yield from [
                boxscore.get_attribute("href")
                for boxscore in wait.until(EC.any_of(
                    EC.presence_of_all_elements_located((By.XPATH, """//a[normalize-space() = "Box Score"][not(@class = "c-scoreboard__media-link")]""")),
                    EC.presence_of_all_elements_located((By.XPATH, """//a[normalize-space() = "Stats"][@class = "schedule-event-links-content__link"]""")),
                    EC.presence_of_all_elements_located((By.XPATH, """//*[contains(@class, "s-game-card__status-time-and-score")][.//picture]/following-sibling::*//a[contains(@href, "game-center")]"""))
                ))
                if boxscore.is_displayed()
            ]
        
        @retry(**RETRY_KWARGS)
        def get_boxscore_urls(url: str) -> list[str]:
            return [*_get_boxscore_urls(url)]

        def _get_participation(url: str) -> Generator[dict[str, str], None, None]:
            driver.get(f"{url}#main-content")

            if "game-center/" in driver.current_url:
                url = wait.until(EC.presence_of_element_located((By.XPATH, """//a[normalize-space() = "Boxscore"]"""))).get_attribute("href")
                driver.get(url)

            try:
                status = wait.until(EC.any_of(
                    EC.presence_of_element_located((By.XPATH, """//*[@class = "boxscore-game-info-item__name"][normalize-space() = "Status"]/following-sibling::*[not(normalize-space() = "Neutral")]""")),
                    EC.presence_of_element_located((By.XPATH, """//*[@class = "game_info"]//*[normalize-space() = "Status"]/following-sibling::*[not(normalize-space() = "Neutral")]""")),
                    EC.presence_of_element_located((By.XPATH, """//*[@class = "boxscore-teams-info__score-divider"]""")),
                    EC.presence_of_element_located((By.XPATH, """//*[@class = "divider"]/span"""))
                )).get_attribute("innerText")
                assert status in ("Away", "Home", "at", "vs.")
            except TimeoutException:
                status = None

            try:
                while True:
                    wait.until(EC.any_of(
                        EC.frame_to_be_available_and_switch_to_it((By.XPATH, """//iframe[contains(@src, "boxscore/iframe/")]""")),
                        EC.frame_to_be_available_and_switch_to_it((By.XPATH, """//iframe[contains(@src, "wmt.games/")]""")),
                        EC.frame_to_be_available_and_switch_to_it((By.XPATH, """//iframe[@class = "iframe-container__iframe"]"""))
                    ))
            except TimeoutException:
                pass

            metadata = {
                "game": wait.until(EC.any_of(
                    EC.presence_of_element_located((By.XPATH, """//figcaption/*[self::h2 or self::h4]""")),
                    EC.presence_of_element_located((By.XPATH, """//h2[contains(@class, "s-common__header-title")]""")),
                    EC.presence_of_element_located((By.XPATH, """//h2[contains(@class, "roster-title__header")]""")),
                    EC.presence_of_element_located((By.XPATH, """//p[contains(@class, "title")]"""))
                )).get_attribute("innerText").replace("\n", " "),
                "date": wait.until(EC.any_of(
                    EC.presence_of_element_located((By.XPATH, """//dt[contains(., "Date")]/following-sibling::dd""")),
                    EC.presence_of_element_located((By.XPATH, """//*[contains(@class, "s-game-details__date")]""")),
                    EC.presence_of_element_located((By.XPATH, """//time""")),
                    EC.presence_of_element_located((By.XPATH, """//p[contains(@class, "heading")][normalize-space() = "Date"]/following-sibling::*"""))
                )).get_attribute("innerText")
            }
            driver.execute_script("arguments[0].click();", wait.until(EC.element_to_be_clickable((By.XPATH, """//*[self::a or self::button][normalize-space() = "Participation"]"""))))

            for player in wait.until(EC.any_of(
                EC.presence_of_all_elements_located((By.XPATH, """//section[@id = "starters"]//tbody[tr//a]/tr""")),
                EC.presence_of_all_elements_located((By.XPATH, """//tbody[tr//a]/tr""")),
                EC.presence_of_all_elements_located((By.XPATH, f"""
                    //*[normalize-space() = "Player Participation" or normalize-space() = "Starters"]/following-sibling::*/*[{({"Away": 1, "Home": 2, "at": 1, "vs.": 2}.get(status, -1))}]
                    //tbody/tr[not(normalize-space(*[1]) = "TM" or normalize-space(*[1]) = "No data")]
                """)),
                EC.presence_of_all_elements_located((By.XPATH, """//table[contains(.//th, "Kentucky")]/tbody/tr[not(normalize-space(*[1]) = "TM" or normalize-space(*[1]) = "No data")]""")) # NOTE: kentucky fix
            )):
                if "," in (full_name := player.find_element(By.XPATH, """*[2]""").get_attribute("innerText")):
                    last_name, first_name = [name.strip() for name in full_name.split(",", 1)]
                else:
                    first_name, last_name = [name.strip() for name in full_name.split(" ", 1)]
                
                yield {
                    **metadata,
                    "number": player.find_element(By.XPATH, """*[1]""").get_attribute("innerText").strip(),
                    "first_name": first_name,
                    "last_name": last_name
                }
        
        @retry(**RETRY_KWARGS)
        def get_participation(url: str) -> list[dict[str, str]]:
            return [*_get_participation(url)]
        
        sheets.spreadsheets().values().clear(spreadsheetId=args.spreadsheet_id, range=f"{args.sheet}!A2:E").execute()
        LOGGER.info("cleared %s", args.sheet)

        # TODO: acc
        for URL in URLS[args.conference]:
            for boxscore_url in get_boxscore_urls(URL):
                LOGGER.info("found %s", boxscore_url)
                response = sheets.spreadsheets().values().append(
                    spreadsheetId=args.spreadsheet_id,
                    range=f"{args.sheet}!A2",
                    valueInputOption="USER_ENTERED",
                    insertDataOption="OVERWRITE",
                    body={"values": [[*participation.values()] for participation in get_participation(boxscore_url)]}
                ).execute()
                LOGGER.info("updated %i rows in %s", response["updates"]["updatedRows"], args.sheet)

if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO)
    main()