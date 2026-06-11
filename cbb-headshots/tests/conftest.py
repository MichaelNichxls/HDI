import csv

import pytest
from playwright.sync_api import BrowserContext


def pytest_generate_tests(metafunc: pytest.Metafunc):
    if "genius" in metafunc.fixturenames:
        with open(metafunc.config.rootpath / "genius.csv") as f:
            genius = [*csv.DictReader(f)]
            metafunc.parametrize("genius", genius, ids=[g["Genius"] for g in genius])


@pytest.fixture(scope="session")
def browser_context_args(browser_context_args):
    return {
        **browser_context_args,
        "viewport": {"width": 1920, "height": 1080},
    }


@pytest.fixture
def context(context: BrowserContext):
    context.set_default_timeout(10000)
    yield context
