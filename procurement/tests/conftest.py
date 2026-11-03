import json
import os
import sys

import pytest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))
FIX = os.path.join(os.path.dirname(__file__), "fixtures")
NOW = "2026-11-03T12:00:00+00:00"


def fixture(name):
    with open(os.path.join(FIX, name), encoding="utf-8") as f:
        return json.load(f)


@pytest.fixture
def fx():
    return fixture


class NoNetwork:
    """A client that fails the test if anything tries to use the network."""

    def __getattr__(self, name):
        raise AssertionError("network access attempted via client.%s" % name)
