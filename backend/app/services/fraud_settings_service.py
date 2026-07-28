"""FraudSettingsService: Administrator-editable fraud configuration.

Composes `app.domains.fraud.settings_validation` with the fraud repositories
and the audit log, covering the mutations the Admin Dashboard's fraud screen
performs (Requirement 8.10):

- Fraud_Configuration read/update (Requirements 6.20, 6.21, 6.24)
- Manual_Blacklist add/remove with normalization (Requirements 6.6-6.8, 6.24)
- GeoIP_Rule create/update/delete (Requirements 6.22, 6.23)

Every mutation is validated in full before any write, so a rejected value
leaves the active configuration untouched, and every mutation records the
Administrator identity, action, target, and result in Audit_History
(Requirement 10.10).

Removing a Manual_Blacklist entry or a GeoIP_Rule deletes only the rule row:
`fraud_flags` already written for past orders are historical evidence and are
never touched (Requirement 6.8).
"""

from __future__ import annotations

from prisma import Prisma
from prisma.models import BlacklistEntry, FraudConfig, GeoIpRule

from app.db.repositories import (
    AuditLogRepository,
    BlacklistEntryRepository,
    FraudConfigRepository,
    GeoIpRuleRepository,
)
from app.domains.fraud.errors import (
    BlacklistEntryNotFoundError,
    ConfigNotFoundError,
    DuplicateBlacklistEntryError,
    DuplicateGeoIpRuleError,
    GeoIpRuleNotFoundError,
)
from app.domains.fraud.settings_validation import (
    validate_blacklist_entry_type,
    validate_blacklist_ip,
    validate_blacklist_reason,
    validate_duplicate_match_fields,
    validate_duplicate_window_hours,
    validate_geoip_action,
    validate_location_code,
    validate_rate_limit_max,
    validate_rate_limit_window_minutes,
)
from app.domains.orders.normalization import normalize_colombian_phone_key

ENTRY_TYPE_PHONE = "phone"


class FraudSettingsService:
    def __init__(self, db: Prisma) -> None:
        self._db = db

    # --- Fraud configuration -------------------------------------------------

    async def get_config(self) -> FraudConfig:
        """Return the singleton Fraud_Configuration row."""
        config = await FraudConfigRepository(self._db).get()
        if config is None:
            raise ConfigNotFoundError()
        return config

    async def update_config(
        self,
        *,
        duplicate_window_hours: int | None = None,
        duplicate_match_fields: list[str] | None = None,
        rate_limit_max: int | None = None,
        rate_limit_window_minutes: int | None = None,
        actor: str,
    ) -> FraudConfig:
        """Update the Fraud_Configuration; omitted fields keep their stored value.

        Presence is decided by `None`, not truthiness, so an explicit invalid
        value such as `0` is reported as a field error instead of silently
        falling back to the stored one (Requirement 6.24).
        """
        async with self._db.tx() as tx:
            configs = FraudConfigRepository(tx)
            audit_log = AuditLogRepository(tx)

            current = await configs.get()
            if current is None:
                raise ConfigNotFoundError()

            data = {}
            if duplicate_window_hours is not None:
                data["duplicateWindowHours"] = validate_duplicate_window_hours(
                    duplicate_window_hours
                )
            if duplicate_match_fields is not None:
                data["duplicateMatchFields"] = validate_duplicate_match_fields(
                    duplicate_match_fields
                )
            if rate_limit_max is not None:
                data["rateLimitMax"] = validate_rate_limit_max(rate_limit_max)
            if rate_limit_window_minutes is not None:
                data["rateLimitWindowMinutes"] = validate_rate_limit_window_minutes(
                    rate_limit_window_minutes
                )

            if not data:
                return current

            updated = await configs.update(data)  # type: ignore[arg-type]
            if updated is None:
                raise ConfigNotFoundError()

            await audit_log.record(
                actor=actor,
                action="fraud.config.update",
                target_type="fraud_config",
                target_id=str(current.id),
                result="success",
            )
            return updated

    # --- Manual blacklist ----------------------------------------------------

    async def list_blacklist(self) -> list[BlacklistEntry]:
        """Return every Manual_Blacklist entry."""
        return await BlacklistEntryRepository(self._db).list_all()

    async def add_blacklist_entry(
        self, *, entry_type: str, value: str, reason: str, actor: str
    ) -> BlacklistEntry:
        """Add a Manual_Blacklist entry after normalizing its value.

        Phone values are normalized to the same key the fraud checks compare
        against, and IP values to their canonical form, so an entry matches
        regardless of the notation it was typed in (Requirement 6.5, 6.6).
        """
        entry_type = validate_blacklist_entry_type(entry_type)
        reason = validate_blacklist_reason(reason)
        if entry_type == ENTRY_TYPE_PHONE:
            value_normalized = normalize_colombian_phone_key(value)
        else:
            value_normalized = validate_blacklist_ip(value)

        async with self._db.tx() as tx:
            entries = BlacklistEntryRepository(tx)
            audit_log = AuditLogRepository(tx)

            if await entries.find(entry_type, value_normalized) is not None:
                raise DuplicateBlacklistEntryError(entry_type, value_normalized)

            entry = await entries.create(
                {
                    "entryType": entry_type,
                    "valueNormalized": value_normalized,
                    "reason": reason,
                }
            )
            await audit_log.record(
                actor=actor,
                action="fraud.blacklist.add",
                target_type="blacklist_entry",
                target_id=str(entry.id),
                result="success",
            )
            return entry

    async def remove_blacklist_entry(self, entry_id: int, *, actor: str) -> None:
        """Remove a Manual_Blacklist entry, preserving historical Fraud_Flags."""
        async with self._db.tx() as tx:
            entries = BlacklistEntryRepository(tx)
            audit_log = AuditLogRepository(tx)

            deleted = await entries.delete(entry_id)
            if deleted is None:
                raise BlacklistEntryNotFoundError(entry_id)

            await audit_log.record(
                actor=actor,
                action="fraud.blacklist.remove",
                target_type="blacklist_entry",
                target_id=str(entry_id),
                result="success",
            )

    # --- GeoIP rules ---------------------------------------------------------

    async def list_geoip_rules(self) -> list[GeoIpRule]:
        """Return every GeoIP_Rule, enabled or not."""
        return await GeoIpRuleRepository(self._db).list_all()

    async def create_geoip_rule(
        self, *, location_code: str, action: str, enabled: bool = True, actor: str
    ) -> GeoIpRule:
        """Create a GeoIP_Rule for one country/region code."""
        location_code = validate_location_code(location_code)
        action = validate_geoip_action(action)

        async with self._db.tx() as tx:
            rules = GeoIpRuleRepository(tx)
            audit_log = AuditLogRepository(tx)

            existing = await tx.geoiprule.find_unique(where={"locationCode": location_code})
            if existing is not None:
                raise DuplicateGeoIpRuleError(location_code)

            rule = await rules.create(
                {"locationCode": location_code, "action": action, "enabled": enabled}
            )
            await audit_log.record(
                actor=actor,
                action="fraud.geoip.create",
                target_type="geoip_rule",
                target_id=str(rule.id),
                result="success",
            )
            return rule

    async def update_geoip_rule(
        self,
        rule_id: int,
        *,
        location_code: str | None = None,
        action: str | None = None,
        enabled: bool | None = None,
        actor: str,
    ) -> GeoIpRule:
        """Update a GeoIP_Rule; omitted fields keep their stored value."""
        async with self._db.tx() as tx:
            rules = GeoIpRuleRepository(tx)
            audit_log = AuditLogRepository(tx)

            current = await tx.geoiprule.find_unique(where={"id": rule_id})
            if current is None:
                raise GeoIpRuleNotFoundError(rule_id)

            data = {}
            if location_code is not None:
                normalized = validate_location_code(location_code)
                if normalized != current.locationCode:
                    clash = await tx.geoiprule.find_unique(where={"locationCode": normalized})
                    if clash is not None:
                        raise DuplicateGeoIpRuleError(normalized)
                data["locationCode"] = normalized
            if action is not None:
                data["action"] = validate_geoip_action(action)
            if enabled is not None:
                data["enabled"] = enabled

            if not data:
                return current

            updated = await rules.update(rule_id, data)  # type: ignore[arg-type]
            if updated is None:
                raise GeoIpRuleNotFoundError(rule_id)

            await audit_log.record(
                actor=actor,
                action="fraud.geoip.update",
                target_type="geoip_rule",
                target_id=str(rule_id),
                result="success",
            )
            return updated

    async def delete_geoip_rule(self, rule_id: int, *, actor: str) -> None:
        """Delete a GeoIP_Rule, preserving historical Fraud_Flags."""
        async with self._db.tx() as tx:
            rules = GeoIpRuleRepository(tx)
            audit_log = AuditLogRepository(tx)

            deleted = await rules.delete(rule_id)
            if deleted is None:
                raise GeoIpRuleNotFoundError(rule_id)

            await audit_log.record(
                actor=actor,
                action="fraud.geoip.delete",
                target_type="geoip_rule",
                target_id=str(rule_id),
                result="success",
            )
