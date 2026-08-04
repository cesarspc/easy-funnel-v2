/**
 * COD order form (Requirements 5.1-5.8), presented in the pop-up the CTA
 * opens (Requirement 3.17-3.18). Conversion-first, in the order a buyer
 * actually needs the information:
 *
 * 1. What am I ordering and what will I pay? — the recap at the top repeats
 *    the product, unit price, quantity, and total, so the sheet never asks for
 *    an address before restating the offer.
 * 2. Nothing to pay now. — the COD promise is stated where the commitment is
 *    asked for, not only on the page behind the sheet.
 * 3. Six fields, one column, in postal order (who → phone → where → how many),
 *    each with the autofill token and mobile keyboard that fits it, so a phone
 *    with saved autofill can complete most of this in one tap.
 * 4. Errors that name the problem and the fix, shown on blur (not while
 *    typing), attached to their control, plus the backend's 422 field errors
 *    mapped onto the same controls (Requirement 8.19). Submitting with errors
 *    focuses the first bad field instead of silently failing.
 * 5. One primary action, always visible: the confirm button is sticky at the
 *    bottom of the scrolling sheet with the amount repeated on it.
 *
 * No countdowns, no invented scarcity, no fake reviews: everything asserted
 * here is either product truth (COD, no card) or the buyer's own input.
 */

import { useMemo, useRef, useState, type FormEvent, type JSX } from "react";
import { FormField } from "../../components/FormField";
import { ApiError, publicApi } from "../../api";
import type { OrderCreateResponse, PublicLandingOffer } from "../../api";
import "./CodForm.css";

export interface CodFormValues {
  full_name: string;
  phone: string;
  department: string;
  city: string;
  address: string;
  quantity: string;
}

const INITIAL_VALUES: CodFormValues = {
  full_name: "",
  phone: "",
  department: "",
  city: "",
  address: "",
  quantity: "1",
};

const MAX_QUANTITY = 99;

/** Fixed multiplier choices exposed in the form; the backend/validation
 *  contract still allows 1 through MAX_QUANTITY (Requirement 5.5). */
const QUANTITY_OPTIONS = [1, 2, 3] as const;

/** Colombia's 32 departments plus the capital district, for the datalist. */
const DEPARTMENTS = [
  "Amazonas",
  "Antioquia",
  "Arauca",
  "Atlántico",
  "Bogotá D.C.",
  "Bolívar",
  "Boyacá",
  "Caldas",
  "Caquetá",
  "Casanare",
  "Cauca",
  "Cesar",
  "Chocó",
  "Córdoba",
  "Cundinamarca",
  "Guainía",
  "Guaviare",
  "Huila",
  "La Guajira",
  "Magdalena",
  "Meta",
  "Nariño",
  "Norte de Santander",
  "Putumayo",
  "Quindío",
  "Risaralda",
  "San Andrés y Providencia",
  "Santander",
  "Sucre",
  "Tolima",
  "Valle del Cauca",
  "Vaupés",
  "Vichada",
] as const;

const CURRENCY = new Intl.NumberFormat("es-CO", {
  style: "currency",
  currency: "COP",
  maximumFractionDigits: 0,
});

/** Field order, used to focus the first invalid control on submit. */
const FIELD_ORDER: (keyof CodFormValues)[] = [
  "full_name",
  "phone",
  "department",
  "city",
  "address",
  "quantity",
];

export interface CodFormProps {
  landingSlug: string;
  /** Product name, repeated in the recap so the sheet restates the offer. */
  productName?: string;
  /** Unit price in COP, used for the recap total and the confirm button. */
  unitPrice?: number;
  /**
   * The quantity offers this landing presents, already priced by the backend.
   *
   * Absent on payloads cached before offers were configurable, in which case
   * the form falls back to the 1/2/3 tiers it always rendered. The totals here
   * are authoritative: they already include any discount the merchant set, and
   * the order records the total of the tier the buyer picks.
   */
  offers?: PublicLandingOffer[];
  onSuccess: (result: OrderCreateResponse) => void;
}

/**
 * Client-side check for one field. Deliberately thin: it catches the mistakes
 * a buyer makes on a phone keyboard (empty field, too-short address, a phone
 * that is not 10 digits) and leaves the authoritative rules to the backend,
 * whose 422 messages are rendered in the same place.
 */
function validateField(field: keyof CodFormValues, raw: string): string | undefined {
  const value = raw.trim();

  switch (field) {
    case "full_name":
      if (!value) return "Escribe tu nombre y apellido.";
      if (value.length < 2) return "Escribe tu nombre completo.";
      return undefined;
    case "phone": {
      const digits = value.replace(/\D/g, "").replace(/^57/, "");
      if (!digits) return "Escribe tu número de celular para coordinar la entrega.";
      if (digits.length !== 10 || !digits.startsWith("3")) {
        return "El celular debe tener 10 dígitos y empezar por 3. Ejemplo: 300 123 4567.";
      }
      return undefined;
    }
    case "department":
      if (!value) return "Elige tu departamento.";
      return undefined;
    case "city":
      if (!value) return "Escribe tu ciudad o municipio.";
      return undefined;
    case "address":
      if (!value) return "Escribe la dirección donde recibes el pedido.";
      if (value.length < 5) return "Agrega más detalle: calle, número, barrio.";
      return undefined;
    case "quantity": {
      const quantity = Number.parseInt(value, 10);
      if (!Number.isInteger(quantity) || quantity < 1 || quantity > MAX_QUANTITY) {
        return `Elige una cantidad entre 1 y ${MAX_QUANTITY}.`;
      }
      return undefined;
    }
    default:
      return undefined;
  }
}

/**
 * Renders the COD order form and submits to POST /api/public/orders.
 * Field errors from the backend's 422 response are mapped to the
 * corresponding control (Requirement 8.19).
 */
export function CodForm({
  landingSlug,
  productName,
  unitPrice,
  offers,
  onSuccess,
}: CodFormProps): JSX.Element {
  const [values, setValues] = useState<CodFormValues>(INITIAL_VALUES);
  const [errors, setErrors] = useState<Partial<Record<keyof CodFormValues, string>>>({});
  const [submitting, setSubmitting] = useState(false);
  const [formError, setFormError] = useState<string | null>(null);
  const formRef = useRef<HTMLFormElement>(null);

  /**
   * The tiers to render. A landing configured by the merchant supplies them;
   * a payload cached before offers existed falls back to the 1/2/3 list with
   * plain totals, so an old cache never renders an empty quantity picker.
   */
  const tiers = useMemo<PublicLandingOffer[]>(() => {
    if (offers && offers.length > 0) {
      return [...offers].sort((a, b) => a.quantity - b.quantity);
    }
    if (unitPrice === undefined) return [];
    return QUANTITY_OPTIONS.map((option) => ({
      quantity: option,
      label: option === 1 ? "1 unidad" : `${option} unidades`,
      sublabel: null,
      discount_percent: 0,
      unit_price: unitPrice,
      gross: unitPrice * option,
      total: unitPrice * option,
      savings: 0,
      compare_at_price: null,
    }));
  }, [offers, unitPrice]);

  const quantity = Number.parseInt(values.quantity, 10);
  const parsedQuantity = Number.isInteger(quantity) && quantity > 0 ? quantity : 1;
  // Never leave the selection on a quantity this landing does not offer: a
  // merchant can lower the offer count between the page loading and the sheet
  // opening, and the submit button must always name a real tier's total.
  const safeQuantity = tiers.some((tier) => tier.quantity === parsedQuantity)
    ? parsedQuantity
    : (tiers[0]?.quantity ?? parsedQuantity);

  const selectedTier = useMemo(
    () => tiers.find((tier) => tier.quantity === safeQuantity),
    [tiers, safeQuantity],
  );

  // The discounted total when the landing priced this tier, the plain product
  // of price and quantity otherwise.
  const total = useMemo(() => {
    if (selectedTier) return selectedTier.total;
    return unitPrice === undefined ? undefined : unitPrice * safeQuantity;
  }, [selectedTier, unitPrice, safeQuantity]);

  function update(field: keyof CodFormValues, value: string) {
    setValues((v) => ({ ...v, [field]: value }));
    // Clear an error as soon as the buyer starts fixing it; never introduce a
    // new error mid-keystroke.
    if (errors[field]) {
      setErrors((current) => ({ ...current, [field]: undefined }));
    }
  }

  function handleBlur(field: keyof CodFormValues) {
    const message = validateField(field, values[field]);
    setErrors((current) => ({ ...current, [field]: message }));
  }

  function setQuantity(next: number) {
    const clamped = Math.min(Math.max(next, 1), MAX_QUANTITY);
    update("quantity", String(clamped));
  }

  function focusField(field: keyof CodFormValues) {
    formRef.current?.querySelector<HTMLElement>(`#${field}`)?.focus();
  }

  async function handleSubmit(event: FormEvent) {
    event.preventDefault();
    setFormError(null);

    const nextErrors: Partial<Record<keyof CodFormValues, string>> = {};
    for (const field of FIELD_ORDER) {
      const message = validateField(field, values[field]);
      if (message) nextErrors[field] = message;
    }

    if (Object.keys(nextErrors).length > 0) {
      setErrors(nextErrors);
      const firstInvalid = FIELD_ORDER.find((field) => nextErrors[field]);
      if (firstInvalid) focusField(firstInvalid);
      return;
    }

    setSubmitting(true);
    setErrors({});
    try {
      const result = await publicApi.createOrder({
        landing_slug: landingSlug,
        full_name: values.full_name.trim(),
        phone: values.phone.trim(),
        department: values.department.trim(),
        city: values.city.trim(),
        address: values.address.trim(),
        quantity: safeQuantity,
      });
      onSuccess(result);
    } catch (err) {
      if (err instanceof ApiError && err.fieldErrors) {
        setErrors(err.fieldErrors as Partial<Record<keyof CodFormValues, string>>);
        const firstInvalid = FIELD_ORDER.find((field) => err.fieldErrors?.[field]);
        if (firstInvalid) focusField(firstInvalid);
      } else if (err instanceof ApiError) {
        setFormError(err.message);
      } else {
        setFormError("No se pudo enviar tu pedido. Revisa tu conexión e intenta de nuevo.");
      }
    } finally {
      setSubmitting(false);
    }
  }

  return (
    <form className="cod-form" onSubmit={handleSubmit} noValidate ref={formRef}>
      {(productName || tiers.length > 0) && (
        <div className="cod-form__recap">
          {/* Quantity is chosen right here, as a price tier, instead of a
              plain number field buried at the end of the form: the buyer
              sees what each quantity costs in the same place they're
              already reading the offer. Each tier is a real radio input
              under the hood, reporting through the same `quantity` field.
              Which tiers exist, what they are called, and whether they carry a
              discount are the merchant's per-landing configuration; the
              presentation below is fixed in the chrome. */}
          <fieldset className="cod-form__tiers" role="radiogroup" aria-label="Cantidad">
            <legend className="sr-only">Elige cuántas unidades quieres</legend>
            {tiers.map((tier) => {
              const discounted = tier.discount_percent > 0;
              return (
                <label
                  key={tier.quantity}
                  className={
                    "cod-form__tier" +
                    (discounted ? " cod-form__tier--best" : "") +
                    (safeQuantity === tier.quantity ? " cod-form__tier--selected" : "")
                  }
                >
                  {/* The badge marks a real, computable saving rather than a
                      hardcoded "most ordered" claim this platform cannot
                      verify. */}
                  {discounted && (
                    <span className="cod-form__tier-badge">
                      -{tier.discount_percent}%
                    </span>
                  )}
                  <input
                    type="radio"
                    name="quantity"
                    value={tier.quantity}
                    checked={safeQuantity === tier.quantity}
                    onChange={() => setQuantity(tier.quantity)}
                    onBlur={() => handleBlur("quantity")}
                  />
                  <span className="cod-form__tier-left">
                    <span className="cod-form__tier-qty">{tier.label}</span>
                    {/* Blank sub-text is how a merchant turns the second line
                        off, so it is simply absent rather than empty. */}
                    {tier.sublabel && (
                      <span className="cod-form__tier-save">{tier.sublabel}</span>
                    )}
                  </span>
                  <span className="cod-form__tier-prices">
                    {/* The pre-discount price, and on the single-unit tier the
                        merchant's own reference price. Both are struck through
                        and informational; `total` is what is actually owed. */}
                    {discounted ? (
                      <s className="cod-form__tier-was">{CURRENCY.format(tier.gross)}</s>
                    ) : (
                      tier.compare_at_price !== null && (
                        <s className="cod-form__tier-was">
                          {CURRENCY.format(tier.compare_at_price)}
                        </s>
                      )
                    )}
                    <strong className="cod-form__tier-total">
                      {CURRENCY.format(tier.total)}
                    </strong>
                  </span>
                </label>
              );
            })}
          </fieldset>
          {errors.quantity && (
            <p className="cod-form__quantity-error" role="alert">
              {errors.quantity}
            </p>
          )}
        </div>
      )}

      <FormField
        name="full_name"
        label="Nombre completo"
        autoComplete="name"
        enterKeyHint="next"
        autoCapitalize="words"
        required
        minLength={2}
        maxLength={120}
        value={values.full_name}
        onChange={(e) => update("full_name", e.target.value)}
        onBlur={() => handleBlur("full_name")}
        error={errors.full_name}
      />

      <FormField
        name="phone"
        label="Número de celular"
        description="Te llamamos o escribimos solo para coordinar la entrega."
        type="tel"
        inputMode="numeric"
        autoComplete="tel-national"
        enterKeyHint="next"
        prefixText="+57"
        placeholder="300 123 4567"
        maxLength={14}
        required
        value={values.phone}
        onChange={(e) => update("phone", e.target.value)}
        onBlur={() => handleBlur("phone")}
        error={errors.phone}
      />

      <div className="cod-form__row">
        <FormField
          name="department"
          label="Departamento"
          autoComplete="address-level1"
          enterKeyHint="next"
          suggestions={DEPARTMENTS}
          placeholder="Antioquia"
          required
          minLength={2}
          maxLength={100}
          value={values.department}
          onChange={(e) => update("department", e.target.value)}
          onBlur={() => handleBlur("department")}
          error={errors.department}
        />

        <FormField
          name="city"
          label="Ciudad o municipio"
          autoComplete="address-level2"
          enterKeyHint="next"
          autoCapitalize="words"
          placeholder="Medellín"
          required
          minLength={2}
          maxLength={100}
          value={values.city}
          onChange={(e) => update("city", e.target.value)}
          onBlur={() => handleBlur("city")}
          error={errors.city}
        />
      </div>

      <FormField
        name="address"
        label="Dirección de entrega"
        description="Incluye barrio y datos que ayuden al mensajero (torre, apto, referencia)."
        autoComplete="street-address"
        enterKeyHint="done"
        placeholder="Calle 10 # 43-25, apto 302, barrio Poblado"
        required
        minLength={5}
        maxLength={250}
        value={values.address}
        onChange={(e) => update("address", e.target.value)}
        onBlur={() => handleBlur("address")}
        error={errors.address}
      />

      {formError && (
        <p className="cod-form__error" role="alert">
          {formError}
        </p>
      )}

      <div className="cod-form__actions">
        <button type="submit" className="cod-form__submit" disabled={submitting}>
          {submitting ? (
            <>
              <span className="cod-form__spinner" aria-hidden="true" />
              Enviando tu pedido…
            </>
          ) : total !== undefined ? (
            `Confirmar pedido — ${CURRENCY.format(total)}`
          ) : (
            "Confirmar pedido"
          )}
        </button>
        <p className="cod-form__note">Pago seguro contraentrega</p>
      </div>
    </form>
  );
}
