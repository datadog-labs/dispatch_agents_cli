"""Pytest configuration and fixtures for CLI tests."""

import pytest

from dispatch_cli.logger import set_logger


@pytest.fixture(autouse=True)
def init_logger():
    """Initialize the logger before each test.

    The CLI logger is a global singleton that must be initialized
    before any utility functions can use it. This fixture ensures
    it's set up for every test automatically.
    """
    set_logger(verbose=False)
    yield
