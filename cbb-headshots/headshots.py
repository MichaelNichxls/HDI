import argparse
import csv
import io
import logging
import os
import re
import sys
from collections.abc import Callable, Generator
from datetime import datetime
from urllib.parse import parse_qs, unquote, urlencode, urlparse, urlunparse

import cv2
import mediapipe as mp
import numpy as np
import requests
from google.oauth2 import service_account
from googleapiclient.discovery import build
from googleapiclient.http import MediaIoBaseUpload
from mediapipe.tasks.python import vision
from playwright.sync_api import BrowserContext, Locator, Page, TimeoutError, expect, sync_playwright

LOGGER = logging.getLogger(__name__)
NOW = datetime.now()
SEASON = {
    "season_4": f"{NOW.replace(NOW.year - 1):%Y}" if NOW < datetime(NOW.year, 6, 1) else f"{NOW:%Y}",
    "season_22": f"{NOW.replace(NOW.year - 1):%y}{NOW:%y}" if NOW < datetime(NOW.year, 6, 1) else f"{NOW:%y}{NOW.replace(NOW.year + 1):%y}",
    "season_42": f"{NOW.replace(NOW.year - 1):%Y}-{NOW:%y}" if NOW < datetime(NOW.year, 6, 1) else f"{NOW:%Y}-{NOW.replace(NOW.year + 1):%y}",
    "season_44": f"{NOW.replace(NOW.year - 1):%Y}-{NOW:%Y}" if NOW < datetime(NOW.year, 6, 1) else f"{NOW:%Y}-{NOW.replace(NOW.year + 1):%Y}",
}
NUMBER_PATTERN = re.compile(r"\d{1,2}")
URL_PATTERN = re.compile(r"https?://\S+\b")
BASE64_PATTERN = re.compile(r"data:image/\w+;base64,\S+\b={0,2}")
TOP_OFFSET = 0.7
BOTTOM_OFFSET = 0.2

LOCATOR: Callable[[Page | Locator], Locator] = lambda locator: (
    locator.locator("select#sidearm-roster-select-template-dropdown")
    .or_(locator.locator("select#sidearm-roster-select-template"))
    .or_(locator.locator("section.roster__filters select#view"))
    .or_(locator.locator(".roster-filters__view select#view"))
    .or_(locator.locator("button#_viewType_card"))
    .or_(locator.locator("button.view__card-button"))
    .or_(locator.locator("a.photo-view"))
    .or_(locator.locator("a.grid-view"))
    .or_(locator.locator("a.section-title_togglers_grid"))
    .or_(locator.locator("a[data-view='card']"))
    .or_(locator.locator(".hero__view a:has-text('Cards')"))
    .or_(locator.locator("table#DataTables_Table_2 tbody tr td[data-order] a"))
    .or_(locator.locator(".roster table tbody tr th.name > a"))
    .or_(locator.locator(".roster-data table tbody tr th > a"))
    .or_(locator.locator(".roster-data table tbody tr th[data-label*='Name'] .player-name-social-row a:nth-of-type(1)"))
    .or_(locator.locator("[class*='common-team-section_container__']:not(:has(h2[class*='common-team-section_title__']:has-text('Coaches'))) a[class*='game-roster-group-player_playerCard__']"))  # noqa: E501
)  # fmt: skip
POPUP_LOCATOR: Callable[[Page | Locator], Locator] = lambda locator: (
    locator.locator("#iubenda-cs-banner")
    .or_(locator.locator("#gdpr-compliance"))
    .or_(locator.locator("#polite-pop-up"))
    .or_(locator.locator(".c-polite-pop-up"))
    .or_(locator.locator(".s-popup"))
    .or_(locator.locator(".sticky-popup"))
    .or_(locator.locator("#onetrust-banner-sdk"))
)
PLAYERS_LOCATOR: Callable[[Page | Locator], Locator] = lambda locator: (
    locator.locator("li.sidearm-list-card-item[data-player-id]")
    .or_(locator.locator("li.sidearm-roster-list-item"))
    .or_(locator.locator("section.roster__list:nth-of-type(2) .roster__list_item"))
    .or_(locator.locator(".roster-players-cards .roster-card"))
    .or_(locator.locator(".roster-players-cards .roster-card-item"))
    .or_(locator.locator(".player-card-wrapper"))
    .or_(locator.locator(".featured__list:not(.staff) .player"))
    .or_(locator.locator("#cardPanel > * > .s-person-card"))
    .or_(locator.locator("#players .grid_view .player"))
    .or_(locator.locator("[itemprop='athlete']"))
)
PLAYERS_JERSEY_LOCATOR: Callable[[Page | Locator], Locator] = lambda locator: (
    locator.locator(".sidearm-roster-player-image .sidearm-roster-player-jersey")
    .or_(locator.locator(".sidearm-roster-list-item-number"))
    .or_(locator.locator(".roster-card__jersey-number"))
    .or_(locator.locator(".roster-card-item__number"))
    .or_(locator.locator(".roster-card-item__jersey-number"))
    .or_(locator.locator(".roster-list_item_number"))
    .or_(locator.locator(".roster-item__number"))
    .or_(locator.locator(".player-card-footer .number"))
    .or_(locator.locator(".player-heading .number"))
    .or_(locator.locator(".player-headshot .number"))
    .or_(locator.locator(".player__thumb .number"))
    .or_(locator.locator(".player__photo .number"))
    .or_(locator.locator(".card-front .number"))
    .or_(locator.locator(".bio-title .number"))
    .or_(locator.locator(".s-stamp__text"))
    .or_(locator.locator(".thumb .icon"))
    .or_(locator.locator(".thumb:has(.image) span"))
    .or_(locator.locator(".bordeaux_bio__title h1"))
    .or_(locator.locator("[itemprop='image'] ~ * .number"))
    .or_(locator.locator(".bg-player-background h2 ~ * p:nth-of-type(1)"))
    .filter(has_text=NUMBER_PATTERN)
)
PLAYERS_HEADSHOT_LOCATOR: Callable[[Page | Locator], Locator] = lambda locator: (
    locator.locator(".sidearm-roster-player-image")
    .or_(locator.locator("img.sidearm-roster-list-item-photo-img"))
    .or_(locator.locator(".roster-card-item__thumb img"))
    .or_(locator.locator("a.roster-card__image-wrapper img"))
    .or_(locator.locator("img.roster-card__image"))
    .or_(locator.locator("img.roster-card-item__image"))
    .or_(locator.locator(".player-headshot img"))
    .or_(locator.locator(".player__thumb .image"))
    .or_(locator.locator(".player-image [style]"))
    .or_(locator.locator(".player__photo [role='img']"))
    .or_(locator.locator("img.s-person-card__header__image"))
    .or_(locator.locator("img.img-thumbnail"))
    .or_(locator.locator("img.bio-headshot"))
    .or_(locator.locator(".thumb .image"))
    .or_(locator.locator(".thumb-image"))
    .or_(locator.locator(".thumb:has(.icon)"))
    .or_(locator.locator(".card-front img.headshot"))
    .or_(locator.locator(".bordeaux_bio__profile_picture img"))
    .or_(locator.locator("[itemprop='image'] ~ a.image img"))
    .or_(locator.locator("[itemprop='image'] ~ a[style]"))
    .or_(locator.locator("img[data-test-id='s-image-resized__img']"))
    .or_(locator.locator(".bg-player-background img.object-cover"))
)


def get_number(locator: Locator) -> str | None:
    if locator.count() == 0:
        return None

    return NUMBER_PATTERN.search(locator.inner_text()).group().zfill(2)


def get_img_url(locator: Locator) -> str | None:
    if locator.count() == 0:
        return None

    locator.scroll_into_view_if_needed()
    expect(locator).not_to_have_css("background-image", BASE64_PATTERN)
    expect(locator).not_to_have_attribute("src", BASE64_PATTERN)
    expect(locator).not_to_have_attribute("srcset", BASE64_PATTERN)

    img: dict[str, str] = locator.evaluate("el => ({ bg: window.getComputedStyle(el).backgroundImage, src: el.src || el.srcset })")
    if not (url := img["bg"] if img["bg"] != "none" else img["src"].split(" ")[0]):
        return None

    parsed = urlparse(URL_PATTERN.search(url).group())
    query = {k: v for k, v in parse_qs(parsed.query).items() if all(q not in k for q in ("width", "height", "type"))}
    if "url" in query:
        return unquote(query["url"][0])

    new_query = urlencode(query, doseq=True)
    return urlunparse(parsed._replace(query=new_query))


def get_headshots(context: BrowserContext, url: str) -> Generator[dict[str, str | None], None, None]:
    def _goto(page: Page, url: str) -> None:
        try:
            page.goto(url, wait_until="networkidle", timeout=5_000)
        except TimeoutError:
            page.wait_for_load_state("load", timeout=55_000)

    def _get_headshot(locator: Page | Locator) -> dict[str, str | None]:
        return {
            "jersey": get_number(PLAYERS_JERSEY_LOCATOR(locator)),
            "headshot": get_img_url(PLAYERS_HEADSHOT_LOCATOR(locator)),
        }

    with context.new_page() as page:
        page.set_default_timeout(10_000)
        page.add_locator_handler(POPUP_LOCATOR(page).first, lambda locator: locator.evaluate("el => el.remove()"), no_wait_after=True)
        _goto(page, url)

        locator = LOCATOR(page)
        match locator.first.evaluate("el => el.tagName"):
            case "SELECT":
                locator.hover()
                locator.select_option(["Roster View - Cards", "Card"])
                if (go := page.locator("button#sidearm-roster-select-template-button")).is_visible():
                    go.click(force=True)

                players = PLAYERS_LOCATOR(page)
                players.first.wait_for()
                for player in players.all():
                    yield _get_headshot(player)

            case "BUTTON" | "A" if locator.count() == 1:
                locator.click(force=True)
                players = PLAYERS_LOCATOR(page)
                players.first.wait_for()
                for player in players.all():
                    yield _get_headshot(player)

            # TODO: async
            case "A" if locator.count() > 1:
                for a in locator.all():
                    with context.new_page() as temp_page:
                        _goto(temp_page, a.evaluate("el => el.href"))
                        yield _get_headshot(temp_page)


# FIXME: tulsa: libpng warning: iCCP: known incorrect sRGB profile
def circular_crop_faces(
    detector: vision.FaceDetector, img: cv2.typing.MatLike, top_offset: float = TOP_OFFSET, bottom_offset: float = BOTTOM_OFFSET
) -> Generator[cv2.typing.MatLike, None, None]:
    mp_img = mp.Image(mp.ImageFormat.SRGB, cv2.cvtColor(img, cv2.COLOR_BGRA2RGB))
    for detection in detector.detect(mp_img).detections:
        bbox = detection.bounding_box
        x, y, w, h = bbox.origin_x, bbox.origin_y, bbox.width, bbox.height
        y -= int(h * top_offset)
        h = int(h * (1 + top_offset + bottom_offset))

        cx, cy = x + w // 2, y + h // 2
        ih, iw = img.shape[:2]
        size = max(w, h)

        x1 = np.clip(cx - size // 2, 0, iw - size)
        y1 = np.clip(cy - size // 2, 0, ih - size)
        side = min(size, iw - x1, ih - y1)
        x2, y2 = x1 + side, y1 + side

        crop = img[y1:y2, x1:x2].copy()
        mask = np.zeros((side, side), np.uint8)
        cv2.circle(mask, (side // 2, side // 2), side // 2, 255, -1)
        yield cv2.bitwise_and(crop, crop, mask=mask)


def main() -> None:
    parser = argparse.ArgumentParser(formatter_class=argparse.ArgumentDefaultsHelpFormatter)
    parser.add_argument("genius", help="genius of college basketball team to scrape headshots from and crop")
    parser.add_argument("-i", "--id", default=os.getenv("GOOGLE_DRIVE_ID"), help="id of google drive; required if GOOGLE_DRIVE_ID environment variable is not specified")
    parser.add_argument("-c", "--credentials", default="service_account.json", metavar="PATH", help="path of google service account json file")
    parser.add_argument("-m", "--model", default="models/blaze_face_short_range.tflite", metavar="PATH", help="path of face detection model")
    parser.add_argument("--wbb", action="store_true", help="whether women's college basketball should be scraped from instead; euroleague has no women teams")
    # parser.add_argument("--clear", action="store_true", help="")
    args = parser.parse_args([a for a in sys.argv[1:] if a.strip()])

    credentials = service_account.Credentials.from_service_account_file(args.credentials, scopes=["https://www.googleapis.com/auth/drive"])
    drive = build("drive", "v3", credentials=credentials)

    with open("genius.csv") as f:
        genius = {row["Genius"]: row for row in csv.DictReader(f)}
        assert args.genius in genius

    url = genius[args.genius]["URL" if not args.wbb else "URLW"].format(**SEASON)
    assert url

    # TODO: create folder if one doesn't exist
    q = f"'{args.id}' in parents and name='{args.genius}' and trashed=false"
    id = drive.files().list(supportsAllDrives=True, includeItemsFromAllDrives=True, q=q).execute()["files"][0]["id"]
    assert id

    with (
        sync_playwright() as p,
        p.chromium.launch() as browser,
        browser.new_context(viewport={"width": 1920, "height": 1080}) as context,
    ):
        headshots = [*get_headshots(context, url)]

    # files = drive.files().list(
    #     supportsAllDrives=True,
    #     includeItemsFromAllDrives=True,
    #     q=f"'{id}' in parents and trashed=false"
    # ).execute()["files"]

    # for file in files:
    #     drive.files().delete(fileId=file["id"], supportsAllDrives=True).execute()
    #     LOGGER.info("deleted %s", file["name"])

    with vision.FaceDetector.create_from_model_path(args.model) as detector:
        for headshot in headshots:
            filename = f"{genius[args.genius]['HDI' if not args.wbb else 'HDIW']}{headshot['jersey']}pic.png"
            if not headshot["headshot"] or not headshot["jersey"]:
                LOGGER.warning("no headshot or jersey found for %s at %s", filename, url)
                continue

            buffer = requests.get(headshot["headshot"]).content
            decoded = cv2.imdecode(np.frombuffer(buffer, np.uint8), cv2.IMREAD_UNCHANGED)
            crops = [*circular_crop_faces(detector, decoded)]
            if len(crops) == 0:
                LOGGER.warning("no faces detected for %s at %s", filename, url)
                continue
            elif len(crops) > 1:
                LOGGER.warning("multiple faces detected for %s at %s", filename, url)

            success, encoded = cv2.imencode(".png", crops[0])
            if not success:
                continue

            media = MediaIoBaseUpload(io.BytesIO(encoded), "image/png", resumable=True)
            drive.files().create(supportsAllDrives=True, media_body=media, body={"name": filename, "parents": [id]}).execute()
            LOGGER.info("created %s", filename)
        else:
            LOGGER.info("finished successfully")


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO)
    main()
