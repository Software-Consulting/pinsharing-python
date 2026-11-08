import io
import json
import unittest
from urllib.error import HTTPError, URLError
from urllib.parse import parse_qs, urlparse

from pinsharing import PinSharingClient, PinSharingError


def response(data):
    return io.BytesIO(json.dumps(data).encode())


def http_error(status, body, headers=None):
    return HTTPError("https://api.pinsharing.com/v1/geocode", status, "failed", headers or {}, io.BytesIO(json.dumps(body).encode()))


class FakeOpener:
    def __init__(self, *items):
        self.items = list(items)
        self.requests = []

    def open(self, request, timeout):
        self.requests.append((request, timeout))
        item = self.items.pop(0)
        if isinstance(item, Exception):
            raise item
        return response(item)


class ClientTests(unittest.TestCase):
    def test_geocode_uses_header_and_geojson(self):
        fc = {"type": "FeatureCollection", "features": [{"geometry": {"coordinates": [-88.35, 41.68]}}], "attribution": "© OpenStreetMap contributors"}
        opener = FakeOpener(fc)
        client = PinSharingClient("secret", opener=opener)
        self.assertEqual(client.geocode(" Oswego "), fc)
        request, timeout = opener.requests[0]
        self.assertEqual(timeout, 30)
        self.assertEqual(urlparse(request.full_url).path, "/v1/geocode")
        self.assertEqual(parse_qs(urlparse(request.full_url).query), {"q": ["Oswego"], "limit": ["1"]})
        self.assertEqual(request.get_header("Authorization"), "Bearer secret")
        self.assertEqual(request.get_header("X-ps-client"), "python/0.1.0")
        self.assertEqual(request.get_header("User-agent"), "PinSharing-Python/0.1.0")
        self.assertNotIn("secret", request.full_url)
        self.assertNotIn("secret", repr(client))

    def test_reverse_and_whoami(self):
        opener = FakeOpener({"account": "test"}, {"type": "FeatureCollection", "features": []})
        client = PinSharingClient("secret", opener=opener)
        self.assertEqual(client.whoami()["account"], "test")
        self.assertEqual(client.reverse(41.68, -88.35)["features"], [])
        self.assertEqual(parse_qs(urlparse(opener.requests[1][0].full_url).query), {"lat": ["41.68"], "lon": ["-88.35"], "limit": ["1"]})

    def test_retries_rate_limit_but_not_monthly_cap(self):
        delays = []
        opener = FakeOpener(http_error(429, {"error": "slow_down"}, {"Retry-After": "2"}), {"features": []})
        self.assertEqual(PinSharingClient("secret", opener=opener, sleep=delays.append).geocode("Oswego"), {"features": []})
        self.assertEqual(delays, [2])
        self.assertEqual(len(opener.requests), 2)
        opener = FakeOpener(http_error(429, {"error": "monthly_cap_reached", "message": "key=secret"}))
        with self.assertRaises(PinSharingError) as cm:
            PinSharingClient("secret", opener=opener, sleep=delays.append).geocode("Oswego")
        self.assertEqual(cm.exception.code, "monthly_cap_reached")
        self.assertNotIn("secret", str(cm.exception))
        self.assertEqual(len(opener.requests), 1)

    def test_bad_key_and_network_errors_hide_details(self):
        for item, code in [(http_error(401, {"message": "secret"}), "http_error"), (URLError("secret"), "network_error")]:
            with self.subTest(item=item):
                with self.assertRaises(PinSharingError) as cm:
                    PinSharingClient("secret", opener=FakeOpener(item)).geocode("Oswego")
                self.assertEqual(cm.exception.code, code)
                self.assertNotIn("secret", str(cm.exception))

    def test_invalid_retry_after_is_bounded(self):
        delays = []
        opener = FakeOpener(http_error(429, {"error": "slow_down"}, {"Retry-After": "NaN"}), {"features": []})
        PinSharingClient("secret", opener=opener, sleep=delays.append).geocode("Oswego")
        self.assertEqual(delays, [1])

    def test_validation_and_batch_cap_before_request(self):
        opener = FakeOpener({"features": []})
        client = PinSharingClient("secret", opener=opener)
        for action in [lambda: client.geocode(""), lambda: client.geocode("x", limit=21), lambda: client.reverse(91, 0), lambda: client.reverse(float("nan"), 0), lambda: client.geocode_many(["a", "b"], max_rows=1)]:
            with self.assertRaises(ValueError):
                action()
        self.assertEqual(opener.requests, [])
        self.assertEqual(client.geocode_many([" ", "Oswego", None]), [None, {"features": []}, None])
        self.assertEqual(len(opener.requests), 1)


if __name__ == "__main__":
    unittest.main()
