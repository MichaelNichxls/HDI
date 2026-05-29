import argparse
import csv
import io
import logging
import re
import sys
from collections.abc import Callable, Generator
from datetime import datetime
from urllib.parse import parse_qs, unquote, urlencode, urlparse, urlunparse

import cv2
import mediapipe as mp
import numpy as np
import requests
from environs import Env
from google.oauth2 import service_account
from googleapiclient.discovery import build
from googleapiclient.http import MediaIoBaseUpload
from mediapipe.tasks.python import vision
from playwright.sync_api import BrowserContext, Locator, Page, TimeoutError, expect, sync_playwright

env = Env()

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

type PageOrLocatorToLocator = Callable[[Page | Locator], Locator]

# fmt: off
LOCATOR: PageOrLocatorToLocator = lambda locator: (
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
    .or_(locator.locator("[class*='common-team-section_container__']:not(:has(h2[class*='common-team-section_title__']:has-text('Coaches'))) a[class*='game-roster-group-player_playerCard__']"))
    .or_(locator.locator("a:has(.spnplnamedesktop)"))
)
POPUP_LOCATOR: PageOrLocatorToLocator = lambda locator: (
    locator.locator("#iubenda-cs-banner")
    .or_(locator.locator("#gdpr-compliance"))
    .or_(locator.locator("#polite-pop-up"))
    .or_(locator.locator(".c-polite-pop-up"))
    .or_(locator.locator(".s-popup"))
    .or_(locator.locator(".sticky-popup"))
    .or_(locator.locator("#onetrust-banner-sdk"))
    .or_(locator.locator("#mys-wrapper"))
    .or_(locator.locator(".adsbygoogle[aria-hidden='false']"))
)
PLAYERS_LOCATOR: PageOrLocatorToLocator = lambda locator: (
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
PLAYERS_JERSEY_LOCATOR: PageOrLocatorToLocator = lambda locator: (
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
    .or_(locator.locator(".tduninumber"))
    .filter(has_text=NUMBER_PATTERN)
)
PLAYERS_HEADSHOT_LOCATOR: PageOrLocatorToLocator = lambda locator: (
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
    .or_(locator.locator("img.plfacepng"))
)
# fmt: on


def get_number(locator: Locator) -> str | None:
    if locator.count() == 0:
        return None

    return NUMBER_PATTERN.search(locator.inner_text()).group().zfill(2)


# TODO: increase timeouts
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

            case "A" if locator.count() > 1:
                for a in locator.all():
                    jersey = None
                    if (jersey_loc := a.locator("xpath=ancestor::tr").locator(PLAYERS_JERSEY_LOCATOR(page))).is_visible():
                        jersey = get_number(jersey_loc)
                    with context.new_page() as temp_page:
                        _goto(temp_page, a.evaluate("el => el.href"))
                        headshot = _get_headshot(temp_page)
                        headshot["jersey"] = jersey or headshot["jersey"]
                        yield headshot


def circular_crop_faces(
    detector: vision.FaceDetector,
    img: cv2.typing.MatLike,
    *,
    top_offset: float = TOP_OFFSET,
    bottom_offset: float = BOTTOM_OFFSET,
    no_clip_bounds: bool = False,
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

        if no_clip_bounds:
            side = max(w, h)
            cx_padded, cy_padded = cx + side, cy + side
            img_padded = cv2.copyMakeBorder(img, side, side, side, side, borderType=cv2.BORDER_CONSTANT, value=0)
            x1, y1 = cx_padded - side // 2, cy_padded - side // 2
            x2, y2 = x1 + side, y1 + side
            crop = img_padded[y1:y2, x1:x2].copy()
        else:
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
    parser.add_argument("-i", "--id", default=env.str("GOOGLE_DRIVE_ID", default=None), help="id of google drive; required if GOOGLE_DRIVE_ID environment variable is not specified")
    parser.add_argument("-c", "--credentials", default="service_account.json", metavar="PATH", help="path of google service account json file")
    parser.add_argument("-m", "--model", default="models/blaze_face_short_range.tflite", metavar="PATH", help="path of face detection model")
    parser.add_argument("--wbb", action="store_true", help="whether women's college basketball should be scraped from instead; euroleague and spanish league have no women teams")
    # parser.add_argument("--clear", action="store_true", help="")
    parser.add_argument("--top-offset", default=env.float("HDI_TOP_OFFSET", default=TOP_OFFSET), metavar="OFFSET", help="top offset to crop headshot")
    parser.add_argument("--bottom-offset", default=env.float("HDI_BOTTOM_OFFSET", default=BOTTOM_OFFSET), metavar="OFFSET", help="bottom offset to crop headshot")
    parser.add_argument("--no-clip-bounds", action="store_true", default=env.bool("HDI_NO_CLIP_BOUNDS", default=False), help="whether to not clip image bounds when cropping headshot; useful for small images")
    # fmt: on
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

    # files = drive.files().list(
    #     supportsAllDrives=True,
    #     includeItemsFromAllDrives=True,
    #     q=f"'{id}' in parents and trashed=false"
    # ).execute()["files"]

    # for file in files:
    #     drive.files().delete(fileId=file["id"], supportsAllDrives=True).execute()
    #     LOGGER.info("deleted %s", file["name"])

    with (
        sync_playwright() as p,
        p.chromium.launch() as browser,
        browser.new_context(viewport={"width": 1920, "height": 1080}) as context,
        vision.FaceDetector.create_from_model_path(args.model) as detector,
    ):
        for headshot in get_headshots(context, url):
            filename = f"{genius[args.genius]['HDI' if not args.wbb else 'HDIW']}{headshot['jersey']}pic.png"
            if not headshot["headshot"] or not headshot["jersey"]:
                LOGGER.warning("no headshot or jersey found for %s at %s", filename, url)
                continue

            buffer = requests.get(
                headshot["headshot"],
                headers={"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/147.0.0.0 Safari/537.36 OPR/131.0.0.0"},
            ).content
            decoded = cv2.imdecode(np.frombuffer(buffer, np.uint8), cv2.IMREAD_UNCHANGED)
            crops = [*circular_crop_faces(detector, decoded, top_offset=args.top_offset, bottom_offset=args.bottom_offset, no_clip_bounds=args.no_clip_bounds)]
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


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO)
    main()
