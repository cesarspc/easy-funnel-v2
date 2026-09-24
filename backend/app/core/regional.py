"""Merchant-editable market conventions: locale, currency, time zone, phones.

These values live in the `store_settings` singleton and are edited under
Admin → Tienda. `DEFAULT_REGIONAL` is the only place the historical defaults
(Colombia) are spelled out; it seeds a fresh database through the `STORE_*`
bootstrap variables and mirrors the migration's column defaults.
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from datetime import date, datetime, tzinfo
from functools import lru_cache
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

_COUNTRY = re.compile(r"^[A-Z]{2}$")
_CURRENCY = re.compile(r"^[A-Z]{3}$")
_LOCALE = re.compile(r"^[a-z]{2,3}(-[A-Za-z0-9]{2,8})*$")
_CALLING_CODE = re.compile(r"^[1-9][0-9]{0,3}$")
_DIGITS = re.compile(r"\d")
PHONE_PATTERN_MAX_LENGTH = 100


class RegionalValidationError(ValueError):
    def __init__(self, field: str, message: str):
        self.field = field
        self.message = message
        super().__init__(message)


@dataclass(frozen=True)
class PhoneRules:
    """How buyer phone numbers are validated and canonicalized.

    `national_pattern` is a regular expression the national significant number
    (digits only, without the calling code) must fully match.
    """

    country_code: str
    national_pattern: str

    @property
    def compiled(self) -> re.Pattern[str]:
        return _compile_national_pattern(self.national_pattern)


@dataclass(frozen=True)
class RegionalConfig:
    country_code: str
    locale: str
    currency: str
    time_zone: str
    phone: PhoneRules

    @property
    def zone(self) -> tzinfo:
        return business_zone(self.time_zone)


DEFAULT_REGIONAL = RegionalConfig(
    country_code="CO",
    locale="es-CO",
    currency="COP",
    time_zone="America/Bogota",
    phone=PhoneRules(country_code="57", national_pattern=r"3[0-9]{9}"),
)


@lru_cache(maxsize=32)
def _compile_national_pattern(pattern: str) -> re.Pattern[str]:
    return re.compile(pattern)


@lru_cache(maxsize=32)
def business_zone(name: str) -> tzinfo:
    """Return the IANA time zone used for the merchant's business calendar."""
    return ZoneInfo(name)


def business_today(time_zone: str, *, now: datetime | None = None) -> date:
    """Return the merchant's calendar date for an instant (now by default)."""
    zone = business_zone(time_zone)
    instant = now or datetime.now(zone)
    if instant.tzinfo is None:
        instant = instant.replace(tzinfo=zone)
    return instant.astimezone(zone).date()


def validate_country_code(value: str) -> str:
    code = (value or "").strip().upper()
    if not _COUNTRY.fullmatch(code):
        raise RegionalValidationError("countryCode", "Use an ISO 3166-1 alpha-2 country code.")
    return code


def validate_currency(value: str) -> str:
    code = (value or "").strip().upper()
    if not _CURRENCY.fullmatch(code):
        raise RegionalValidationError("currency", "Use an ISO 4217 currency code.")
    return code


def validate_locale(value: str) -> str:
    tag = (value or "").strip()
    if len(tag) > 35 or not _LOCALE.fullmatch(tag):
        raise RegionalValidationError("locale", "Use a BCP 47 locale such as es-CO.")
    return tag


def validate_time_zone(value: str) -> str:
    name = (value or "").strip()
    if not name or len(name) > 64:
        raise RegionalValidationError("timeZone", "Use an IANA time zone such as America/Bogota.")
    try:
        business_zone(name)
    except (ZoneInfoNotFoundError, ValueError) as exc:
        raise RegionalValidationError(
            "timeZone", "Use an IANA time zone such as America/Bogota."
        ) from exc
    return name


def validate_phone_country_code(value: str) -> str:
    code = (value or "").strip().lstrip("+")
    if not _CALLING_CODE.fullmatch(code):
        raise RegionalValidationError("phoneCountryCode", "Use a 1-4 digit calling code.")
    return code


def validate_phone_national_pattern(value: str) -> str:
    pattern = (value or "").strip()
    if not pattern or len(pattern) > PHONE_PATTERN_MAX_LENGTH:
        raise RegionalValidationError(
            "phoneNationalPattern",
            f"Provide a regular expression of at most {PHONE_PATTERN_MAX_LENGTH} characters.",
        )
    try:
        _compile_national_pattern(pattern)
    except re.error as exc:
        raise RegionalValidationError(
            "phoneNationalPattern", "The regular expression is not valid."
        ) from exc
    return pattern


def national_phone_digits(raw: str, rules: PhoneRules) -> str | None:
    """Return the national number for `raw`, or None when it is not valid.

    Formatting characters are ignored. The calling code is optional: a value
    that already matches the national pattern is accepted as-is, otherwise a
    leading calling code is stripped once before matching.
    """
    digits = "".join(_DIGITS.findall(raw)) if raw else ""
    pattern = rules.compiled
    if pattern.fullmatch(digits):
        return digits
    if digits.startswith(rules.country_code):
        national = digits[len(rules.country_code):]
        if pattern.fullmatch(national):
            return national
    return None
