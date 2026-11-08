# PinSharing Python client

Open-source package for geocoding and reverse geocoding in Python notebooks and data pipelines. It has no runtime dependencies and sends the key in an HTTPS Authorization header, not a URL. Results are GeoJSON FeatureCollections with attribution and storage terms from the API.

```python
from pinsharing import PinSharingClient

client = PinSharingClient("YOUR_SERVER_SIDE_KEY")
client.whoami()  # checks the key without a metered address lookup
places = client.geocode("Oswego, Illinois", limit=3)
nearby = client.reverse(41.68, -88.35)
rows = client.geocode_many(["Oswego, Illinois", "Yorkville, Illinois"])
```

Use a server-side key without a website restriction. Keep the key in your credential manager or process environment, not notebook source, committed files, or shared output. The client keeps it out of its `repr`, URL, and exception messages. API responses retain the service's OpenStreetMap attribution and storage terms; follow those terms when persisting results. Each nonblank geocode/reverse lookup is metered. `geocode_many` runs sequentially, preserves input order, skips blanks, and refuses more than 500 rows by default. It retries transient 429 responses twice, respects `Retry-After` up to 10 seconds, and does not retry a monthly cap.

## Test and release status

Run `python3 -m unittest discover -s test -v` from this folder with `PYTHONPATH=src`. Before a PyPI release, build a wheel and source distribution, install the wheel in a clean environment, run the live geocode/reverse/auth/quota checks with a limited test key, and verify the PyPI package name and publisher account. No PyPI upload has been made. Forgejo is self-hosted, so its CI cannot use PyPI's listed Trusted Publishers; use a project-scoped PyPI token held outside git if publishing from Forgejo.
