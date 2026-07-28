"""GeoIP resolver using bundled MaxMind GeoLite2 database (Requirement 6.16-6.18).

Resolves request IP through the locally bundled GeoLite2 database without
any external geolocation API. Returns:
- Resolved location (country/region)
- 'unresolved' if address not in database
- 'unavailable' if database cannot be read

The database path comes from settings and can be updated by the in-instance
GeoIpUpdateTask (task 22.2).
"""

from __future__ import annotations

import contextlib
import os
from functools import lru_cache
from typing import Any

from app.core.settings import Settings, get_settings


class GeoIpResolver:
    """Resolve IP addresses to locations using bundled GeoLite2 database."""

    def __init__(self, settings: Settings | None = None):
        self._settings = settings or get_settings()
        self._geoip_reader: Any | None = None

    def _get_reader(self) -> Any | None:
        """Get or create the GeoIP reader.

        Returns None if database is unavailable.
        """
        if self._geoip_reader is not None:
            return self._geoip_reader

        try:
            import maxminddb

            db_path = self._settings.geoip_database_path
            if not os.path.exists(db_path):
                return None

            self._geoip_reader = maxminddb.open_database(db_path, maxminddb.MODE_AUTO)
            return self._geoip_reader

        except Exception:
            return None

    def resolve(self, ip_address: str) -> tuple[str | None, str | None, str]:
        """Resolve an IP address to country/region.

        Returns:
            Tuple of (country_code, region_code, status)
            - status is 'resolved', 'unresolved', or 'unavailable'
        """
        reader = self._get_reader()

        if reader is None:
            return None, None, "unavailable"

        try:
            # Try to look up the IP
            result = reader.get(ip_address)

            if result is None:
                return None, None, "unresolved"

            # Extract country and region
            country = None
            region = None

            if "country" in result and "iso_code" in result["country"]:
                country = result["country"]["iso_code"]

            if "subdivisions" in result and result["subdivisions"]:
                # Get the first subdivision (usually most specific)
                subdiv = result["subdivisions"][0]
                if "iso_code" in subdiv:
                    region = subdiv["iso_code"]

            return country, region, "resolved"

        except Exception:
            return None, None, "unavailable"
        finally:
            # Don't close the reader - keep it open for reuse
            pass

    def close(self) -> None:
        """Close the GeoIP database connection."""
        if self._geoip_reader is not None:
            with contextlib.suppress(Exception):
                self._geoip_reader.close()
            self._geoip_reader = None


@lru_cache
def get_geoip_resolver() -> GeoIpResolver:
    """FastAPI dependency returning the process-wide GeoIP resolver.

    Cached so the bundled GeoLite2 database is opened once per process rather
    than reopened on every submission.
    """
    return GeoIpResolver(get_settings())
