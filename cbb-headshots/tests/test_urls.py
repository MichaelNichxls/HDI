import re

import pytest
from playwright.sync_api import Page, expect

from headshots import SEASON


@pytest.mark.parametrize("species", ["URL", "URLW"])
def test_url_is_valid(page: Page, genius: dict[str, str], species: str):
    if not genius[species]:
        pytest.skip()
    
    url = genius[species].format(**SEASON)
    page.goto(url, wait_until="domcontentloaded")
    expect(page).to_have_url(re.compile(rf"^{re.escape(url)}/?$"))