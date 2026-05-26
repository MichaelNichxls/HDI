# TODO: option label in launch
# TODO: performance

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
from playwright.sync_api import BrowserContext, FrameLocator, Locator, Page, TimeoutError, sync_playwright

LOGGER = logging.getLogger(__name__)
NOW = datetime.now()
SERIES_DATE = {
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

type PageOrLocatorToLocator = Callable[[Page | Locator | FrameLocator], Locator]
type Metadata = dict[str, Any]

META_GAME_LOCATOR: PageOrLocatorToLocator = lambda locator: locator.locator("table.schedule-event-table__table tbody > tr").or_(
    locator.locator("table.sidearm-calendar-table tbody > tr")
)
META_MATCHUP_FIRST_LOCATOR: PageOrLocatorToLocator = lambda locator: locator.locator(
    "td.schedule-event-cell--firstTeam .schedule-event-opponent__name"
).or_(locator.locator("td.sidearm-team-away .sidearm-calendar-list-group-list-game-team-title"))
META_MATCHUP_SECOND_LOCATOR: PageOrLocatorToLocator = lambda locator: locator.locator(
    "td.schedule-event-cell--secondTeam .schedule-event-opponent__name"
).or_(locator.locator("td.sidearm-team-home .sidearm-calendar-list-group-list-game-team-title"))
META_DATE_LOCATOR: PageOrLocatorToLocator = lambda locator: locator.locator("td.schedule-event-cell--results_time span:not([class])").or_(
    locator.locator("td span[data-bind*='date']")
)
META_URL_LOCATOR: PageOrLocatorToLocator = lambda locator: locator.locator("a:has-text('Stats')").or_(locator.locator("a:has-text('Box Score')"))
GAME_LOCATOR: PageOrLocatorToLocator = lambda locator: locator.locator("h2.roster-title__header:has(.roster-title__content)").or_(
    locator.locator("header.sidearm-box-score-header h3")
)
DATE_LOCATOR: PageOrLocatorToLocator = lambda locator: locator.locator("time.match-stats-header__match-details-item-value").or_(
    locator.locator("dt:has-text('Date') + dd")
)
BATTING_LOCATOR: PageOrLocatorToLocator = lambda locator: locator.locator("//*[normalize-space()='Hitting']/following-sibling::*[1]//table").or_(
    locator.locator("//h3[normalize-space()='Batting']/following-sibling::*//table")
)
PITCHING_LOCATOR: PageOrLocatorToLocator = lambda locator: locator.locator("//*[normalize-space()='Pitching']/following-sibling::*[1]//table").or_(
    locator.locator("//h3[normalize-space()='Pitching']/following::table[position()<=2]")
)
BP_TEAM_LOCATOR: PageOrLocatorToLocator = lambda locator: locator.locator("thead tr:first-child th.advanced-table__cell--head:last-child").or_(
    locator.locator("> caption")
)
BP_PLAYER_LOCATOR: PageOrLocatorToLocator = lambda locator: locator.locator("tbody > tr")
BP_PLAYER_NAME_LOCATOR: PageOrLocatorToLocator = lambda locator: locator.locator(
    "xpath=td[count(ancestor::table//th[normalize-space()='Player']/preceding-sibling::th)+1][contains(@class,'advanced-table__cell')]"
).or_(locator.locator("xpath=th[ancestor::tbody/preceding-sibling::caption]"))


def normalize(str_: str) -> str:
    str_ = PARENS_PATTERN.sub("", str_)
    str_ = NUMBER_PATTERN.sub("", str_)
    str_ = LAST_FIRST_PATTERN.sub(r"\2 \1", str_)
    return " ".join(str_.replace("\n", " ").strip().title().split())


def enumerate_games_grouped_by_series(metadata: Generator[Metadata, None, None]) -> Generator[list[Metadata], None, None]:
    for _, metadata_by_series in groupby(metadata, key=lambda m: m["series"]):
        metadata_by_series = sorted(metadata_by_series, key=lambda m: (m["matchup"], m["date"]))
        for _, metadata_by_matchup in groupby(metadata_by_series, key=lambda m: m["matchup"]):
            for i, m in enumerate(metadata_by_matchup, 1):
                m["game"] = i

        yield metadata_by_series


def get_boxscore_metadata(context: BrowserContext, url: str, series_date: datetime) -> Generator[Metadata, None, None]:
    with context.new_page() as page:
        page.set_default_timeout(10_000)
        page.goto(url)
        while True:
            try:
                # TODO: if visible the first time, loop
                page.locator(".schedule-list__load_more__button").click(timeout=5_000)
            except TimeoutError:
                break

        for game in META_GAME_LOCATOR(page).all():
            matchup = (
                normalize(META_MATCHUP_FIRST_LOCATOR(game).text_content()),
                normalize(META_MATCHUP_SECOND_LOCATOR(game).text_content()),
            )
            try:
                date = datetime.strptime(f"{META_DATE_LOCATOR(game).text_content()}, {NOW.year}", "%a., %b. %d, %Y")
            except ValueError:
                date = datetime.strptime(META_DATE_LOCATOR(game).text_content(), "%A %m/%d/%Y")

            url_ = url_loc.evaluate("el => el.href") if (url_loc := META_URL_LOCATOR(game)).is_visible() else None
            series = ((date - series_date).days + 1) // 7 + 1
            yield {
                "matchup": matchup,
                "date": date,
                "url": url_,
                "series": series,
            }


def get_boxscores(context: BrowserContext, url: str) -> Generator[dict[str, str], None, None]:
    with context.new_page() as page:
        page.set_default_timeout(10_000)
        page.goto(url)
        try:
            page_or_frame = page.frame_locator(".iframe-container__iframe").frame_locator("#boxscore")
            game = normalize(GAME_LOCATOR(page_or_frame).text_content())
        except TimeoutError:
            page_or_frame = page
            game = normalize(GAME_LOCATOR(page_or_frame).text_content())

        date = datetime.strptime(DATE_LOCATOR(page_or_frame).text_content(), "%m/%d/%Y")
        for batting in BATTING_LOCATOR(page_or_frame).all():
            team = normalize(BP_TEAM_LOCATOR(batting).text_content())
            for player in BP_PLAYER_LOCATOR(batting).all():
                name = normalize(BP_PLAYER_NAME_LOCATOR(player).text_content())
                data = player.locator("td, th").all()
                if (position := data[0].text_content().upper()) == "P":
                    continue
                yield {
                    "game": game,
                    "date": date,
                    "team": team,
                    "player": name,
                    "position": position,
                    **{s: float(data[i].text_content()) for i, s in enumerate(STATS["batting"], 2)},
                }
        for pitching in PITCHING_LOCATOR(page_or_frame).all():
            team = normalize(BP_TEAM_LOCATOR(pitching).text_content())
            for player in BP_PLAYER_LOCATOR(pitching).all():
                name = normalize(BP_PLAYER_NAME_LOCATOR(player).text_content())
                data = player.locator("td, th").all()
                yield {
                    "game": game,
                    "date": date,
                    "team": team,
                    "player": name,
                    "position": "P",
                    **{s: float(data[i].text_content()) for i, s in enumerate(STATS["pitching"], 1)},
                }


def main() -> None:
    parser = argparse.ArgumentParser(formatter_class=argparse.ArgumentDefaultsHelpFormatter)
    # fmt: off
    parser.add_argument("conference", choices=["sec", "acc"], help="conference to scrape college baseball boxscores from")
    parser.add_argument("-i", "--id", default=os.getenv("GOOGLE_SPREADSHEET_ID"), help="id of google spreadsheet; required if GOOGLE_SPREADSHEET_ID environment variable is not specified")
    parser.add_argument("-c", "--credentials", default="service_account.json", metavar="PATH", help="path of google service account json file")
    parser.add_argument("-r", "--ranges", nargs=2, default=["Sheet1!A1", "Sheet2!A1"], metavar="RANGE", help="ranges within google spreadsheet to write the data to; first range is for batting data, second range is for pitching data")
    parser.add_argument("--clear", action="store_true", help="clears ranges within google spreadsheet before writing the data; ranges are specified via the '-r, --ranges' flag")
    # fmt: on
    args = parser.parse_args()

    credentials = service_account.Credentials.from_service_account_file(args.credentials, scopes=["https://www.googleapis.com/auth/spreadsheets"])
    sheets = build("sheets", "v4", credentials=credentials)

    if args.clear:
        response = sheets.spreadsheets().values().batchClear(spreadsheetId=args.id, body={"ranges": [args.ranges[0], args.ranges[1]]}).execute()
        LOGGER.info("cleared %i rows in %s and %s", response["updates"]["updatedRows"], args.ranges[0], args.ranges[1])

    with (
        sync_playwright() as p,
        p.chromium.launch() as browser,
        browser.new_context(viewport={"width": 1920, "height": 1080}) as context,
    ):
        metadata = get_boxscore_metadata(context, URLS[args.conference], SERIES_DATE[args.conference])
        for metadata_by_series in enumerate_games_grouped_by_series(metadata):
            metadata_by_series = [
                m
                for m in metadata_by_series
                if m["matchup"][0] in TEAMS[args.conference]
                and m["matchup"][1] in TEAMS[args.conference]
                and m["date"] <= NOW
                and m["url"]
                and m["series"] in range(1, 11)
            ]
            if not metadata_by_series:
                continue

            for m in metadata_by_series:
                for batter, boxscore_by_position in groupby(get_boxscores(context, m["url"]), key=lambda b: b["position"] != "P"):
                    body = {
                        "values": [
                            [
                                f"""=HYPERLINK("{m["url"]}", "{b["game"]}")""",
                                datetime.strftime(b["date"], "%m/%d/%Y"),
                                b["team"],
                                b["player"],
                                f"""{b["player"]}{m["series"]}{m["game"]}""",
                                *([b["ab"]] if batter else [b["ip"], b["bf"], b["np"]]),
                                m["series"],
                                m["game"],
                            ]
                            for b in boxscore_by_position
                        ]
                    }
                    response = (
                        sheets.spreadsheets()
                        .values()
                        .append(
                            spreadsheetId=args.id,
                            range=args.ranges[0] if batter else args.ranges[1],
                            valueInputOption="USER_ENTERED",
                            insertDataOption="OVERWRITE",
                            body=body,
                        )
                        .execute()
                    )
                    LOGGER.info("updated %i rows in %s", response["updates"]["updatedRows"], args.ranges[0])


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO)
    main()
