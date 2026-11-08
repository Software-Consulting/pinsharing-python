"""Small, dependency-free client for PinSharing's GeoJSON endpoints."""

from __future__ import annotations

import json
import math
import time
from urllib.error import HTTPError, URLError
from urllib.parse import urlencode
from urllib.request import HTTPRedirectHandler, Request, build_opener


_BASE = "https://api.pinsharing.com"
_VERSION = "0.1.0"


class PinSharingError(Exception):
    """A PinSharing request failed; credential values are never included."""

    def __init__(self, status: int | None, code: str, message: str):
        self.status = status
        self.code = code
        super().__init__(message)


class _NoRedirect(HTTPRedirectHandler):
    def redirect_request(self, request, fp, code, msg, headers, newurl):
        return None


class PinSharingClient:
    """Use a server-side API key; results are GeoJSON FeatureCollections."""

    def __init__(self, api_key: str, *, timeout: float = 30.0, opener=None, sleep=time.sleep):
        if not isinstance(api_key, str) or not api_key.strip():
            raise ValueError("A PinSharing API key is required.")
        if not math.isfinite(timeout) or timeout <= 0:
            raise ValueError("timeout must be positive and finite")
        self._api_key = api_key.strip()
        self._timeout = timeout
        self._opener = opener or build_opener(_NoRedirect())
        self._sleep = sleep

    def __repr__(self) -> str:
        return "PinSharingClient(api_key=<redacted>)"

    @staticmethod
    def _error(status: int | None, raw: bytes) -> PinSharingError:
        try:
            payload = json.loads(raw[:65536])
        except (ValueError, UnicodeDecodeError):
            payload = {}
        if not isinstance(payload, dict):
            payload = {}
        code = payload.get("error") if isinstance(payload.get("error"), str) else "http_error"
        if status == 401:
            message = "PinSharing did not accept the API key."
        elif status == 403:
            message = "This API key is not permitted for this request."
        elif status == 429 and code == "monthly_cap_reached":
            message = "The monthly address lookup cap is used up."
        elif status == 429:
            message = "PinSharing is rate limiting requests."
        elif status is not None and status >= 500:
            message = "PinSharing is temporarily unavailable."
        else:
            message = "PinSharing rejected the request."
        return PinSharingError(status, code, message)

    def _get(self, path: str, params: dict[str, str | int | float]) -> dict:
        url = f"{_BASE}{path}?{urlencode(params)}" if params else f"{_BASE}{path}"
        request = Request(url, headers={
            "Authorization": f"Bearer {self._api_key}",
            "Accept": "application/json",
            "X-PS-Client": f"python/{_VERSION}",
            "User-Agent": f"PinSharing-Python/{_VERSION}",
        })
        attempts = 0
        while True:
            try:
                with self._opener.open(request, timeout=self._timeout) as response:
                    payload = json.load(response)
                if not isinstance(payload, dict):
                    raise PinSharingError(None, "invalid_response", "PinSharing returned invalid JSON.")
                return payload
            except HTTPError as exc:
                raw = exc.read(65536)
                error = self._error(exc.code, raw)
                if exc.code == 429 and error.code != "monthly_cap_reached" and attempts < 2:
                    attempts += 1
                    try:
                        delay = float(exc.headers.get("Retry-After", "1"))
                    except (ValueError, TypeError):
                        delay = 1.0
                    if not math.isfinite(delay):
                        delay = 1.0
                    self._sleep(min(max(delay, 0.0), 10.0))
                    continue
                raise error from None
            except URLError:
                raise PinSharingError(None, "network_error", "Could not reach PinSharing.") from None
            except (ValueError, UnicodeDecodeError):
                raise PinSharingError(None, "invalid_response", "PinSharing returned invalid JSON.") from None

    def whoami(self) -> dict:
        """Check the key without consuming an address lookup."""
        return self._get("/v1/whoami", {})

    def geocode(self, address: str, *, limit: int = 1, language: str | None = None) -> dict:
        """Find places matching an address; returns GeoJSON with attribution."""
        if not isinstance(address, str) or not address.strip() or len(address.strip()) > 300:
            raise ValueError("address must contain 1 to 300 characters")
        if not isinstance(limit, int) or isinstance(limit, bool) or not 1 <= limit <= 20:
            raise ValueError("limit must be an integer from 1 to 20")
        params: dict[str, str | int] = {"q": address.strip(), "limit": limit}
        if language:
            params["lang"] = language
        return self._get("/v1/geocode", params)

    def reverse(self, latitude: float, longitude: float, *, limit: int = 1) -> dict:
        """Find places near WGS84 latitude and longitude; returns GeoJSON."""
        try:
            lat, lon = float(latitude), float(longitude)
        except (TypeError, ValueError):
            raise ValueError("latitude and longitude must be finite numbers") from None
        if not math.isfinite(lat) or not math.isfinite(lon) or not -90 <= lat <= 90 or not -180 <= lon <= 180:
            raise ValueError("latitude must be -90 to 90 and longitude -180 to 180")
        if not isinstance(limit, int) or isinstance(limit, bool) or not 1 <= limit <= 20:
            raise ValueError("limit must be an integer from 1 to 20")
        return self._get("/v1/reverse", {"lat": lat, "lon": lon, "limit": limit})

    def geocode_many(self, addresses, *, max_rows: int = 500) -> list[dict | None]:
        """Geocode sequentially, preserving input order; blanks return None."""
        if not isinstance(max_rows, int) or isinstance(max_rows, bool) or max_rows < 1:
            raise ValueError("max_rows must be a positive integer")
        rows = list(addresses)
        if len(rows) > max_rows:
            raise ValueError(f"Refusing to geocode more than {max_rows} rows")
        return [self.geocode(value) if isinstance(value, str) and value.strip() else None for value in rows]
