# TODO: remove stubs, add typings
# TODO: EAFP
# TODO: eager loading
# TODO: less empty lines
# TODO: visibility vs presence
# TODO: _get_*()
# TODO: normalize null check
# TODO: incognito and args
# TODO: no RE
# TODO: configurable consts
# TODO: less blank lines
# TODO: option label in launch
# TODO: no more body={} shenanigans

import argparse
from contextlib import contextmanager
from datetime import datetime
from itertools import groupby
import logging
import os
import re
from typing import Any, Generator

from google.oauth2 import service_account
from googleapiclient.discovery import build
from selenium import webdriver
from selenium.common.exceptions import TimeoutException
from selenium.webdriver.common.by import By
from selenium.webdriver.remote.webdriver import WebDriver
from selenium.webdriver.support import expected_conditions as EC
from selenium.webdriver.support.wait import WebDriverWait

LOGGER = logging.getLogger(__name__)
NOW = datetime.now()
TEAMS = {
    "sec": (
        "Alabama",
        "Arkansas",
        "Auburn",
        "Florida",
        "Georgia",
        "Kentucky",
        "LSU",
        "Ole Miss",
        "Mississippi State",
        "Missouri",
        "Oklahoma",
        "South Carolina",
        "Tennessee",
        "Texas",
        "Texas A&M",
        "Vanderbilt"
    ),
    "acc": (
        "Boston College",
        "California",
        "Clemson",
        "Duke",
        "Florida State",
        "Georgia Tech",
        "Louisville",
        "Miami",
        "North Carolina",
        "NC State",
        "Notre Dame",
        "Pitt",
        "Stanford",
        "Virginia",
        "Virginia Tech",
        "Wake Forest"
    )
}
SERIES = {
    "sec": datetime(NOW.year, 3, 13),
    "acc": datetime(NOW.year, 3, 6)
}
STATS = {
    "batting": (
        "ab",
        "r",
        "h",
        "rbi",
        "bb",
        "so",
        "lob"
    ),
    "pitching": (
        "ip",
        "h",
        "r",
        "er",
        "bb",
        "so",
        "wp",
        "bk",
        "hbp",
        "ibb",
        "ab",
        "bf",
        "fo",
        "go",
        "np"
    )
}
RE = {
    "parens": re.compile(r"\([^)]*\)"),
    "number": re.compile(r"#?\d{1,2}"),
    "last_first": re.compile(r"(\b.*),\s*(.*\b)")
}

def normalize(str_: str) -> str:
    str_ = RE["parens"].sub("", str_)
    str_ = RE["number"].sub("", str_)
    str_ = RE["last_first"].sub(r"\2 \1", str_)
    return str_.replace("\n", " ").strip().title()

@contextmanager
def temp_tab(driver: WebDriver, url: str) -> Generator[None, None, None]:
    current_window = driver.current_window_handle
    driver.switch_to.new_window("tab")
    driver.get(url)
    try:
        yield
    finally:
        driver.close()
        driver.switch_to.window(current_window)

def get_boxscore_metadata(driver: WebDriver, conference: str) -> Generator[dict[str, Any], None, None]:
    wait = WebDriverWait(driver, 5)
    
    if conference == "sec":
        LOGGER.info("goto %s", "https://www.secsports.com/schedule/baseball?view=season")
        driver.get("https://www.secsports.com/schedule/baseball?view=season")

        while True:
            try:
                wait.until(EC.element_to_be_clickable((By.CLASS_NAME, "schedule-list__load_more__button"))).click()
            except TimeoutException:
                break

        for game in wait.until(EC.presence_of_all_elements_located((By.CSS_SELECTOR, "table.schedule-event-table__table tbody > tr"))):
            matchup = (
                normalize(game.find_element(By.CSS_SELECTOR, "td.schedule-event-cell--firstTeam .schedule-event-opponent__name").text),
                normalize(game.find_element(By.CSS_SELECTOR, "td.schedule-event-cell--secondTeam .schedule-event-opponent__name").text)
            )
            date = datetime.strptime(f"{game.find_element(By.CSS_SELECTOR, "td.schedule-event-cell--results_time span:not([class])").text}, {NOW.year}", "%a., %b. %d, %Y")
            url = boxscore[0].get_attribute("href") if (boxscore := game.find_elements(By.PARTIAL_LINK_TEXT, "Stats")) else None
            series = ((date - SERIES[conference]).days + 1) // 7 + 1
            yield {
                "conference": conference,
                "matchup": matchup,
                "date": date,
                "url": url,
                "series": series
            }
    elif conference == "acc":
        LOGGER.info("goto %s", "https://theacc.com/calendar.aspx?path=baseball")
        driver.get("https://theacc.com/calendar.aspx?path=baseball")

        for calendar in wait.until(EC.presence_of_all_elements_located((By.CSS_SELECTOR, "table.sidearm-calendar-table"))):
            for game in calendar.find_elements(By.CSS_SELECTOR, "tbody > tr"):
                matchup = (
                    normalize(game.find_element(By.CSS_SELECTOR, "td.sidearm-team-away .sidearm-calendar-list-group-list-game-team-title").text),
                    normalize(game.find_element(By.CSS_SELECTOR, "td.sidearm-team-home .sidearm-calendar-list-group-list-game-team-title").text)
                )
                date = datetime.strptime(calendar.find_element(By.CSS_SELECTOR, "caption span.sidearm-calendar-list-group-heading-date:not([aria-hidden])").text, "%A, %B %d, %Y")
                url = boxscore[0].get_attribute("href") if (boxscore := game.find_elements(By.LINK_TEXT, "Box Score")) else None
                series = ((date - SERIES[conference]).days + 1) // 7 + 1
                yield {
                    "conference": conference,
                    "matchup": matchup,
                    "date": date,
                    "url": url,
                    "series": series
                }

def get_boxscore_from_metadata(driver: WebDriver, metadata: dict[str, Any]) -> Generator[dict[str, str], None, None]:
    wait = WebDriverWait(driver, 5)

    with temp_tab(driver, metadata["url"]):
        LOGGER.info("goto %s", metadata["url"])
        
        if metadata["conference"] == "sec":
            wait.until(EC.frame_to_be_available_and_switch_to_it((By.CLASS_NAME, "iframe-container__iframe")))
            wait.until(EC.frame_to_be_available_and_switch_to_it((By.ID, "boxscore")))

            game = normalize(wait.until(EC.presence_of_element_located((By.CSS_SELECTOR, "h2.roster-title__header:has(.roster-title__content)"))).text)
            date = datetime.strftime(metadata["date"], "%m/%d/%Y")

            for batting in wait.until(EC.presence_of_all_elements_located((By.XPATH, "//*[normalize-space()='Hitting']/following-sibling::*[1]//table"))):
                team = normalize(batting.find_element(By.XPATH, "thead/tr[1]/th[last()]").text)

                for player in batting.find_elements(By.XPATH, "tbody/tr[normalize-space(td[1])!='P']"):
                    data = player.find_elements(By.TAG_NAME, "td")
                    name = normalize(data[1].text)
                    position = data[0].text
                    yield {
                        "game": game,
                        "date": date,
                        "team": team,
                        "player": name,
                        "position": position,
                        **{s: data[i].text for i, s in enumerate(STATS["batting"], 2)}
                    }
            for pitching in wait.until(EC.presence_of_all_elements_located((By.XPATH, "//*[normalize-space()='Pitching']/following-sibling::*[1]//table"))):
                team = normalize(pitching.find_element(By.XPATH, "thead/tr[1]/th[last()]").text)

                for player in pitching.find_elements(By.XPATH, "tbody/tr"):
                    data = player.find_elements(By.TAG_NAME, "td")
                    name = normalize(data[0].text)
                    yield {
                        "game": game,
                        "date": date,
                        "team": team,
                        "player": name,
                        "position": "P",
                        **{s: data[i].text for i, s in enumerate(STATS["pitching"], 1)}
                    }
        elif metadata["conference"] == "acc":
            game = normalize(wait.until(EC.presence_of_element_located((By.CSS_SELECTOR, "header.sidearm-box-score-header h3"))).text)
            date = datetime.strftime(metadata["date"], "%m/%d/%Y")

            for batting in wait.until(EC.presence_of_all_elements_located((By.XPATH, "//h3[normalize-space()='Batting']/following-sibling::*//table"))):
                team = normalize(batting.find_element(By.TAG_NAME, "caption").text)

                for player in batting.find_elements(By.XPATH, "tbody/tr[normalize-space(td[1])!='p']"):
                    data = player.find_elements(By.TAG_NAME, "td")
                    name = normalize(player.find_element(By.TAG_NAME, "th").text)
                    position = data[0].text
                    yield {
                        "game": game,
                        "date": date,
                        "team": team,
                        "player": name,
                        "position": position,
                        **{s: data[i].text for i, s in enumerate(STATS["batting"], 1)}
                    }
            for pitching in wait.until(EC.presence_of_all_elements_located((By.XPATH, "//h3[normalize-space()='Pitching']/following::table[position()<=2]"))):
                team = normalize(pitching.find_element(By.TAG_NAME, "caption").text)

                for player in pitching.find_elements(By.XPATH, "tbody/tr"):
                    data = player.find_elements(By.TAG_NAME, "td")
                    name = normalize(player.find_element(By.TAG_NAME, "th").text)
                    yield {
                        "game": game,
                        "date": date,
                        "team": team,
                        "player": name,
                        "position": "P",
                        **{s: data[i].text for i, s in enumerate(STATS["pitching"])}
                    }

# FIXME: stale ref edge case
def main() -> None:
    parser = argparse.ArgumentParser(formatter_class=argparse.ArgumentDefaultsHelpFormatter)
    parser.add_argument("conference", choices=["sec", "acc"], help="conference to scrape college baseball boxscores from")
    parser.add_argument("-i", "--id", default=os.getenv("GOOGLE_SPREADSHEET_ID"), help="id of google spreadsheet; required if GOOGLE_SPREADSHEET_ID environment variable is not specified")
    parser.add_argument("-c", "--credentials", default="service_account.json", metavar="PATH", help="path of google service account json file")
    parser.add_argument("-r", "--ranges", nargs=2, default=["Sheet1!A1", "Sheet2!A1"], metavar="RANGE", help="ranges within google spreadsheet to write the data to; first range is for batting data, second range is for pitching data")
    parser.add_argument("--clear", action="store_true", help="clears ranges within google spreadsheet before writing the data; ranges are specified via the '-r, --ranges' flag")
    args = parser.parse_args()

    credentials = service_account.Credentials.from_service_account_file(args.credentials, scopes=["https://www.googleapis.com/auth/spreadsheets"])
    sheets = build("sheets", "v4", credentials=credentials)

    if args.clear:
        response = sheets.spreadsheets().values().batchClear(
            spreadsheetId=args.id,
            body={"ranges": [args.ranges[0], args.ranges[1]]}
        ).execute()
        LOGGER.info("cleared %i rows in %s and %s", response["updates"]["updatedRows"], args.ranges[0], args.ranges[1])

    options = webdriver.ChromeOptions()
    options.add_argument("--headless=new")
    options.add_argument("--window-size=1920,1080")

    with webdriver.Chrome(options) as driver:
        for series, metadata_by_series in groupby(get_boxscore_metadata(driver, args.conference), key=lambda m: m["series"]):
            if series not in range(1, 11):
                continue
            
            metadata_by_series = [
                m
                for m in metadata_by_series
                if m["matchup"][0] in TEAMS[args.conference]
                    and m["matchup"][1] in TEAMS[args.conference]
                    and m["date"] <= NOW
                    and m["url"]
            ]
            assert metadata_by_series
            metadata_by_series.sort(key=lambda m: (m["matchup"], m["date"]))
            
            for _, metadata_by_matchup in groupby(metadata_by_series, key=lambda m: m["matchup"]):
                for i, m in enumerate(metadata_by_matchup, 1):
                    m["game"] = i
            
            for metadata in metadata_by_series:
                for batter, boxscore_by_position in groupby(get_boxscore_from_metadata(driver, metadata), key=lambda b: b["position"] != "P"):
                    if batter:
                        response = sheets.spreadsheets().values().append(
                            spreadsheetId=args.id,
                            range=args.ranges[0],
                            valueInputOption="USER_ENTERED",
                            insertDataOption="OVERWRITE",
                            body={"values": [
                                [
                                    f"""=HYPERLINK("{metadata["url"]}", "{boxscore["game"]}")""",
                                    *[*boxscore.values()][1:4],
                                    f"{boxscore["player"]}{metadata["series"]}{metadata["game"]}",
                                    boxscore["ab"],
                                    *[*metadata.values()][4:6]
                                ]
                                for boxscore in boxscore_by_position
                            ]}
                        ).execute()
                        LOGGER.info("updated %i rows in %s", response["updates"]["updatedRows"], args.ranges[0])
                    else:
                        response = sheets.spreadsheets().values().append(
                            spreadsheetId=args.id,
                            range=args.ranges[1],
                            valueInputOption="USER_ENTERED",
                            insertDataOption="OVERWRITE",
                            body={"values": [
                                [
                                    f"""=HYPERLINK("{metadata["url"]}", "{boxscore["game"]}")""",
                                    *[*boxscore.values()][1:4],
                                    f"{boxscore["player"]}{metadata["series"]}{metadata["game"]}",
                                    boxscore["ip"],
                                    boxscore["bf"],
                                    boxscore["np"],
                                    *[*metadata.values()][4:6]
                                ]
                                for boxscore in boxscore_by_position
                            ]}
                        ).execute()
                        LOGGER.info("updated %i rows in %s", response["updates"]["updatedRows"], args.ranges[1])
        else:
            LOGGER.info("finished successfully")

if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO)
    main()