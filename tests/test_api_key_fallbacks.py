import unittest
from unittest.mock import patch

from geospatial.sentinel_client import SentinelClient


class FakeResponse:
    def __init__(self, status_code, payload):
        self.status_code = status_code
        self._payload = payload

    def raise_for_status(self):
        if self.status_code >= 400:
            raise RuntimeError("request failed")

    def json(self):
        return self._payload


class SentinelClientFallbackTests(unittest.TestCase):
    def test_uses_fallback_credentials_when_primary_auth_fails(self):
        client = SentinelClient(client_id="primary-id", client_secret="primary-secret")
        client._credential_pairs = [
            ("primary-id", "primary-secret"),
            ("fallback-id", "fallback-secret"),
        ]

        with patch("geospatial.sentinel_client.httpx.post", side_effect=[
            FakeResponse(401, {}),
            FakeResponse(200, {"access_token": "fallback-token"}),
        ]) as mock_post:
            token = client._get_token()

        self.assertEqual(token, "fallback-token")
        self.assertEqual(client.client_id, "fallback-id")
        self.assertEqual(client.client_secret, "fallback-secret")
        self.assertEqual(mock_post.call_count, 2)


if __name__ == "__main__":
    unittest.main()
