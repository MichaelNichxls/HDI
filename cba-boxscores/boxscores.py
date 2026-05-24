# TODO: remove stubs, add typings
# TODO: easier to ask for permission
# TODO: eager loading
# TODO: less empty lines
# TODO: visibility vs presence
# TODO: _get_*()
# TODO: normalize null check
# TODO: no RE
# TODO: configurable consts
# TODO: option label in launch
# TODO: no more body={} shenanigans

import argparse
import logging
import os
import re
from collections.abc import Callable, Generator
from datetime import datetime
from itertools import groupby
from typing import Any

from google.oauth2 import service_account
from googleapiclient.discovery import build
from playwright.sync_api import BrowserContext, Locator, Page, TimeoutError, sync_playwright

LOGGER = logging.getLogger(__name__)
NOW = datetime.now()
SERIES = {
    "sec": datetime(NOW.year, 3, 13),
    "acc": datetime(NOW.year, 3, 6),
}
URLS = {
    "sec": "https://www.secsports.com/schedule/baseball?view=season",
    "acc": "https://theacc.com/calendar.aspx?path=baseball",
}
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
        "Vanderbilt",
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
        "Wake Forest",
    ),
}
STATS = {
    "batting": (
        "ab",
        "r",
        "h",
        "rbi",
        "bb",
        "so",
        "lob",
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
        "np",
    ),
}
PARENS_PATTERN = re.compile(r"\([^)]*\)")
NUMBER_PATTERN = re.compile(r"#?\d{1,2}")
LAST_FIRST_PATTERN = re.compile(r"(\b.*),\s*(.*\b)")

GAME_LOCATOR: Callable[[Page | Locator], Locator] = lambda locator: locator.locator("table.schedule-event-table__table tbody > tr").or_(
    locator.locator("table.sidearm-calendar-table tbody > tr")
)
MATCHUP_FIRST_LOCATOR: Callable[[Page | Locator], Locator] = lambda locator: locator.locator("td.schedule-event-cell--firstTeam .schedule-event-opponent__name").or_(
    locator.locator("td.sidearm-team-away .sidearm-calendar-list-group-list-game-team-title")
)
MATCHUP_SECOND_LOCATOR: Callable[[Page | Locator], Locator] = lambda locator: locator.locator("td.schedule-event-cell--secondTeam .schedule-event-opponent__name").or_(
    locator.locator("td.sidearm-team-home .sidearm-calendar-list-group-list-game-team-title")
)
DATE_LOCATOR: Callable[[Page | Locator], Locator] = lambda locator: locator.locator("td.schedule-event-cell--results_time span:not([class])").or_(
    locator.locator("td span[data-bind*='date']")
)
URL_LOCATOR: Callable[[Page | Locator], Locator] = lambda locator: locator.locator("a:has-text('Stats')").or_(locator.locator("a:has-text('Box Score')"))


def normalize(str_: str) -> str:
    str_ = PARENS_PATTERN.sub("", str_)
    str_ = NUMBER_PATTERN.sub("", str_)
    str_ = LAST_FIRST_PATTERN.sub(r"\2 \1", str_)
    return str_.replace("\n", " ").strip().title()


def get_boxscore_metadata(context: BrowserContext, url: str) -> Generator[dict[str, Any], None, None]:
    with context.new_page() as page:
        page.set_default_timeout(10_000)
        page.goto(url)
        # TODO: is there any other way to do this
        while True:
            try:
                page.locator(".schedule-list__load_more__button").click(timeout=5_000)
            except TimeoutError:
                break

        for game in GAME_LOCATOR(page).all():
            matchup = (
                normalize(MATCHUP_FIRST_LOCATOR(game).inner_text()),
                normalize(MATCHUP_SECOND_LOCATOR(game).inner_text()),
            )
            try:
                date = datetime.strptime(f"{DATE_LOCATOR(game).inner_text(), {NOW.year}}", "%a., %b. %d, %Y")
            except ValueError:
                date = datetime.strptime(DATE_LOCATOR(game).inner_text(), "%A %m/%d/%Y")

            url = u.evaluate("el => el.href") if (u := URL_LOCATOR(game)).is_visible() else None
            # series = ((date - SERIES[conference]).days + 1) // 7 + 1
            yield {
                # "conference": conference,
                "matchup": matchup,
                "date": date,
                "url": url,
                # "series": series,
            }


def get_boxscores(context: BrowserContext, metadata: dict[str, Any]) -> Generator[dict[str, str], None, None]:
    pass


#     wait = WebDriverWait(driver, 5)

#     with temp_tab(driver, metadata["url"]):
#         LOGGER.info("goto %s", metadata["url"])

#         if metadata["conference"] == "sec":
#             wait.until(EC.frame_to_be_available_and_switch_to_it((By.CLASS_NAME, "iframe-container__iframe")))
#             wait.until(EC.frame_to_be_available_and_switch_to_it((By.ID, "boxscore")))

#             game = normalize(wait.until(EC.presence_of_element_located((By.CSS_SELECTOR, "h2.roster-title__header:has(.roster-title__content)"))).text)
#             date = datetime.strftime(metadata["date"], "%m/%d/%Y")

#             for batting in wait.until(EC.presence_of_all_elements_located((By.XPATH, "//*[normalize-space()='Hitting']/following-sibling::*[1]//table"))):
#                 team = normalize(batting.find_element(By.XPATH, "thead/tr[1]/th[last()]").text)

#                 for player in batting.find_elements(By.XPATH, "tbody/tr[normalize-space(td[1])!='P']"):
#                     data = player.find_elements(By.TAG_NAME, "td")
#                     name = normalize(data[1].text)
#                     position = data[0].text
#                     yield {
#                         "game": game,
#                         "date": date,
#                         "team": team,
#                         "player": name,
#                         "position": position,
#                         **{s: data[i].text for i, s in enumerate(STATS["batting"], 2)},
#                     }
#             for pitching in wait.until(EC.presence_of_all_elements_located((By.XPATH, "//*[normalize-space()='Pitching']/following-sibling::*[1]//table"))):
#                 team = normalize(pitching.find_element(By.XPATH, "thead/tr[1]/th[last()]").text)

#                 for player in pitching.find_elements(By.XPATH, "tbody/tr"):
#                     data = player.find_elements(By.TAG_NAME, "td")
#                     name = normalize(data[0].text)
#                     yield {
#                         "game": game,
#                         "date": date,
#                         "team": team,
#                         "player": name,
#                         "position": "P",
#                         **{s: data[i].text for i, s in enumerate(STATS["pitching"], 1)},
#                     }
#         elif metadata["conference"] == "acc":
#             game = normalize(wait.until(EC.presence_of_element_located((By.CSS_SELECTOR, "header.sidearm-box-score-header h3"))).text)
#             date = datetime.strftime(metadata["date"], "%m/%d/%Y")

#             for batting in wait.until(EC.presence_of_all_elements_located((By.XPATH, "//h3[normalize-space()='Batting']/following-sibling::*//table"))):
#                 team = normalize(batting.find_element(By.TAG_NAME, "caption").text)

#                 for player in batting.find_elements(By.XPATH, "tbody/tr[normalize-space(td[1])!='p']"):
#                     data = player.find_elements(By.TAG_NAME, "td")
#                     name = normalize(player.find_element(By.TAG_NAME, "th").text)
#                     position = data[0].text
#                     yield {
#                         "game": game,
#                         "date": date,
#                         "team": team,
#                         "player": name,
#                         "position": position,
#                         **{s: data[i].text for i, s in enumerate(STATS["batting"], 1)},
#                     }
#             for pitching in wait.until(EC.presence_of_all_elements_located((By.XPATH, "//h3[normalize-space()='Pitching']/following::table[position()<=2]"))):
#                 team = normalize(pitching.find_element(By.TAG_NAME, "caption").text)

#                 for player in pitching.find_elements(By.XPATH, "tbody/tr"):
#                     data = player.find_elements(By.TAG_NAME, "td")
#                     name = normalize(player.find_element(By.TAG_NAME, "th").text)
#                     yield {
#                         "game": game,
#                         "date": date,
#                         "team": team,
#                         "player": name,
#                         "position": "P",
#                         **{s: data[i].text for i, s in enumerate(STATS["pitching"])},
#                     }


def main() -> None:
    parser = argparse.ArgumentParser(formatter_class=argparse.ArgumentDefaultsHelpFormatter)
    parser.add_argument("conference", choices=["sec", "acc"], help="conference to scrape college baseball boxscores from")
    parser.add_argument("-i", "--id", default=os.getenv("GOOGLE_SPREADSHEET_ID"), help="id of google spreadsheet; required if GOOGLE_SPREADSHEET_ID environment variable is not specified")  # fmt: skip  # noqa: E501
    parser.add_argument("-c", "--credentials", default="service_account.json", metavar="PATH", help="path of google service account json file")
    parser.add_argument("-r", "--ranges", nargs=2, default=["Sheet1!A1", "Sheet2!A1"], metavar="RANGE", help="ranges within google spreadsheet to write the data to; first range is for batting data, second range is for pitching data")  # fmt: skip  # noqa: E501
    parser.add_argument("--clear", action="store_true", help="clears ranges within google spreadsheet before writing the data; ranges are specified via the '-r, --ranges' flag")
    args = parser.parse_args()

    credentials = service_account.Credentials.from_service_account_file(args.credentials, scopes=["https://www.googleapis.com/auth/spreadsheets"])
    sheets = build("sheets", "v4", credentials=credentials)

    if args.clear:
        response = sheets.spreadsheets().values().batchClear(spreadsheetId=args.id, body={"ranges": [args.ranges[0], args.ranges[1]]}).execute()
        LOGGER.info("cleared %i rows in %s and %s", response["updates"]["updatedRows"], args.ranges[0], args.ranges[1])

    with (
        sync_playwright() as p,
        p.chromium.launch(headless=False) as browser,
        browser.new_context(viewport={"width": 1920, "height": 1080}) as context,
    ):
        for series, metadata_by_series in groupby(get_boxscore_metadata(context, URLS[args.conference]), key=lambda m: m["series"]):
            if series not in range(1, 11):
                continue

            metadata_by_series = [
                m for m in metadata_by_series if m["matchup"][0] in TEAMS[args.conference] and m["matchup"][1] in TEAMS[args.conference] and m["date"] <= NOW and m["url"]
            ]
            assert metadata_by_series
            metadata_by_series.sort(key=lambda m: (m["matchup"], m["date"]))
            for _, metadata_by_matchup in groupby(metadata_by_series, key=lambda m: m["matchup"]):
                for i, m in enumerate(metadata_by_matchup, 1):
                    m["game"] = i

            for metadata in metadata_by_series:
                break  # DEBUG
                for batter, boxscore_by_position in groupby(get_boxscores(context, metadata), key=lambda b: b["position"] != "P"):
                    # TODO: simplify
                    if batter:
                        body = {
                            "values": [
                                [
                                    f"""=HYPERLINK("{metadata["url"]}", "{boxscore["game"]}")""",
                                    *[*boxscore.values()][1:4],
                                    f"{boxscore['player']}{metadata['series']}{metadata['game']}",
                                    boxscore["ab"],
                                    *[*metadata.values()][4:6],
                                ]
                                for boxscore in boxscore_by_position
                            ]
                        }
                        response = (
                            sheets.spreadsheets()
                            .values()
                            .append(spreadsheetId=args.id, range=args.ranges[0], valueInputOption="USER_ENTERED", insertDataOption="OVERWRITE", body=body)
                            .execute()
                        )
                        LOGGER.info("updated %i rows in %s", response["updates"]["updatedRows"], args.ranges[0])
                    else:
                        body = {
                            "values": [
                                [
                                    f"""=HYPERLINK("{metadata["url"]}", "{boxscore["game"]}")""",
                                    *[*boxscore.values()][1:4],
                                    f"{boxscore['player']}{metadata['series']}{metadata['game']}",
                                    boxscore["ip"],
                                    boxscore["bf"],
                                    boxscore["np"],
                                    *[*metadata.values()][4:6],
                                ]
                                for boxscore in boxscore_by_position
                            ]
                        }
                        response = (
                            sheets.spreadsheets()
                            .values()
                            .append(spreadsheetId=args.id, range=args.ranges[1], valueInputOption="USER_ENTERED", insertDataOption="OVERWRITE", body=body)
                            .execute()
                        )
                        LOGGER.info("updated %i rows in %s", response["updates"]["updatedRows"], args.ranges[1])


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO)
    main()
