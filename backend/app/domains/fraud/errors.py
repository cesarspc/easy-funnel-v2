"""Fraud domain exceptions."""


class FraudCheckError(Exception):
    """Base class for fraud check errors."""

    def __init__(self, message: str) -> None:
        super().__init__(message)


class FraudValidationError(FraudCheckError):
    """Field-specific validation failure on an Administrator-editable fraud
    setting (Requirements 6.20-6.24). Maps to 422; the active configuration is
    never replaced by a rejected value."""

    def __init__(self, field: str, message: str) -> None:
        super().__init__(message)
        self.field = field
        self.message = message


class DuplicateBlacklistEntryError(FraudCheckError):
    """Raised when a Manual_Blacklist value already exists for the same entry
    type (Requirement 6.7). Maps to 409; the existing entry is left unchanged."""

    def __init__(self, entry_type: str, value_normalized: str) -> None:
        super().__init__(f"A {entry_type} blacklist entry for this value already exists.")
        self.entry_type = entry_type
        self.value_normalized = value_normalized


class DuplicateGeoIpRuleError(FraudCheckError):
    """Raised when a GeoIP_Rule already exists for a location code (the
    `geoip_rules_location_code_key` unique index). Maps to 409."""

    def __init__(self, location_code: str) -> None:
        super().__init__(f"A rule for location '{location_code}' already exists.")
        self.location_code = location_code


class ConfigNotFoundError(FraudCheckError):
    """Raised when fraud configuration is not found."""

    def __init__(self) -> None:
        super().__init__("Fraud configuration not found")


class BlacklistEntryNotFoundError(FraudCheckError):
    """Raised when a blacklist entry is not found."""

    def __init__(self, entry_id: int) -> None:
        self.entry_id = entry_id
        super().__init__(f"Blacklist entry {entry_id} not found")


class GeoIpRuleNotFoundError(FraudCheckError):
    """Raised when a GeoIP rule is not found."""

    def __init__(self, rule_id: int) -> None:
        self.rule_id = rule_id
        super().__init__(f"GeoIP rule {rule_id} not found")
