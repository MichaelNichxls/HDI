import pytest
from playwright.sync_api import BrowserContext

from headshots import SEASON, get_headshots


@pytest.mark.parametrize("species", ["URL", "URLW"])
def test_headshot_locators_are_valid(context: BrowserContext, genius: dict[str, str], species: str):
    if not genius[species]:
        pytest.skip()

    results = [*get_headshots(context, genius[species].format(**SEASON))]

    assert results
    assert not all(not r["jersey"] for r in results)
    assert not all(not r["headshot"] for r in results)
