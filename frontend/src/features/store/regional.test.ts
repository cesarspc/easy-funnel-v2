import { describe, expect, it } from "vitest";
import {
  DEFAULT_REGIONAL,
  businessDateIso,
  createMoneyFormatter,
  matchesNationalPhone,
  regionalFromStore,
  toE164,
  type RegionalSettings,
} from "./regional";

const MEXICO: RegionalSettings = {
  countryCode: "MX",
  locale: "es-MX",
  currency: "MXN",
  timeZone: "America/Mexico_City",
  phoneCountryCode: "52",
  phoneNationalPattern: "[0-9]{10}",
};

describe("regional settings", () => {
  it("falls back to the defaults before the store loads", () => {
    expect(regionalFromStore(null)).toEqual(DEFAULT_REGIONAL);
  });

  it("formats money in the configured currency without forced decimals", () => {
    // Intl separates the symbol with a no-break space.
    expect(createMoneyFormatter(DEFAULT_REGIONAL).format(59900).replace(/\s/g, " ")).toBe("$ 59.900");
    expect(createMoneyFormatter({ ...DEFAULT_REGIONAL, locale: "en-US", currency: "USD" }).format(19.5))
      .toBe("$19.50");
  });

  it("survives an invalid currency by falling back to the defaults", () => {
    expect(() => createMoneyFormatter({ ...DEFAULT_REGIONAL, currency: "??" }).format(1)).not.toThrow();
  });

  it("normalizes phones with the configured calling code and pattern", () => {
    expect(toE164(DEFAULT_REGIONAL, "+57 300 123 4567")).toBe("+573001234567");
    expect(toE164(DEFAULT_REGIONAL, "3001234567")).toBe("+573001234567");
    expect(toE164(MEXICO, "55 1234 5678")).toBe("+525512345678");
    expect(matchesNationalPhone(DEFAULT_REGIONAL, "6011234567")).toBe(false);
    expect(matchesNationalPhone(MEXICO, "5512345678")).toBe(true);
  });

  it("computes the business date in the configured time zone", () => {
    const instant = new Date("2026-07-02T03:00:00Z");
    expect(businessDateIso(DEFAULT_REGIONAL, instant)).toBe("2026-07-01");
    expect(businessDateIso({ ...DEFAULT_REGIONAL, timeZone: "Asia/Tokyo" }, instant)).toBe("2026-07-02");
  });
});
