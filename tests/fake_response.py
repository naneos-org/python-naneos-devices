"""A stand-in for requests.Response, with just what the uploader reads."""

import json


class FakeResponse:
    def __init__(self, status_code: int = 200, text: str = "") -> None:
        self.status_code = status_code
        self.text = text

    def json(self):
        return json.loads(self.text)  # raises ValueError for a body that is not JSON


def wrapped(status: int, message: str) -> FakeResponse:
    """What the API gateway sends when the lambda answers {"statusCode": status, ...}."""
    body = json.dumps({"message": message})
    return FakeResponse(200, json.dumps({"statusCode": status, "body": body}))
