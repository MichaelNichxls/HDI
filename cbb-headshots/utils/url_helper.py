import csv

from playwright.sync_api import sync_playwright


def main() -> None:
    with open("genius.csv") as f:
        genius = {row["Genius"]: row for row in csv.DictReader(f)}
    with (
        sync_playwright() as p,
        p.chromium.launch(headless=False) as browser,
        browser.new_page() as page,
    ):
        page.goto("https://www.google.com")
        for k in genius.keys():
            search = page.locator("textarea[name='q']")
            search.fill(f"{k} 2024-25 Men's Basketball Roster")
            search.press("Enter")
            results = page.locator("#search a")
            url = (
                results.first.get_attribute("href")
                .replace("2024-25", "{season_42}")
                .replace("2024-2025", "{season_44}")
                .replace("2425", "{season_22}")
                .replace("2024", "{season_4}")
            )
            print(url)


if __name__ == "__main__":
    main()
