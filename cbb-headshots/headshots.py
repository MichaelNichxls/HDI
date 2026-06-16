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
from playwright.sync_api import BrowserContext, Locator, Page, TimeoutError, sync_playwright

LOGGER = logging.getLogger(__name__)
NOW = datetime.now()
SEASON = {
    "season_Y": f"{NOW.replace(NOW.year - 1):%Y}" if NOW < datetime(NOW.year, 8, 1) else f"{NOW:%Y}",
    "season_yy": f"{NOW.replace(NOW.year - 1):%y}{NOW:%y}" if NOW < datetime(NOW.year, 8, 1) else f"{NOW:%y}{NOW.replace(NOW.year + 1):%y}",
    "season_Yy": f"{NOW.replace(NOW.year - 1):%Y}-{NOW:%y}" if NOW < datetime(NOW.year, 8, 1) else f"{NOW:%Y}-{NOW.replace(NOW.year + 1):%y}",
    "season_YY": f"{NOW.replace(NOW.year - 1):%Y}-{NOW:%Y}" if NOW < datetime(NOW.year, 8, 1) else f"{NOW:%Y}-{NOW.replace(NOW.year + 1):%Y}",
}
NUMBER_PATTERN = re.compile(r"\d{1,2}")
URL_PATTERN = re.compile(r"https?://\S+\b")
TOP_OFFSET = 0.7
BOTTOM_OFFSET = 0.2

type PageOrLocator = Page | Locator
type PageOrLocatorToLocator = Callable[[PageOrLocator], Locator]

VIEW_LOCATOR: PageOrLocatorToLocator = lambda locator: locator.locator(
    ", ".join(
        [
            "select#sidearm-roster-select-template-dropdown",
            "select#sidearm-roster-select-template",
            "section.roster__filters select#view",
            ".roster-filters__view select#view",
            "button#_viewType_card",
            "button.view__card-button",
            "a.photo-view",
            "a.grid-view",
            "a.section-title_togglers_grid",
            "a[data-view='card']",
            ".hero__view a:has-text('Cards')",
        ]
    )
)
POPUP_LOCATOR: PageOrLocatorToLocator = lambda locator: locator.locator(
    ", ".join(
        [
            "#iubenda-cs-banner",
            "#gdpr-compliance",
            "#polite-pop-up",
            ".c-polite-pop-up",
            ".s-popup",
            ".sticky-popup",
            "#onetrust-banner-sdk",
            "#CybotCookiebotDialog",
            "#didomi-popup",
        ]
    )
)
PLAYERS_LOCATOR: PageOrLocatorToLocator = lambda locator: locator.locator(
    ", ".join(
        [
            "li.sidearm-list-card-item[data-player-id]",
            "li.sidearm-roster-list-item",
            "section.roster__list:nth-of-type(2) .roster__list_item",
            ".roster-players-cards .roster-card",
            ".roster-players-cards .roster-card-item",
            ".player-card-wrapper",
            ".featured__list:not(.staff) .player",
            "#cardPanel > * > .s-person-card",
            "#players .grid_view .player",
            "[itemprop='athlete']",
            "table#DataTables_Table_2 tbody tr td[data-order] a",
            ".roster table tbody tr th.name > a",
            ".roster-data table tbody tr th > a",
            ".roster-data table tbody tr th[data-label*='Name'] .player-name-social-row a:nth-of-type(1)",
            ".bottom-team:has-text('L’EQUIPE') + .managment-bottom > a",
            "[class$='Wrapper'] > * > a[class^='LinkButton-module_button__']",
            "canales-digitales-baskonia-alaves-member-card",
            ".players h4:not(:has-text('Cuerpo técnico')) + app-swipe-carousel app-player-profile-card",
            ".plantilla .items-row > *",
            ".view-plantilla h3:not(:has-text('Cuerpo Técnico')) + * > * > *",
            "#roster .listado-personas > *",
            "h2:not(:has-text('Coaches')) + * > a[class*='__playerCard']",
            ":not([aria-label='Coaching Staff']) + ul li.team-list__person-container",
            "section.uk-section li",
            ".team-grid [data-position]",
            "dl.gallery-item",
        ]
    )
)
PLAYERS_JERSEY_LOCATOR: PageOrLocatorToLocator = lambda locator: locator.locator(
    ", ".join(
        [
            ".sidearm-roster-player-image .sidearm-roster-player-jersey",
            ".sidearm-roster-list-item-number",
            ".roster-card__jersey-number",
            ".roster-card-item__number",
            ".roster-card-item__jersey-number",
            ".roster-list_item_number",
            ".roster-item__number",
            ".player-card-footer .number",
            ".player-heading .number",
            ".player-headshot .number",
            ".player__thumb .number",
            ".player__photo .number",
            ".card-front .number",
            ".bio-title .number",
            ".s-stamp__text",
            ".thumb .icon",
            ".thumb:has(.image) span",
            ".bordeaux_bio__title h1",
            "[itemprop='image'] ~ * .number",
            ".les-topsh1",
            ".player-content .dorsal",
            "[class^='Column-module_column__'] > *:has(+ h1[id]):last-of-type",
            ".profile-card__number",
            ".img-dorsal",
            ".card-deportista__info__dorsal",
            ".contenido .dorsal",
            ".bg-player-background h2 + * > p:first-child",
            ".team-person__number",
            ".uk-description-list dt:has-text('Number') + dd",
            ".player-number",
            ".gallery-caption .number",
        ]
    )
)
PLAYERS_HEADSHOT_LOCATOR: PageOrLocatorToLocator = lambda locator: locator.locator(
    ", ".join(
        [
            ".sidearm-roster-player-image",
            "img.sidearm-roster-list-item-photo-img",
            ".roster-card-item__thumb img",
            "a.roster-card__image-wrapper img",
            "img.roster-card__image",
            "img.roster-card-item__image",
            ".player-headshot img",
            ".player__thumb .image",
            ".player-image [style]",
            ".player__photo [role='img']",
            "img.s-person-card__header__image",
            "img.img-thumbnail",
            "img.bio-headshot",
            ".thumb .image",
            ".thumb-image",
            ".thumb:has(.icon)",
            ".card-front img.headshot",
            ".bordeaux_bio__profile_picture img",
            "[itemprop='image'] ~ a.image img",
            "[itemprop='image'] ~ a[style]",
            "img[data-test-id='s-image-resized__img']",
            ".player-box img",
            "canales-digitales-baskonia-alaves-strapi-image img",
            "[class^='Image-module_imageFill'] img",
            "img.profile-card__img",
            "img[itemprop='thumbnailUrl']",
            "img.image-style-foto-deportista",
            ".contenido a img",
            ".bg-player-background > * > * > img",
            "picture.team-person__picture img",
            ".uk-card-media-top img",
            ".wrapper-img img:first-child",
            ".gallery-icon img",
        ]
    )
)


def get_number(locator: Locator) -> str | None:
    if locator.count() == 0:
        return None

    return match.group().zfill(2) if (match := NUMBER_PATTERN.search(locator.text_content() or "")) else None


def get_img_url(locator: Locator) -> str | None:
    if locator.count() == 0:
        return None

    locator.scroll_into_view_if_needed()
    url: str = locator.page.wait_for_function(
        """
        ([el, pattern]) => [window.getComputedStyle(el).backgroundImage, el.srcset, el.src]
            .map(src => src?.match(new RegExp(pattern))?.[0])
            .find(Boolean)
        """,
        arg=[locator.element_handle(), URL_PATTERN.pattern],
    ).json_value()

    parsed = urlparse(url)
    query = {k: v for k, v in parse_qs(parsed.query).items() if all(q not in k for q in ("wid", "hei", "type", "fit"))}
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

    def _get_headshot(locator: PageOrLocator) -> dict[str, str | None]:
        return {"jersey": get_number(PLAYERS_JERSEY_LOCATOR(locator)), "headshot": get_img_url(PLAYERS_HEADSHOT_LOCATOR(locator))}

    with context.new_page() as page:
        page.add_locator_handler(POPUP_LOCATOR(page).first, lambda locator: locator.evaluate("el => el.remove()"), no_wait_after=True)
        _goto(page, url)
        if (view := VIEW_LOCATOR(page)).is_visible():
            match view.evaluate("el => el.tagName"):
                case "SELECT":
                    view.select_option(["Roster View - Cards", "Card"])
                    if (go := page.locator("button#sidearm-roster-select-template-button")).is_visible():
                        go.click(force=True)
                case "BUTTON" | "A":
                    view.click(force=True)

        players = PLAYERS_LOCATOR(page)
        players.first.wait_for()
        for player in players.all():
            match player.evaluate("el => el.tagName"):
                case "A":
                    with context.new_page() as temp_page:
                        _goto(temp_page, player.evaluate("el => el.href"))
                        yield _get_headshot(temp_page)
                case _:
                    yield _get_headshot(player)


def circular_crop_faces(
    detector: vision.FaceDetector, img: cv2.typing.MatLike, *, top_offset: float = TOP_OFFSET, bottom_offset: float = BOTTOM_OFFSET
) -> Generator[cv2.typing.MatLike, None, None]:
    img = cv2.cvtColor(img, cv2.COLOR_BGR2BGRA)
    mp_img = mp.Image(mp.ImageFormat.SRGB, cv2.cvtColor(img, cv2.COLOR_BGRA2RGB))
    for detection in detector.detect(mp_img).detections:
        bbox = detection.bounding_box
        x, y, w, h = bbox.origin_x, bbox.origin_y, bbox.width, bbox.height
        y -= int(h * top_offset)
        h = int(h * (1 + top_offset + bottom_offset))

        cx, cy = x + w // 2, y + h // 2
        ih, iw = img.shape[:2]
        side = min(max(w, h), iw, ih)

        x1, y1 = np.clip(cx - side // 2, 0, iw - side), np.clip(cy - side // 2, 0, ih - side)
        x2, y2 = x1 + side, y1 + side
        crop = img[y1:y2, x1:x2].copy()

        mask = np.zeros((side, side), np.uint8)
        cv2.circle(mask, (side // 2, side // 2), side // 2, 255, -1)
        yield cv2.bitwise_and(crop, crop, mask=mask)


def main() -> None:
    parser = argparse.ArgumentParser(formatter_class=argparse.ArgumentDefaultsHelpFormatter)
    # fmt: off
    parser.add_argument("genius", help="genius of college basketball team to scrape headshots from and crop")
    parser.add_argument("-i", "--id", default=os.getenv("GOOGLE_DRIVE_ID"), help="id of Google drive (required if GOOGLE_DRIVE_ID environment variable is not set)")
    parser.add_argument("-c", "--credentials", default="service_account.json", metavar="PATH", help="path to Google service account json file")
    parser.add_argument("-m", "--model", default="models/blaze_face_short_range.tflite", metavar="PATH", help="path to face detection model")
    parser.add_argument("--wbb", action="store_true", help="whether women's college basketball should be scraped from instead (EuroLeague and Spanish League have no women teams)")
    parser.add_argument("--recreate", action="store_true", help="recreate current genius folder in Google drive, if any, before writing data")
    parser.add_argument("--top-offset", default=TOP_OFFSET, metavar="OFFSET", help="top offset to crop headshot")
    parser.add_argument("--bottom-offset", default=BOTTOM_OFFSET, metavar="OFFSET", help="bottom offset to crop headshot")
    # fmt: on
    args = parser.parse_args([a for a in sys.argv[1:] if a.strip()])

    credentials = service_account.Credentials.from_service_account_file(args.credentials, scopes=["https://www.googleapis.com/auth/drive"])
    drive = build("drive", "v3", credentials=credentials)

    with open("genius.csv") as f:
        genius = {row["Genius"]: row for row in csv.DictReader(f)}

    if args.genius not in genius:
        LOGGER.critical("%s not found in genius.csv", args.genius)
        return

    url = genius[args.genius]["URL" if not args.wbb else "URLW"].format(**SEASON)
    if not url:
        LOGGER.critical("%s URL not found", args.genius)
        return

    list = drive.files().list(q=f"'{args.id}' in parents and name='{args.genius}' and trashed=false", includeItemsFromAllDrives=True, supportsAllDrives=True).execute()
    id = list["files"][0]["id"] if list["files"] else None
    if id and args.trash:
        update = drive.files().update(fileId=id, body={"trashed": True}, supportsAllDrives=True).execute()
        LOGGER.info("%s Trashed", update["name"])
        id = None

    if not id:
        create = drive.files().create(body={"name": args.genius, "mimeType": "application/vnd.google-apps.folder", "parents": [args.id]}, supportsAllDrives=True).execute()
        LOGGER.info("%s Created", create["name"])
        id = create["id"]

    # TODO: first None or "0"
    with (
        sync_playwright() as p,
        p.chromium.launch() as browser,
        browser.new_context(viewport={"width": 1920, "height": 1080}) as context,
        vision.FaceDetector.create_from_model_path(args.model) as detector,
    ):
        for headshot in get_headshots(context, url):
            filename = f"{genius[args.genius]['HDI' if not args.wbb else 'HDIW']}{headshot['jersey']}pic.png"
            if not headshot["headshot"] or not headshot["jersey"]:
                LOGGER.error("%s No headshot or jersey found", filename)
                continue

            buffer = requests.get(
                headshot["headshot"],
                headers={"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/147.0.0.0 Safari/537.36"},
            ).content
            decoded = cv2.imdecode(np.frombuffer(buffer, np.uint8), cv2.IMREAD_UNCHANGED)
            crops = [*circular_crop_faces(detector, decoded, top_offset=args.top_offset, bottom_offset=args.bottom_offset)]
            if len(crops) == 0:
                LOGGER.error("%s No faces detected", filename)
                continue
            elif len(crops) > 1:
                LOGGER.warning("%s Multiple faces detected", filename)

            success, encoded = cv2.imencode(".png", crops[0])
            if not success:
                LOGGER.error("%s Failed to encode image")
                continue

            drive.files().create(
                media_body=MediaIoBaseUpload(io.BytesIO(encoded), "image/png", resumable=True),
                body={"name": filename, "parents": [id]},
                supportsAllDrives=True,
            ).execute()
            LOGGER.info("%s Created", filename)


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO)
    main()
