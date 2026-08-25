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
 * 3. Customer fields in postal order (who → phone → where → how many),
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

import { Fragment, useMemo, useRef, useState, type FormEvent, type JSX } from "react";
import { FormField } from "../../components/FormField";
import { ApiError, publicApi } from "../../api";
import type {
  ColombianDepartment,
  OrderCreateResponse,
  ProductVariantOption,
  PublicLandingOffer,
} from "../../api";
import type { PurchaseCustomerData } from "../../analytics/metaCommerce";
import "./CodForm.css";

export interface CodFormValues {
  /** Exact fulfillment parts; also joined into the existing `full_name`. */
  first_name: string;
  last_name: string;
  phone: string;
  department: string;
  city: string;
  address: string;
  /**
   * Optional reference/complement line ("apto 101", "torre B") shown as its
   * own field right after the address, but frontend-only: it is never sent to
   * the backend as its own field. On submit it is joined onto `address` with
   * a single space, so the order's one `address` column still carries the
   * complete delivery address (Requirement 5.4) without any API/schema
   * change.
   */
  address2: string;
  quantity: string;
}

function initialValues(defaultOfferQuantity?: number): CodFormValues {
  return {
    first_name: "",
    last_name: "",
    phone: "",
    department: "",
    city: "",
    address: "",
    address2: "",
    quantity: String(defaultOfferQuantity ?? 1),
  };
}

const MAX_QUANTITY = 99;

/** Fixed multiplier choices exposed in the form; the backend/validation
 *  contract still allows 1 through MAX_QUANTITY (Requirement 5.5). */
const QUANTITY_OPTIONS = [1, 2, 3] as const;

const CURRENCY = new Intl.NumberFormat("es-CO", {
  style: "currency",
  currency: "COP",
  maximumFractionDigits: 0,
});

/** Field order, used to focus the first invalid control on submit. */
const FIELD_ORDER: (keyof CodFormValues)[] = [
  "first_name",
  "last_name",
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
  defaultOfferQuantity?: number;
  variantOptions?: ProductVariantOption[];
  departments: ColombianDepartment[];
  onSuccess: (
    result: OrderCreateResponse,
    purchase: PurchaseCustomerData & { quantity: number },
  ) => void;
}

function fitVariantSelections(
  options: ProductVariantOption[],
  quantity: number,
  existing: Record<string, string>[] = [],
): Record<string, string>[] {
  if (options.length === 0) return [];
  return Array.from({ length: quantity }, (_, index) =>
    Object.fromEntries(
      options.map((option) => [
        option.name,
        option.values.find((value) => value === existing[index]?.[option.name]) ??
          option.values[0] ??
          "",
      ]),
    ),
  );
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
    case "first_name":
      if (!value) return "Escribe tu nombre.";
      if (value.length > 120) return "El nombre no puede superar 120 caracteres.";
      return undefined;
    case "last_name":
      if (!value) return "Escribe tu apellido.";
      if (value.length > 120) return "El apellido no puede superar 120 caracteres.";
      return undefined;
    case "phone": {
      const digits = value.replace(/\D/g, "").replace(/^57/, "");
      if (!digits) return "Escribe tu número de celular para coordinar la entrega.";
      if (digits.length !== 10 || !digits.startsWith("3")) {
        return "El celular debe tener 10 dígitos y empezar por 3. Ejemplo: 3001234567.";
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
  defaultOfferQuantity,
  variantOptions = [],
  departments,
  onSuccess,
}: CodFormProps): JSX.Element {
  const [values, setValues] = useState<CodFormValues>(() => initialValues(defaultOfferQuantity));
  const initialQuantity = Number(defaultOfferQuantity ?? 1);
  const [variantSelections, setVariantSelections] = useState<Record<string, string>[]>(() =>
    fitVariantSelections(variantOptions, initialQuantity),
  );
  const [variantError, setVariantError] = useState<string | undefined>();
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
  const selectedDepartment = departments.find(
    (department) => department.name === values.department,
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
    setVariantSelections((current) => fitVariantSelections(variantOptions, clamped, current));
    setVariantError(undefined);
  }

  function setVariant(unitIndex: number, optionName: string, value: string) {
    setVariantSelections((current) =>
      current.map((unit, index) =>
        index === unitIndex ? { ...unit, [optionName]: value } : unit,
      ),
    );
    setVariantError(undefined);
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

    const fullName = [values.first_name.trim(), values.last_name.trim()].join(" ");
    if (!nextErrors.first_name && !nextErrors.last_name && fullName.length > 120) {
      nextErrors.last_name = "El nombre completo no puede superar 120 caracteres.";
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
        // Preserve the established Order value and send exact components to
        // the additive fulfillment record used by MasterShop.
        full_name: fullName,
        first_name: values.first_name.trim(),
        last_name: values.last_name.trim(),
        phone: values.phone.trim(),
        department: values.department.trim(),
        city: values.city.trim(),
        // Keep the established local order contract while also sending the
        // exact components needed by the fulfillment integration.
        address: [values.address.trim(), values.address2.trim()].filter(Boolean).join(" "),
        address1: values.address.trim(),
        address2: values.address2.trim() || null,
        quantity: safeQuantity,
        variant_selections: fitVariantSelections(
          variantOptions,
          safeQuantity,
          variantSelections,
        ),
      });
      onSuccess(result, {
        firstName: values.first_name.trim(),
        lastName: values.last_name.trim(),
        phone: values.phone.trim(),
        city: values.city.trim(),
        state: values.department.trim(),
        quantity: safeQuantity,
      });
    } catch (err) {
      if (err instanceof ApiError && err.fieldErrors) {
        const { full_name: fullNameError, ...fieldErrors } = err.fieldErrors;
        const mappedErrors = {
          ...fieldErrors,
          first_name: fullNameError ?? fieldErrors.first_name,
        } as Partial<Record<keyof CodFormValues, string>>;
        setErrors(mappedErrors);
        setVariantError(err.fieldErrors.variant_selections);
        const firstInvalid = FIELD_ORDER.find((field) => mappedErrors[field]);
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
                <Fragment key={tier.quantity}>
                <label
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
                {safeQuantity === tier.quantity && variantOptions.length > 0 && (
                  <div className="cod-form__variants" aria-label="Opciones del producto">
                    {variantSelections.slice(0, safeQuantity).map((selection, unitIndex) => (
                      <fieldset className="cod-form__variant-unit" key={unitIndex}>
                        <legend>
                          {safeQuantity === 1
                            ? "Elige tus opciones"
                            : `Unidad ${unitIndex + 1} de ${safeQuantity}`}
                        </legend>
                        <div className="cod-form__variant-fields">
                          {variantOptions.map((option) => (
                            <fieldset className="cod-form__variant-option" key={option.name}>
                              <legend>{option.name}</legend>
                              <div className="cod-form__variant-choices">
                                {option.values.map((value) => {
                                  const checked =
                                    (selection[option.name] ?? option.values[0] ?? "") === value;
                                  return (
                                    <label
                                      className={
                                        checked
                                          ? "cod-form__variant-choice cod-form__variant-choice--selected"
                                          : "cod-form__variant-choice"
                                      }
                                      key={value}
                                    >
                                      <input
                                        type="radio"
                                        name={`variant-${unitIndex}-${option.name}`}
                                        value={value}
                                        checked={checked}
                                        onChange={() => setVariant(unitIndex, option.name, value)}
                                        aria-label={`${option.name} ${value}, unidad ${unitIndex + 1}`}
                                      />
                                      <span>{value}</span>
                                    </label>
                                  );
                                })}
                              </div>
                            </fieldset>
                          ))}
                        </div>
                      </fieldset>
                    ))}
                    {variantError && <p className="cod-form__quantity-error" role="alert">{variantError}</p>}
                  </div>
                )}
                </Fragment>
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

      <div className="cod-form__row">
        <FormField
          name="first_name"
          label="Nombre"
          autoComplete="given-name"
          enterKeyHint="next"
          autoCapitalize="words"
          required
          maxLength={120}
          value={values.first_name}
          onChange={(e) => update("first_name", e.target.value)}
          onBlur={() => handleBlur("first_name")}
          error={errors.first_name}
        />

        <FormField
          name="last_name"
          label="Apellido"
          autoComplete="family-name"
          enterKeyHint="next"
          autoCapitalize="words"
          required
          maxLength={120}
          value={values.last_name}
          onChange={(e) => update("last_name", e.target.value)}
          onBlur={() => handleBlur("last_name")}
          error={errors.last_name}
        />
      </div>

      <FormField
        name="phone"
        label="Celular / WhatsApp"
        description=""
        type="tel"
        inputMode="numeric"
        autoComplete="tel-national"
        enterKeyHint="next"
        prefixText="+57"
        placeholder="Ej. 3001234567"
        maxLength={14}
        required
        value={values.phone}
        onChange={(e) => update("phone", e.target.value)}
        onBlur={() => handleBlur("phone")}
        error={errors.phone}
      />

      <div className="cod-form__row">
        <div className="form-field" data-field-name="department">
          <label htmlFor="department" className="form-field-label">Departamento</label>
          <select
            id="department"
            name="department"
            className={errors.department ? "form-field-input--error" : "form-field-input"}
            autoComplete="address-level1"
            required
            value={values.department}
            onChange={(event) => {
              update("department", event.target.value);
              update("city", "");
            }}
            onBlur={() => handleBlur("department")}
            aria-invalid={Boolean(errors.department)}
            aria-describedby={errors.department ? "department-error" : undefined}
            disabled={departments.length === 0}
          >
            <option value="">{departments.length ? "Selecciona" : "Cargando…"}</option>
            {departments.map((department) => (
              <option key={department.code} value={department.name}>{department.name}</option>
            ))}
          </select>
          {errors.department && <p className="form-field-error" id="department-error" role="alert">{errors.department}</p>}
        </div>

        <div className="form-field" data-field-name="city">
          <label htmlFor="city" className="form-field-label">Ciudad o municipio</label>
          <select
            id="city"
            name="city"
            className={errors.city ? "form-field-input--error" : "form-field-input"}
            autoComplete="address-level2"
            required
            value={values.city}
            onChange={(event) => update("city", event.target.value)}
            onBlur={() => handleBlur("city")}
            aria-invalid={Boolean(errors.city)}
            aria-describedby={errors.city ? "city-error" : undefined}
            disabled={!selectedDepartment}
          >
            <option value="">{selectedDepartment ? "Selecciona" : "Elige departamento"}</option>
            {selectedDepartment?.cities.map((city) => (
              <option key={city.code} value={city.name}>{city.name}</option>
            ))}
          </select>
          {errors.city && <p className="form-field-error" id="city-error" role="alert">{errors.city}</p>}
        </div>
      </div>

      <FormField
        name="address"
        label="Dirección de entrega"
        description=""
        autoComplete="address-line1"
        enterKeyHint="next"
        placeholder="Ej. Calle 10 # 43-25"
        required
        minLength={5}
        maxLength={250}
        value={values.address}
        onChange={(e) => update("address", e.target.value)}
        onBlur={() => handleBlur("address")}
        error={errors.address}
      />

      <FormField
        name="address2"
        label=""
        aria-label="Dirección 2 (opcional)"
        description="Apto, interior o referencia para el mensajero"
        autoComplete="address-line2"
        enterKeyHint="done"
        placeholder="Ej. Barrio, Int 302 (Opcional)"
        maxLength={250}
        value={values.address2}
        onChange={(e) => update("address2", e.target.value)}
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
