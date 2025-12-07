import argparse
import logging
import os
import re
import shutil
import tempfile
from urllib.parse import (
    parse_qs,
    unquote,
    urlencode,
    urljoin,
    urlparse,
    urlunparse
)
from urllib.request import Request, urlopen

import cv2
# TODO: import Credentials
from google.oauth2.service_account import Credentials
from googleapiclient.discovery import build
from googleapiclient.http import MediaFileUpload
import mediapipe as mp
# from mediapipe import tasks
from mediapipe.tasks import python as tasks
from mediapipe.tasks.python import vision
import numpy as np
from selenium import webdriver
# TODO: *?
# from selenium.common.exceptions import (
#     ElementClickInterceptedException,
#     StaleElementReferenceException,
#     TimeoutException
# )
from selenium.common.exceptions import ElementNotInteractableException
from selenium.webdriver.common.action_chains import ActionChains
from selenium.webdriver.common.by import By
from selenium.webdriver.support import expected_conditions as EC
# TODO: support.ui
from selenium.webdriver.support.select import Select
from selenium.webdriver.support.wait import WebDriverWait
# from tenacity import *

# TODO: remove main

LOGGER = logging.getLogger(__name__)
# RETRY_KWARGS = {
#     "stop": stop_after_attempt(3),
#     "retry": retry_if_exception_type((ElementClickInterceptedException, StaleElementReferenceException, TimeoutException)),
#     "after": after_log(LOGGER, logging.ERROR),
#     "reraise": True
# }
REGEXES = {
    "number": re.compile(r"\d{1,2}"),
    "url": re.compile(r"""url\(['"](.*?)['"]\);?""")
}
TOP_EXTEND_RATIO = .7
BOTTOM_EXTEND_RATIO = .2

def main() -> None:
    # TODO: rename
    # TODO: choices; nargs
    # TODO: -w for WBB?
    parser = argparse.ArgumentParser(formatter_class=argparse.ArgumentDefaultsHelpFormatter)
    parser.add_argument("genius", help="")
    parser.add_argument("-c", "--credentials", default="service_account.json", help="path of google service account json file")
    parser.add_argument("-i", "--id", default=os.getenv("GOOGLE_SPREADSHEET_ID"), help="id of google spreadsheet; required if GOOGLE_SPREADSHEET_ID environment variable is not specified")
    parser.add_argument("-o", "--output", default="Sheet1", help="name of google sheet to write the data to")

    args = parser.parse_args()
    # TODO: simplify
    W = args.genius.endswith("WBB")
    args.genius = args.genius.removesuffix("WBB").rstrip()

    credentials = Credentials.from_service_account_file(
        args.credentials,
        scopes=[
            "https://www.googleapis.com/auth/spreadsheets.readonly",
            "https://www.googleapis.com/auth/drive"
        ]
    )
    sheets = build("sheets", "v4", credentials=credentials)
    drive = build("drive", "v3", credentials=credentials)

    # TODO: change range in other projects
    genius_key = {
        genius: {
            header: v
            for header, v in zip(range["values"][0][1:], vs)
        }
        for range in sheets.spreadsheets().values().batchGet(
            spreadsheetId=args.id,
            ranges=["Genius Names List!A:C"]
        ).execute()["valueRanges"]
        for genius, *vs in range["values"][1:]
    }
    geniuses = {
        genius: {
            header: v
            for header, v in zip(range["values"][0][1:], vs)
        }
        for range in sheets.spreadsheets().values().batchGet(
            spreadsheetId=args.id,
            ranges=[
                "Genius Specific Team Names!A2:F",
                "Genius Specific Team Names!G2:K",
                "Genius Specific Team Names!L2:O"
            ]
        ).execute()["valueRanges"]
        for genius, *vs in range["values"][1:]
    }

    assert args.genius in genius_key

    # TODO: id
    id = drive.files().list(
        supportsAllDrives=True,
        includeItemsFromAllDrives=True,
        q=f""""{os.getenv("_MBB_ID") if not W else os.getenv("_WBB_ID")}" in parents and name="{args.genius}" and trashed=false"""
    ).execute()["files"][0]["id"]
    # TODO: create folder if not exists

    assert id

    driver_options = webdriver.ChromeOptions()
    driver_options.add_argument("--headless=new")
    driver_options.add_argument("--window-size=1920,1080")
    # driver_options.add_argument("--log-level=3")

    from selenium.webdriver.remote.webdriver import WebDriver
    from selenium.webdriver.remote.webelement import WebElement
    def _n(el: WebElement):
        if not el:
            return None
        elif text := el.get_attribute("innerText"):
            return REGEXES["number"].search(text).group()
        else:
            return None
    
    def _u(el: WebElement, d: WebDriver):
        if not el:
            return None
        elif (url := el.value_of_css_property("background-image")) != "none":
            parsed = urlparse(REGEXES["url"].fullmatch(url).group(1))
        elif (url := el.get_attribute("data-src") or el.get_attribute("src")):
            parsed = urlparse(url)
        else:
            return None

        query = parse_qs(parsed.query)
        # TODO: simplify
        query.pop("width", None)
        query.pop("height", None)
        query.pop("max_width", None)
        query.pop("max_height", None)

        new_query = urlencode(query, doseq=True)
        cleaned = urlunparse(parsed._replace(query=new_query))

        if not parsed.scheme and not parsed.netloc:
            return urljoin(d.current_url, cleaned)

        if "url" in query:
            return unquote(query["url"][0])
        
        return cleaned

    URL = genius_key[args.genius]["Roster" if not W else "Roster WBB"].format(season="2025-26")
    with webdriver.Chrome(driver_options) as driver:
        wait = WebDriverWait(driver, 4)
        actions = ActionChains(driver)
        
        # TODO: config
        # TODO: ?view=3
        LOGGER.info("found %s", URL)
        driver.get(URL)

        # if rejects := wait.until(EC.presence_of_all_elements_located((By.CSS_SELECTOR, "button.iubenda-cs-reject-btn"))):
        #     rejects[0].click()

        # # TODO: generalize
        # if selections := driver.find_elements(By.CSS_SELECTOR, "#sidearm-roster-select-template-dropdown"):
        #     Select(selections[0]).select_by_visible_text("Roster View - Cards") # select_by_value("3")
        #     driver.find_element(By.CSS_SELECTOR, "#sidearm-roster-select-template-button").click()
        # elif selections := driver.find_elements(By.CSS_SELECTOR, "li.headshot > a"):
        #     selections[0].click()
        # elif selections := driver.find_elements(By.CSS_SELECTOR, "div.view"):
        #     selections[0].click()

        # TODO: simplify all
        players = wait.until(EC.any_of(
            # TODO: tags debatable
            EC.presence_of_all_elements_located((By.CSS_SELECTOR, "li.sidearm-roster-player")),
            EC.presence_of_all_elements_located((By.CSS_SELECTOR, "div#players .roster__item")),
            EC.presence_of_all_elements_located((By.CSS_SELECTOR, "div#listPanel > .s-person-card")),
            EC.presence_of_all_elements_located((By.CSS_SELECTOR, "[itemprop='athlete']")),
            EC.presence_of_all_elements_located((By.CSS_SELECTOR, "li.sidearm-roster-list-item")),
            EC.presence_of_all_elements_located((By.CSS_SELECTOR, "ul#sidearm-m-roster > li")),
            EC.presence_of_all_elements_located((By.CSS_SELECTOR, "ul#sidearm-f-roster > li")),
            EC.presence_of_all_elements_located((By.CSS_SELECTOR, "div.roster-players-cards > .roster-card")),
            EC.presence_of_all_elements_located((By.CSS_SELECTOR, "div.roster-players-cards > .roster-card-item")),
            EC.presence_of_all_elements_located((By.CSS_SELECTOR, "div.player-card-wrapper")),
            EC.presence_of_all_elements_located((By.CSS_SELECTOR, "ul.roster-players-list > li")),
            EC.presence_of_all_elements_located((By.CSS_SELECTOR, "div#players .player")),
            EC.presence_of_all_elements_located((By.CSS_SELECTOR, "div.roster__list_item"))
        ))

        # TODO: make auto/arg; elementnotinteractableexception
        try:
            for player in players:
                actions.scroll_to_element(player).perform()
        except ElementNotInteractableException:
            pass
        
        # TODO: simplify all
        player_data = [
            {
                "number": _n(
                    # TODO: card, list
                    (player.find_elements(By.CSS_SELECTOR, ".sidearm-roster-player-jersey-number")
                        or player.find_elements(By.CSS_SELECTOR, ".number")
                        or player.find_elements(By.CSS_SELECTOR, ".s-stamp__text")
                        or player.find_elements(By.CSS_SELECTOR, ".sidearm-roster-list-item-photo-number")
                        or player.find_elements(By.CSS_SELECTOR, ".sidearm-roster-player-jersey")
                        or player.find_elements(By.CSS_SELECTOR, ".roster-card__jersey-number")
                        or player.find_elements(By.CSS_SELECTOR, ".roster-item__number")
                        or player.find_elements(By.CSS_SELECTOR, ".roster-list-item__number")
                        or player.find_elements(By.CSS_SELECTOR, ".roster-list-item__jersey-number")
                        or player.find_elements(By.CSS_SELECTOR, ".roster-card-item__jersey-number")
                        or player.find_elements(By.CSS_SELECTOR, ".thumb span")
                        or [None]
                    )[0]
                ),
                "image": _u(
                    (player.find_elements(By.CSS_SELECTOR, ".sidearm-roster-player-image img")
                        or player.find_elements(By.CSS_SELECTOR, ".roster__image img")
                        or player.find_elements(By.CSS_SELECTOR, ".s-person-thumbnail img")
                        or player.find_elements(By.CSS_SELECTOR, ".image img")
                        or player.find_elements(By.CSS_SELECTOR, ".sidearm-roster-list-item-photo img")
                        or player.find_elements(By.CSS_SELECTOR, "div.sidearm-roster-player-image")
                        or player.find_elements(By.CSS_SELECTOR, "img.roster-card__image")
                        or player.find_elements(By.CSS_SELECTOR, "[itemprop='image'] ~ a img")
                        or player.find_elements(By.CSS_SELECTOR, ".player-image img")
                        or player.find_elements(By.CSS_SELECTOR, "img.roster-list-item__image")
                        or player.find_elements(By.CSS_SELECTOR, "img.roster-card-item__image")
                        or player.find_elements(By.CSS_SELECTOR, ".thumb img")
                        or [None]
                    )[0],
                    driver
                )
            }
            for player in players
        ]
        # TODO: vanderbilt, georgia tech wbb, sam houston wbb
        player_data[0]["number"] = player_data[0]["number"] or "0"

    # files = drive.files().list(
    #     supportsAllDrives=True,
    #     includeItemsFromAllDrives=True,
    #     q=f"'{id}' in parents and trashed=false"
    # ).execute()["files"]

    # for file in files:
    #     drive.files().delete(fileId=file["id"], supportsAllDrives=True).execute()
    #     LOGGER.info("deleted %s", file["name"])
    
    # TODO: handle zero (only one) in player_data
    # TODO: batch
    # TODO: http error 500
    for player in player_data:
        # TODO: log
        if not player["number"]:
            continue

        FILENAME = f"{geniuses[args.genius]["HDI" if not W else "HDIW"]}{player["number"].zfill(2)}pic.png"
        if not player["image"]:
            LOGGER.warning("no image for %s on %s", FILENAME, URL)
            continue

        # filename, _ = urlretrieve(player["image"])

        req = Request(player["image"], headers={"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64)"})
        with urlopen(req) as res:
            # TODO: delete
            with tempfile.NamedTemporaryFile(delete=False, suffix=".png") as temp:
                shutil.copyfileobj(res, temp)
                filename = temp.name

        image = cv2.imread(filename)
        mp_image = mp.Image(image_format=mp.ImageFormat.SRGB, data=cv2.cvtColor(image, cv2.COLOR_BGR2RGB))

        options = vision.FaceDetectorOptions(
            base_options=tasks.BaseOptions(model_asset_path="models/blaze_face_short_range.tflite"),
            running_mode=vision.RunningMode.IMAGE
        )
        with vision.FaceDetector.create_from_options(options) as detector:
            result = detector.detect(mp_image)

        if not result.detections:
            LOGGER.warning("no image for %s on %s", FILENAME, URL)
            continue

        # TODO: warn instead of assert
        assert len(result.detections) == 1

        # bbox = result.detections[0].bounding_box
        # x, y, w, h = bbox.origin_x, bbox.origin_y, bbox.width, bbox.height

        # y -= int(h * TOP_EXTEND_RATIO)
        # h = int(h * (1 + TOP_EXTEND_RATIO + BOTTOM_EXTEND_RATIO))

        # size = max(w, h)
        # cx, cy = x + w // 2, y + h // 2

        # x1, y1 = max(0, cx - size // 2), max(0, cy - size // 2)
        # x2, y2 = min(image.shape[1] - 1, x1 + size), min(image.shape[0] - 1, y1 + size)

        # crop = image[y1:y2, x1:x2]
        # h, w = crop.shape[:2]
        
        # size = max(w, h)
        # crop = cv2.resize(crop, (size, size))

        # # c = (size // 2, size // 2)
        # # r = size // 2

        # mask = np.zeros((size, size), np.uint8)
        # cv2.circle(mask, (size // 2, size // 2), size // 2, 255, -1)

        # result = cv2.bitwise_and(crop, crop, mask=mask)
        
        # image_bgra = cv2.cvtColor(result, cv2.COLOR_BGR2BGRA)
        # image_bgra[:, :, 3] = mask

        # # TODO: named temp file
        # cv2.imwrite(f".png", image_bgra)

        bbox = result.detections[0].bounding_box
        x, y, w, h = bbox.origin_x, bbox.origin_y, bbox.width, bbox.height

        # Expand vertically
        y -= int(h * TOP_EXTEND_RATIO)
        h = int(h * (1 + TOP_EXTEND_RATIO + BOTTOM_EXTEND_RATIO))

        # Target square size
        size = int(max(w, h))
        cx, cy = int(x + w / 2), int(y + h / 2)

        # Clamp the square region to stay within image
        half = size // 2
        x1 = cx - half
        y1 = cy - half
        x2 = x1 + size
        y2 = y1 + size

        # Shift inward if going out of bounds
        if x1 < 0:
            x2 -= x1  # move both edges right
            x1 = 0
        if y1 < 0:
            y2 -= y1  # move both edges down
            y1 = 0
        if x2 > image.shape[1]:
            diff = x2 - image.shape[1]
            x1 -= diff
            x2 = image.shape[1]
        if y2 > image.shape[0]:
            diff = y2 - image.shape[0]
            y1 -= diff
            y2 = image.shape[0]

        # Final clamp (in case we shifted past zero)
        x1 = max(0, x1)
        y1 = max(0, y1)
        x2 = min(image.shape[1], x2)
        y2 = min(image.shape[0], y2)

        # Enforce exact square dimensions
        final_w = x2 - x1
        final_h = y2 - y1
        side = min(final_w, final_h)
        x2 = x1 + side
        y2 = y1 + side

        # Crop
        crop = image[y1:y2, x1:x2].copy()

        # Validate
        h, w = crop.shape[:2]
        assert h == w

        # Circular mask
        mask = np.zeros((h, w), np.uint8)
        cv2.circle(mask, (w // 2, h // 2), w // 2, 255, -1)

        result = cv2.bitwise_and(crop, crop, mask=mask)
        image_bgra = cv2.cvtColor(result, cv2.COLOR_BGR2BGRA)
        image_bgra[:, :, 3] = mask

        cv2.imwrite(filename, image_bgra)
        drive.files().create(
            supportsAllDrives=True,
            media_body=MediaFileUpload(filename),
            body={
                "name": FILENAME,
                "parents": [id]
            }
        ).execute()
        LOGGER.info("created %s", FILENAME)
    else:
        LOGGER.info("finished %s", URL)

if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO)
    main()