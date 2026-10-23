import pytest
from scripts.testing.scenario import play_scenario

pytestmark = pytest.mark.e2e


def test_game_lifecycle_over_real_http(api_url):
    play_scenario(api_url, steps=True)
