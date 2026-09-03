import pytest

from saiclawbot.llm import _sdk_base_url


@pytest.mark.parametrize(
    ("configured", "expected"),
    [
        (None, None),
        ("https://api.anthropic.com", "https://api.anthropic.com"),
        ("https://opencode.ai/zen/go/v1", "https://opencode.ai/zen/go"),
        ("https://opencode.ai/zen/go/v1/", "https://opencode.ai/zen/go"),
    ],
)
def test_sdk_base_url_removes_api_version_for_anthropic_sdk(configured, expected):
    assert _sdk_base_url(configured) == expected
