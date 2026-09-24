/**
 * Market conventions (locale, currency, time zone, phone rules) come from the
 * store settings the merchant edits under Admin → Tienda. Components read them
 * through `useRegional()` instead of hard-coding a country.
 *
 * `DEFAULT_REGIONAL` mirrors the backend defaults and is only used before the
 * store has loaded (or in isolated component tests without a provider).
 */

import { useMemo } from "react";
import type { StoreSettings } from "../../api";
import { useStore } from "./StoreContext";

export interface RegionalSettings {
  countryCode: string;
  locale: string;
  currency: string;
  timeZone: string;
  phoneCountryCode: string;
  phoneNationalPattern: string;
}

export const DEFAULT_REGIONAL: RegionalSettings = {
  countryCode: "CO",
  locale: "es-CO",
  currency: "COP",
  timeZone: "America/Bogota",
  phoneCountryCode: "57",
  phoneNationalPattern: "3[0-9]{9}",
};

export function regionalFromStore(store: StoreSettings | null | undefined): RegionalSettings {
  if (!store) return DEFAULT_REGIONAL;
  return {
    countryCode: store.country_code || DEFAULT_REGIONAL.countryCode,
    locale: store.locale || DEFAULT_REGIONAL.locale,
    currency: store.currency || DEFAULT_REGIONAL.currency,
    timeZone: store.time_zone || DEFAULT_REGIONAL.timeZone,
    phoneCountryCode: store.phone_country_code || DEFAULT_REGIONAL.phoneCountryCode,
    phoneNationalPattern: store.phone_national_pattern || DEFAULT_REGIONAL.phoneNationalPattern,
  };
}

/** Build an Intl formatter, falling back to the defaults on an invalid tag. */
function safeFormatter<T>(build: (locale: string) => T, locale: string): T {
  try {
    return build(locale);
  } catch {
    return build(DEFAULT_REGIONAL.locale);
  }
}

export function createMoneyFormatter(regional: RegionalSettings): Intl.NumberFormat {
  // Whole amounts render without decimals (e.g. "$ 59.900"); fractional ones
  // keep the currency's minor units (e.g. "$19.50").
  const options = {
    style: "currency",
    currency: regional.currency,
    trailingZeroDisplay: "stripIfInteger",
  } as Intl.NumberFormatOptions;
  try {
    return new Intl.NumberFormat(regional.locale, options);
  } catch {
    return new Intl.NumberFormat(DEFAULT_REGIONAL.locale, {
      ...options,
      currency: DEFAULT_REGIONAL.currency,
    });
  }
}

export function createDateFormatter(
  regional: RegionalSettings,
  options: Intl.DateTimeFormatOptions,
  { businessTimeZone = true }: { businessTimeZone?: boolean } = {},
): Intl.DateTimeFormat {
  const withZone = businessTimeZone ? { timeZone: regional.timeZone, ...options } : options;
  return safeFormatter((locale) => new Intl.DateTimeFormat(locale, withZone), regional.locale);
}

export function createNumberFormatter(
  regional: RegionalSettings,
  options: Intl.NumberFormatOptions,
): Intl.NumberFormat {
  return safeFormatter((locale) => new Intl.NumberFormat(locale, options), regional.locale);
}

/** ISO `YYYY-MM-DD` calendar date of `date` in the merchant's time zone. */
export function businessDateIso(regional: RegionalSettings, date: Date = new Date()): string {
  let parts: Intl.DateTimeFormatPart[];
  const options: Intl.DateTimeFormatOptions = {
    year: "numeric",
    month: "2-digit",
    day: "2-digit",
  };
  try {
    parts = new Intl.DateTimeFormat("en", { ...options, timeZone: regional.timeZone }).formatToParts(date);
  } catch {
    parts = new Intl.DateTimeFormat("en", { ...options, timeZone: DEFAULT_REGIONAL.timeZone }).formatToParts(date);
  }
  const value = (type: Intl.DateTimeFormatPartTypes) =>
    parts.find((part) => part.type === type)?.value ?? "";
  return `${value("year")}-${value("month")}-${value("day")}`;
}

/** Whether `digits` is a valid national number under the store's rules. */
export function matchesNationalPhone(regional: RegionalSettings, digits: string): boolean {
  try {
    return new RegExp(`^(?:${regional.phoneNationalPattern})$`).test(digits);
  } catch {
    // A pattern valid for the backend but not for this browser: let the
    // server remain the authority instead of blocking the buyer.
    return true;
  }
}

/** National number for a buyer-typed phone, mirroring backend normalization. */
export function nationalPhoneDigits(regional: RegionalSettings, raw: string): string {
  const digits = raw.replace(/\D/g, "");
  if (matchesNationalPhone(regional, digits)) return digits;
  if (digits.startsWith(regional.phoneCountryCode)) {
    return digits.slice(regional.phoneCountryCode.length);
  }
  return digits;
}

/** Canonical `+<calling code><national number>` for a buyer-typed phone. */
export function toE164(regional: RegionalSettings, raw: string): string {
  return `+${regional.phoneCountryCode}${nationalPhoneDigits(regional, raw)}`;
}

export interface Regional extends RegionalSettings {
  money: Intl.NumberFormat;
}

/** Current market settings plus a ready money formatter. */
export function useRegional(): Regional {
  const { store } = useStore();
  const regional = regionalFromStore(store);
  const key = JSON.stringify(regional);
  // eslint-disable-next-line react-hooks/exhaustive-deps
  return useMemo(() => ({ ...regional, money: createMoneyFormatter(regional) }), [key]);
}
