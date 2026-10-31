import argparse
from unittest.mock import patch

import pytest

from opspilot.cli import local_api_origin, main


@pytest.mark.parametrize(
    "url",
    [
        "http://127.0.0.1:8080@evil.example",
        "http://127.0.0.1:8080@evil.example/path",
        "http://user:password@127.0.0.1:8080",
        "http://127.0.0.1.evil.example:8080",
        "http://127.0.0.1:8080/path",
        "http://127.0.0.1:8080?target=evil",
        "http://127.0.0.1:8080#fragment",
        "https://127.0.0.1:8080",
        "http://127.0.0.1:99999",
        "http://127.0.0.1",
        "http://127.0.0.1:0",
    ],
)
def test_reject_url_authority_and_suffix(url):
    with pytest.raises(argparse.ArgumentTypeError):
        local_api_origin(url)


@pytest.mark.parametrize("url", ["http://127.0.0.1:8080", "http://127.0.0.1:8080/"])
def test_canonical_local_origin(url):
    assert local_api_origin(url) == "http://127.0.0.1:8080"


def test_bad_url_never_sends_credentials(monkeypatch):
    monkeypatch.setenv("OPSPILOT_TOKEN", "synthetic-credential")
    monkeypatch.setattr(
        "sys.argv", ["opspilot", "run", "logs", "--url", "http://127.0.0.1:8080@evil.example"]
    )
    with patch("opspilot.cli.httpx.post") as post, pytest.raises(SystemExit) as error:
        main()
    assert error.value.code == 2
    post.assert_not_called()
