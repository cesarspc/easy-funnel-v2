/**
 * Conversion components panel of the landing editor (Requirements 3.27-3.31).
 *
 * The Administrator does exactly two things here: choose one of the fixed
 * pre-defined components and the position it occupies, and write its content.
 * There is no control for spacing, color, type, or width — those are fixed in
 * the public landing chrome and tuned for conversion, so this panel cannot
 * de-optimize a component.
 *
 * Positions come from the API, not from this file: the backend derives one
 * label per slot from the same banner sequence and CTA positions the public
 * page renders ("1-2 · entre banner 1 y CTA 1"), so the list shown here and
 * the rendered result cannot disagree.
 */

import { useCallback, useEffect, useState, type JSX } from "react";
import { ApiError, landingsApi } from "../../api";
import type { ConversionBlockType, LandingBlock } from "../../api";
import "./LandingBlocksPanel.css";

export interface LandingBlocksPanelProps {
  landingId: number;
  /**
   * Changes whenever the banner sequence or CTA configuration changes, so the
   * placement slots are re-read instead of going stale.
   */
  sequenceSignature: string;
  /** Resolved landing-level block accent, used when a block has no override. */
  defaultAccentColor: string;
}

interface BlockTypeMeta {
  label: string;
  purpose: string;
}

/** Merchant-facing name and the objection each component removes. */
const BLOCK_TYPES: Record<ConversionBlockType, BlockTypeMeta> = {
  cta: {
    label: "Botón CTA",
    purpose: "Añade otra llamada a la acción entre componentes y abre el mismo formulario COD.",
  },
  announcement_bar: {
    label: "Barra superior",
    purpose: "Un mensaje corto arriba de todo (envío gratis, promo). Es su propia franja de color.",
  },
  cod_assurance: {
    label: "Pago contraentrega",
    purpose: "Quita el miedo a pagar por adelantado. Solo agregas una nota opcional.",
  },
  benefits: {
    label: "Beneficios",
    purpose: "De 2 a 5 razones cortas para comprar, en una sola pasada de lectura.",
  },
  offer_price: {
    label: "Precio y ahorro",
    purpose: "Muestra el precio del producto y, si indicas el precio anterior, el ahorro.",
  },
  included_benefits: {
    label: "Incluido en tu pedido",
    purpose: "Lista de lo que recibe el comprador, con valor y etiqueta opcionales.",
  },
  reviews: {
    label: "Reseñas",
    purpose: "Hasta 4 reseñas reales de clientes, con nombre y ciudad.",
  },
  faq: {
    label: "Preguntas frecuentes",
    purpose: "Hasta 6 preguntas que resuelven dudas sin empujar el CTA fuera de pantalla.",
  },
  guarantee: {
    label: "Garantía",
    purpose: "Reduce el riesgo percibido con una promesa clara que puedas cumplir.",
  },
  main_problem: {
    label: "Problema principal",
    purpose: "Presenta el problema central y sus síntomas en tarjetas editables.",
  },
  solution_presentation: {
    label: "Presentación de solución",
    purpose: "Conecta el problema con tu solución, sus pilares y un cierre opcional.",
  },
  how_it_works: {
    label: "Cómo funciona",
    purpose: "Explica el proceso como una secuencia de pasos clara y móvil.",
  },
  audience: {
    label: "Para quién es",
    purpose: "Aclara para quién sí y para quién no es el producto.",
  },
  moment: {
    label: "Momento",
    purpose: "Crea una pausa breve con un mensaje de decisión y acción.",
  },
};

const BLOCK_TYPE_ORDER: ConversionBlockType[] = [
  "announcement_bar",
  "cod_assurance",
  "offer_price",
  "cta",
  "benefits",
  "included_benefits",
  "reviews",
  "faq",
  "main_problem",
  "solution_presentation",
  "how_it_works",
  "audience",
  "moment",
  "guarantee",
];

type Draft = Record<string, unknown>;

/** Starting content per type. `included_benefits` ships a blank item list. */
function defaultDraft(type: ConversionBlockType): Draft {
  switch (type) {
    case "cta":
      return { text: "", accent_color: "" };
    case "announcement_bar":
      return { text: "Envío gratis + Paga al recibir", accent_color: "" };
    case "cod_assurance":
      return { note: "", accent_color: "" };
    case "benefits":
      return { title: "", items: ["", ""], accent_color: "" };
    case "offer_price":
      return { compare_at_price: "", note: "", accent_color: "" };
    case "included_benefits":
      return {
        title: "",
        items: [{ name: "", value: "", tag: "" }],
        accent_color: "",
      };
    case "reviews":
      return { title: "", items: [{ name: "", city: "", text: "", rating: "" }], accent_color: "" };
    case "faq":
      return { title: "", items: [{ question: "", answer: "" }], accent_color: "" };
    case "guarantee":
      return {
        eyebrow: "Compra protegida",
        title: "Garantía total",
        text: "Pruébalo con tranquilidad. Si no es para ti, solicita la devolución dentro del plazo.",
        days: "7",
        benefits: [
          { title: "Riesgo cero", text: "Tu compra está protegida." },
          { title: "Devolución rápida", text: "Proceso simple y claro." },
          { title: "Sin preguntas", text: "Sin trámites innecesarios." },
        ],
        accent_color: "",
      };
    case "main_problem":
      return {
        eyebrow: "Si esto te suena familiar, sigue leyendo",
        title: "La razón por la que",
        highlight: "todavía tienes este problema",
        subtitle: "No es falta de esfuerzo. Necesitas una solución creada para esta situación.",
        items: [
          { title: "Problema principal", text: "Describe cómo se siente este problema." },
        ],
        accent_color: "",
      };
    case "solution_presentation":
      return {
        bridge_text: "Si te identificaste con estos puntos, esta solución fue creada para ti.",
        eyebrow: "La solución",
        title: "Presentamos",
        highlight: "TU SOLUCIÓN",
        text: "Explica en una frase clara qué es y qué resultado ayuda a conseguir.",
        supporting_text: "Agrega aquí una prueba o diferenciador importante.",
        items: [{ title: "Pilar principal", text: "Describe esta parte de la solución.", kicker: "" }],
        final_title: "",
        final_highlight: "",
        accent_color: "",
      };
    case "how_it_works":
      return {
        title: "Cómo funciona",
        highlight: "PASO A PASO",
        subtitle: "Un proceso claro, sin complicaciones.",
        steps: [{ kicker: "Paso 1", title: "Primer paso", text: "Explica qué debe hacer." }],
        accent_color: "",
      };
    case "audience":
      return {
        title: "Para quién es",
        highlight: "este producto",
        positive_title: "ES PARA TI",
        positive_subtitle: "Si te identificas con esto",
        positive_items: ["Persona que busca una solución práctica"],
        negative_title: "NO ES PARA TI",
        negative_subtitle: "Si buscas esto, no es la opción indicada",
        negative_items: ["Persona que espera resultados sin seguir las indicaciones"],
        footer: "",
        accent_color: "",
      };
    case "moment":
      return {
        title: "¿Sigues esperando el",
        highlight: "momento perfecto?",
        text: "El momento perfecto no existe. Los resultados empiezan cuando decides actuar.",
        emphasis: "Actúa aunque no esté todo listo.",
        footer: "",
        accent_color: "",
      };
    default:
      return {};
  }
}

function draftFromBlock(block: LandingBlock): Draft {
  const base = defaultDraft(block.block_type);
  return { ...base, ...block.config };
}

function asStringList(value: unknown, fallbackLength: number): string[] {
  if (Array.isArray(value)) return value.map((item) => (typeof item === "string" ? item : ""));
  return Array.from({ length: fallbackLength }, () => "");
}

function asRecordList(value: unknown): Record<string, unknown>[] {
  if (Array.isArray(value)) {
    return value.map((item) =>
      typeof item === "object" && item !== null ? (item as Record<string, unknown>) : {},
    );
  }
  return [];
}

function textValue(record: Record<string, unknown>, key: string): string {
  const value = record[key];
  return typeof value === "string" || typeof value === "number" ? String(value) : "";
}

interface EditorProps {
  type: ConversionBlockType;
  draft: Draft;
  onChange: (draft: Draft) => void;
  idPrefix: string;
  fieldErrors: Record<string, string>;
  /** Current form accent color for the color picker default. */
  defaultAccentColor: string;
}

function FieldError({ id, message }: { id: string; message?: string }): JSX.Element | null {
  if (!message) return null;
  return (
    <p className="landings-field__error" id={id} role="alert">
      {message}
    </p>
  );
}

interface RepeatField {
  key: string;
  label: string;
  placeholder: string;
  maxLength: number;
  textarea?: boolean;
}

function RecordItemsEditor({
  legend,
  value,
  onChange,
  fields,
  minimum = 1,
  maximum,
  addLabel,
  removeLabel,
  error,
  idPrefix,
}: {
  legend: string;
  value: unknown;
  onChange: (items: Record<string, unknown>[]) => void;
  fields: RepeatField[];
  minimum?: number;
  maximum: number;
  addLabel: string;
  removeLabel: string;
  error?: string;
  idPrefix: string;
}): JSX.Element {
  const items = asRecordList(value);
  return (
    <fieldset className="lblocks__fieldset">
      <legend className="landings-field__label">{legend}</legend>
      {items.map((item, index) => (
        <div className="lblocks__group" key={index}>
          {fields.map((field) => {
            const shared = {
              className: "landings-field__input",
              "aria-label": `${field.label} ${index + 1}`,
              placeholder: field.placeholder,
              maxLength: field.maxLength,
              value: textValue(item, field.key),
              onChange: (event: React.ChangeEvent<HTMLInputElement | HTMLTextAreaElement>) => {
                const next = [...items];
                next[index] = { ...item, [field.key]: event.target.value };
                onChange(next);
              },
            };
            return field.textarea ? (
              <textarea key={field.key} {...shared} rows={3} />
            ) : (
              <input key={field.key} {...shared} />
            );
          })}
          {items.length > minimum && (
            <button
              type="button"
              className="landings-table__action"
              onClick={() => onChange(items.filter((_, itemIndex) => itemIndex !== index))}
            >
              {removeLabel}
            </button>
          )}
        </div>
      ))}
      {items.length < maximum && (
        <button
          type="button"
          className="landings-table__action"
          onClick={() =>
            onChange([...items, Object.fromEntries(fields.map((field) => [field.key, ""]))])
          }
        >
          {addLabel}
        </button>
      )}
      <FieldError id={`${idPrefix}-error`} message={error} />
    </fieldset>
  );
}

function StringItemsEditor({
  legend,
  value,
  onChange,
  maximum,
  addLabel,
  error,
  idPrefix,
}: {
  legend: string;
  value: unknown;
  onChange: (items: string[]) => void;
  maximum: number;
  addLabel: string;
  error?: string;
  idPrefix: string;
}): JSX.Element {
  const items = asStringList(value, 1);
  return (
    <fieldset className="lblocks__fieldset">
      <legend className="landings-field__label">{legend}</legend>
      {items.map((item, index) => (
        <div className="lblocks__row" key={index}>
          <input
            className="landings-field__input"
            aria-label={`${legend} ${index + 1}`}
            value={item}
            maxLength={90}
            onChange={(event) => {
              const next = [...items];
              next[index] = event.target.value;
              onChange(next);
            }}
          />
          {items.length > 1 && (
            <button
              type="button"
              className="landings-table__action"
              onClick={() => onChange(items.filter((_, itemIndex) => itemIndex !== index))}
            >
              Quitar
            </button>
          )}
        </div>
      ))}
      {items.length < maximum && (
        <button
          type="button"
          className="landings-table__action"
          onClick={() => onChange([...items, ""])}
        >
          {addLabel}
        </button>
      )}
      <FieldError id={`${idPrefix}-error`} message={error} />
    </fieldset>
  );
}

function ContentEditor({
  type,
  draft,
  onChange,
  idPrefix,
  fieldErrors,
  defaultAccentColor,
}: EditorProps): JSX.Element {
  function set(key: string, value: unknown) {
    onChange({ ...draft, [key]: value });
  }

  function storyTextField(
    key: string,
    label: string,
    placeholder: string,
    maximum: number,
    textarea = false,
  ): JSX.Element {
    const inputProps = {
      id: `${idPrefix}-${key}`,
      className: "landings-field__input",
      value: textValue(draft, key),
      maxLength: maximum,
      placeholder,
      onChange: (event: React.ChangeEvent<HTMLInputElement | HTMLTextAreaElement>) =>
        set(key, event.target.value),
    };
    return (
      <div className="landings-field">
        <label className="landings-field__label" htmlFor={`${idPrefix}-${key}`}>
          {label}
        </label>
        {textarea ? <textarea {...inputProps} rows={3} /> : <input {...inputProps} />}
        <FieldError id={`${idPrefix}-${key}-error`} message={fieldErrors[key]} />
      </div>
    );
  }

  const titleField = (
    <div className="landings-field">
      <label className="landings-field__label" htmlFor={`${idPrefix}-title`}>
        Título (opcional)
      </label>
      <input
        id={`${idPrefix}-title`}
        className="landings-field__input"
        value={textValue(draft, "title")}
        maxLength={80}
        onChange={(event) => set("title", event.target.value)}
      />
      <FieldError id={`${idPrefix}-title-error`} message={fieldErrors.title} />
    </div>
  );

  // Every component type accepts this same optional override: a color for its
  // own buttons/lines/background, in place of the landing's form accent. One
  // field, shared across every editor, so adding it here cannot drift
  // per type the way a copy-pasted field eventually would.
  const accentColorField = (
    <div className="landings-field">
      <label className="landings-field__label" htmlFor={`${idPrefix}-accent`}>
        Color de acento (opcional)
      </label>
      <div className="lblocks__row">
        <input
          id={`${idPrefix}-accent`}
          className="landings-field__input"
          type="color"
          style={{ maxWidth: 56, padding: 2 }}
          value={/^#[0-9a-fA-F]{6}$/.test(textValue(draft, "accent_color")) ? textValue(draft, "accent_color") : defaultAccentColor}
          onChange={(event) => set("accent_color", event.target.value)}
          aria-label="Elegir color de acento"
        />
        <input
          className="landings-field__input"
          value={textValue(draft, "accent_color")}
          placeholder="Usa el acento del formulario"
          maxLength={7}
          onChange={(event) => set("accent_color", event.target.value)}
        />
        {textValue(draft, "accent_color") && (
          <button
            type="button"
            className="landings-table__action"
            onClick={() => set("accent_color", "")}
          >
            Quitar
          </button>
        )}
      </div>
      <p className="landings-page__muted">
        Sin color propio, este componente usa el color general de componentes.
      </p>
      <FieldError id={`${idPrefix}-accent-error`} message={fieldErrors.accent_color} />
    </div>
  );

  const darkModeField = (
    <div className="landings-field">
      <label className="landings-field__label">Modo oscuro</label>
      <select
        className="landings-field__input"
        style={{ maxWidth: 220 }}
        value={draft.dark_mode === true ? "dark" : draft.dark_mode === false ? "light" : "default"}
        onChange={(event) => {
          const v = event.target.value;
          set("dark_mode", v === "dark" ? true : v === "light" ? false : "");
        }}
      >
        <option value="default">Usar default de la landing</option>
        <option value="light">Siempre claro</option>
        <option value="dark">Siempre oscuro</option>
      </select>
    </div>
  );

  switch (type) {
    case "cta":
      return (
        <div className="lblocks__editor">
          <div className="landings-field">
            <label className="landings-field__label" htmlFor={`${idPrefix}-text`}>
              Texto del botón (opcional)
            </label>
            <input
              id={`${idPrefix}-text`}
              className="landings-field__input"
              value={textValue(draft, "text")}
              maxLength={60}
              placeholder="Usar el texto general del CTA"
              onChange={(event) => set("text", event.target.value)}
            />
            <p className="landings-page__muted">
              Vacío reutiliza el texto configurado para los CTA de esta landing.
            </p>
            <FieldError id={`${idPrefix}-text-error`} message={fieldErrors.text} />
          </div>
          {accentColorField}
          {darkModeField}
        </div>
      );

    case "announcement_bar":
      return (
        <div className="lblocks__editor">
          <div className="landings-field">
            <label className="landings-field__label" htmlFor={`${idPrefix}-text`}>
              Texto
            </label>
            <input
              id={`${idPrefix}-text`}
              className="landings-field__input"
              value={textValue(draft, "text")}
              maxLength={80}
              placeholder="Envío gratis + Paga al recibir"
              onChange={(event) => set("text", event.target.value)}
            />
            <FieldError id={`${idPrefix}-text-error`} message={fieldErrors.text} />
          </div>
          {accentColorField}
          {darkModeField}
        </div>
      );

    case "cod_assurance":
      return (
        <div className="lblocks__editor">
          <p className="landings-page__muted">
            Los tres mensajes (pagas al recibir, revisas antes de pagar, sin tarjeta) son fijos:
            describen cómo funciona la plataforma.
          </p>
          <div className="landings-field">
            <label className="landings-field__label" htmlFor={`${idPrefix}-note`}>
              Nota adicional (opcional)
            </label>
            <input
              id={`${idPrefix}-note`}
              className="landings-field__input"
              value={textValue(draft, "note")}
              maxLength={140}
              placeholder="Cobertura en todo el país"
              onChange={(event) => set("note", event.target.value)}
            />
            <FieldError id={`${idPrefix}-note-error`} message={fieldErrors.note} />
          </div>
          {accentColorField}
          {darkModeField}
        </div>
      );

    case "benefits": {
      const items = asStringList(draft.items, 2);
      return (
        <div className="lblocks__editor">
          {titleField}
          <fieldset className="lblocks__fieldset">
            <legend className="landings-field__label">Beneficios (2 a 5)</legend>
            {items.map((item, index) => (
              <div className="lblocks__row" key={index}>
                <input
                  className="landings-field__input"
                  aria-label={`Beneficio ${index + 1}`}
                  value={item}
                  maxLength={90}
                  onChange={(event) => {
                    const next = [...items];
                    next[index] = event.target.value;
                    set("items", next);
                  }}
                />
                {items.length > 2 && (
                  <button
                    type="button"
                    className="landings-table__action"
                    onClick={() => set("items", items.filter((_, i) => i !== index))}
                  >
                    Quitar
                  </button>
                )}
              </div>
            ))}
            {items.length < 5 && (
              <button
                type="button"
                className="landings-table__action"
                onClick={() => set("items", [...items, ""])}
              >
                Agregar beneficio
              </button>
            )}
            <FieldError id={`${idPrefix}-items-error`} message={fieldErrors.items} />
          </fieldset>
          {accentColorField}
          {darkModeField}
        </div>
      );
    }

    case "offer_price":
      return (
        <div className="lblocks__editor">
          <p className="landings-page__muted">
            El precio de venta se toma del producto, así nunca se desalinea con lo que cobra el
            pedido.
          </p>
          <div className="landings-field">
            <label className="landings-field__label" htmlFor={`${idPrefix}-compare`}>
              Precio anterior (opcional)
            </label>
            <input
              id={`${idPrefix}-compare`}
              className="landings-field__input"
              type="number"
              min={1}
              value={textValue(draft, "compare_at_price")}
              onChange={(event) => set("compare_at_price", event.target.value)}
            />
            <FieldError
              id={`${idPrefix}-compare-error`}
              message={fieldErrors.compare_at_price}
            />
          </div>
          <div className="landings-field">
            <label className="landings-field__label" htmlFor={`${idPrefix}-note`}>
              Nota (opcional)
            </label>
            <input
              id={`${idPrefix}-note`}
              className="landings-field__input"
              value={textValue(draft, "note")}
              maxLength={140}
              onChange={(event) => set("note", event.target.value)}
            />
            <FieldError id={`${idPrefix}-note-error`} message={fieldErrors.note} />
          </div>
          {accentColorField}
          {darkModeField}
        </div>
      );

    case "included_benefits": {
      const items = asRecordList(draft.items);
      return (
        <div className="lblocks__editor">
          {titleField}
          <fieldset className="lblocks__fieldset">
            <legend className="landings-field__label">Beneficios incluidos (2–8)</legend>
            {items.map((item, index) => (
              <div className="lblocks__group" key={index}>
                <input
                  className="landings-field__input"
                  aria-label={`Nombre beneficio ${index + 1}`}
                  placeholder="Nombre del beneficio"
                  value={textValue(item, "name")}
                  maxLength={90}
                  onChange={(event) => {
                    const next = [...items];
                    next[index] = { ...item, name: event.target.value };
                    set("items", next);
                  }}
                />
                <input
                  className="landings-field__input"
                  aria-label={`Valor ${index + 1}`}
                  placeholder="Valor (ej: Valor USD 497)"
                  value={textValue(item, "value")}
                  maxLength={40}
                  onChange={(event) => {
                    const next = [...items];
                    next[index] = { ...item, value: event.target.value };
                    set("items", next);
                  }}
                />
                <input
                  className="landings-field__input"
                  aria-label={`Etiqueta ${index + 1}`}
                  placeholder="Etiqueta (ej: GRATIS)"
                  value={textValue(item, "tag")}
                  maxLength={20}
                  onChange={(event) => {
                    const next = [...items];
                    next[index] = { ...item, tag: event.target.value };
                    set("items", next);
                  }}
                />
                {items.length > 2 && (
                  <button
                    type="button"
                    className="lblocks__remove"
                    aria-label={`Eliminar beneficio ${index + 1}`}
                    onClick={() => {
                      const next = items.filter((_, i) => i !== index);
                      set("items", next);
                    }}
                  >
                    ✕
                  </button>
                )}
              </div>
            ))}
            {items.length < 8 && (
              <button
                type="button"
                className="lblocks__add-item"
                onClick={() => set("items", [...items, { name: "", value: "", tag: "" }])}
              >
                + Agregar beneficio
              </button>
            )}
            <FieldError id={`${idPrefix}-items-error`} message={fieldErrors.items} />
          </fieldset>
          {accentColorField}
          {darkModeField}
        </div>
      );
    }

    case "reviews": {
      const items = asRecordList(draft.items);
      return (
        <div className="lblocks__editor">
          {titleField}
          <fieldset className="lblocks__fieldset">
            <legend className="landings-field__label">Reseñas (hasta 4, reales)</legend>
            {items.map((item, index) => (
              <div className="lblocks__group" key={index}>
                <input
                  className="landings-field__input"
                  aria-label={`Nombre ${index + 1}`}
                  placeholder="Nombre"
                  value={textValue(item, "name")}
                  maxLength={60}
                  onChange={(event) => {
                    const next = [...items];
                    next[index] = { ...item, name: event.target.value };
                    set("items", next);
                  }}
                />
                <input
                  className="landings-field__input"
                  aria-label={`Ciudad ${index + 1}`}
                  placeholder="Ciudad (opcional)"
                  value={textValue(item, "city")}
                  maxLength={60}
                  onChange={(event) => {
                    const next = [...items];
                    next[index] = { ...item, city: event.target.value };
                    set("items", next);
                  }}
                />
                <textarea
                  className="landings-field__input"
                  aria-label={`Reseña ${index + 1}`}
                  placeholder="Lo que dijo el cliente"
                  rows={2}
                  maxLength={280}
                  value={textValue(item, "text")}
                  onChange={(event) => {
                    const next = [...items];
                    next[index] = { ...item, text: event.target.value };
                    set("items", next);
                  }}
                />
                <input
                  className="landings-field__input"
                  aria-label={`Estrellas ${index + 1}`}
                  type="number"
                  min={1}
                  max={5}
                  placeholder="Estrellas 1-5 (opcional)"
                  value={textValue(item, "rating")}
                  onChange={(event) => {
                    const next = [...items];
                    next[index] = { ...item, rating: event.target.value };
                    set("items", next);
                  }}
                />
                {items.length > 1 && (
                  <button
                    type="button"
                    className="landings-table__action"
                    onClick={() => set("items", items.filter((_, i) => i !== index))}
                  >
                    Quitar reseña
                  </button>
                )}
              </div>
            ))}
            {items.length < 4 && (
              <button
                type="button"
                className="landings-table__action"
                onClick={() =>
                  set("items", [...items, { name: "", city: "", text: "", rating: "" }])
                }
              >
                Agregar reseña
              </button>
            )}
            <FieldError id={`${idPrefix}-items-error`} message={fieldErrors.items} />
          </fieldset>
          {accentColorField}
          {darkModeField}
        </div>
      );
    }

    case "faq": {
      const items = asRecordList(draft.items);
      return (
        <div className="lblocks__editor">
          {titleField}
          <fieldset className="lblocks__fieldset">
            <legend className="landings-field__label">Preguntas (hasta 6)</legend>
            {items.map((item, index) => (
              <div className="lblocks__group" key={index}>
                <input
                  className="landings-field__input"
                  aria-label={`Pregunta ${index + 1}`}
                  placeholder="¿Cuánto tarda la entrega?"
                  value={textValue(item, "question")}
                  maxLength={140}
                  onChange={(event) => {
                    const next = [...items];
                    next[index] = { ...item, question: event.target.value };
                    set("items", next);
                  }}
                />
                <textarea
                  className="landings-field__input"
                  aria-label={`Respuesta ${index + 1}`}
                  placeholder="Respuesta"
                  rows={2}
                  maxLength={500}
                  value={textValue(item, "answer")}
                  onChange={(event) => {
                    const next = [...items];
                    next[index] = { ...item, answer: event.target.value };
                    set("items", next);
                  }}
                />
                {items.length > 1 && (
                  <button
                    type="button"
                    className="landings-table__action"
                    onClick={() => set("items", items.filter((_, i) => i !== index))}
                  >
                    Quitar pregunta
                  </button>
                )}
              </div>
            ))}
            {items.length < 6 && (
              <button
                type="button"
                className="landings-table__action"
                onClick={() => set("items", [...items, { question: "", answer: "" }])}
              >
                Agregar pregunta
              </button>
            )}
            <FieldError id={`${idPrefix}-items-error`} message={fieldErrors.items} />
          </fieldset>
          {accentColorField}
          {darkModeField}
        </div>
      );
    }

    case "guarantee":
      return (
        <div className="lblocks__editor">
          {storyTextField("eyebrow", "Etiqueta superior (opcional)", "Compra protegida", 60)}
          <div className="landings-field">
            <label className="landings-field__label" htmlFor={`${idPrefix}-title`}>
              Título
            </label>
            <input
              id={`${idPrefix}-title`}
              className="landings-field__input"
              value={textValue(draft, "title")}
              maxLength={80}
              placeholder="Garantía de satisfacción"
              onChange={(event) => set("title", event.target.value)}
            />
            <FieldError id={`${idPrefix}-title-error`} message={fieldErrors.title} />
          </div>
          <div className="landings-field">
            <label className="landings-field__label" htmlFor={`${idPrefix}-text`}>
              Texto
            </label>
            <textarea
              id={`${idPrefix}-text`}
              className="landings-field__input"
              rows={2}
              maxLength={320}
              value={textValue(draft, "text")}
              onChange={(event) => set("text", event.target.value)}
            />
            <FieldError id={`${idPrefix}-text-error`} message={fieldErrors.text} />
          </div>
          <div className="landings-field">
            <label className="landings-field__label" htmlFor={`${idPrefix}-days`}>
              Días (opcional)
            </label>
            <input
              id={`${idPrefix}-days`}
              className="landings-field__input"
              type="number"
              min={1}
              max={365}
              value={textValue(draft, "days")}
              onChange={(event) => set("days", event.target.value)}
            />
            <FieldError id={`${idPrefix}-days-error`} message={fieldErrors.days} />
          </div>
          <RecordItemsEditor
            legend="Beneficios de la garantía (hasta 4)"
            value={draft.benefits}
            onChange={(items) => set("benefits", items)}
            fields={[
              { key: "title", label: "Título de beneficio", placeholder: "Riesgo cero", maxLength: 80 },
              { key: "text", label: "Texto de beneficio", placeholder: "Tu compra está protegida", maxLength: 280, textarea: true },
            ]}
            maximum={4}
            addLabel="Agregar beneficio"
            removeLabel="Quitar beneficio"
            error={fieldErrors.benefits}
            idPrefix={`${idPrefix}-benefits`}
          />
          {accentColorField}
          {darkModeField}
        </div>
      );

    case "main_problem":
      return (
        <div className="lblocks__editor">
          {storyTextField("eyebrow", "Etiqueta superior (opcional)", "Si esto te suena familiar", 60)}
          {storyTextField("title", "Título", "La razón por la que", 160)}
          {storyTextField("highlight", "Línea destacada (opcional)", "todavía tienes este problema", 160)}
          {storyTextField("subtitle", "Subtítulo (opcional)", "Explica por qué sucede", 320, true)}
          <RecordItemsEditor
            legend="Problemas (hasta 6)"
            value={draft.items}
            onChange={(items) => set("items", items)}
            fields={[
              { key: "title", label: "Título del problema", placeholder: "Problema", maxLength: 80 },
              { key: "text", label: "Descripción del problema", placeholder: "Describe la situación", maxLength: 280, textarea: true },
            ]}
            maximum={6}
            addLabel="Agregar problema"
            removeLabel="Quitar problema"
            error={fieldErrors.items}
            idPrefix={`${idPrefix}-problems`}
          />
          {accentColorField}
          {darkModeField}
        </div>
      );

    case "solution_presentation":
      return (
        <div className="lblocks__editor">
          {storyTextField("bridge_text", "Texto puente (opcional)", "Si te identificaste, esto es para ti", 320, true)}
          {storyTextField("eyebrow", "Etiqueta superior (opcional)", "La solución", 60)}
          {storyTextField("title", "Título", "Presentamos", 160)}
          {storyTextField("highlight", "Línea destacada (opcional)", "TU SOLUCIÓN", 160)}
          {storyTextField("text", "Descripción", "Explica qué es y qué resultado entrega", 500, true)}
          {storyTextField("supporting_text", "Texto de respaldo (opcional)", "Prueba o diferenciador", 500, true)}
          <RecordItemsEditor
            legend="Pilares de la solución (hasta 6)"
            value={draft.items}
            onChange={(items) => set("items", items)}
            fields={[
              { key: "title", label: "Título del pilar", placeholder: "Pilar", maxLength: 80 },
              { key: "text", label: "Descripción del pilar", placeholder: "Qué incluye", maxLength: 280, textarea: true },
              { key: "kicker", label: "Etiqueta del pilar", placeholder: "Módulos 1-3 (opcional)", maxLength: 60 },
            ]}
            maximum={6}
            addLabel="Agregar pilar"
            removeLabel="Quitar pilar"
            error={fieldErrors.items}
            idPrefix={`${idPrefix}-solution-items`}
          />
          {storyTextField("final_title", "Título final (opcional)", "Un solo sistema", 160)}
          {storyTextField("final_highlight", "Línea final destacada (opcional)", "Resultados reales", 160)}
          {accentColorField}
          {darkModeField}
        </div>
      );

    case "how_it_works":
      return (
        <div className="lblocks__editor">
          {storyTextField("title", "Título", "Cómo funciona", 160)}
          {storyTextField("highlight", "Línea destacada (opcional)", "PASO A PASO", 160)}
          {storyTextField("subtitle", "Subtítulo (opcional)", "Un proceso claro", 320)}
          <RecordItemsEditor
            legend="Pasos (hasta 10)"
            value={draft.steps}
            onChange={(items) => set("steps", items)}
            fields={[
              { key: "kicker", label: "Momento del paso", placeholder: "Día 1 / Paso 1", maxLength: 60 },
              { key: "title", label: "Título del paso", placeholder: "Primer paso", maxLength: 80 },
              { key: "text", label: "Descripción del paso", placeholder: "Qué sucede aquí", maxLength: 280, textarea: true },
            ]}
            maximum={10}
            addLabel="Agregar paso"
            removeLabel="Quitar paso"
            error={fieldErrors.steps}
            idPrefix={`${idPrefix}-steps`}
          />
          {accentColorField}
          {darkModeField}
        </div>
      );

    case "audience":
      return (
        <div className="lblocks__editor">
          {storyTextField("title", "Título", "Para quién es", 160)}
          {storyTextField("highlight", "Línea destacada (opcional)", "este producto", 160)}
          {storyTextField("positive_title", "Título positivo", "ES PARA TI", 80)}
          {storyTextField("positive_subtitle", "Subtítulo positivo (opcional)", "Si te identificas", 140)}
          <StringItemsEditor
            legend="Sí es para"
            value={draft.positive_items}
            onChange={(items) => set("positive_items", items)}
            maximum={10}
            addLabel="Agregar perfil positivo"
            error={fieldErrors.positive_items}
            idPrefix={`${idPrefix}-positive`}
          />
          {storyTextField("negative_title", "Título negativo", "NO ES PARA TI", 80)}
          {storyTextField("negative_subtitle", "Subtítulo negativo (opcional)", "Si buscas esto", 140)}
          <StringItemsEditor
            legend="No es para"
            value={draft.negative_items}
            onChange={(items) => set("negative_items", items)}
            maximum={10}
            addLabel="Agregar perfil negativo"
            error={fieldErrors.negative_items}
            idPrefix={`${idPrefix}-negative`}
          />
          {storyTextField("footer", "Cierre (opcional)", "Aclara aquí una condición importante", 320, true)}
          {accentColorField}
          {darkModeField}
        </div>
      );

    case "moment":
      return (
        <div className="lblocks__editor">
          {storyTextField("title", "Título", "¿Sigues esperando el", 160)}
          {storyTextField("highlight", "Línea destacada", "momento perfecto?", 160)}
          {storyTextField("text", "Texto", "El momento perfecto no existe", 320, true)}
          {storyTextField("emphasis", "Frase enfatizada (opcional)", "Actúa aunque no esté todo listo", 320)}
          {storyTextField("footer", "Texto final (opcional)", "Mientras lees esto, otros ya empezaron", 320)}
          {accentColorField}
          {darkModeField}
        </div>
      );

    default:
      return <div />;
  }
}

export function LandingBlocksPanel({
  landingId,
  sequenceSignature,
  defaultAccentColor,
}: LandingBlocksPanelProps): JSX.Element {
  const [blocks, setBlocks] = useState<LandingBlock[]>([]);
  const [slots, setSlots] = useState<string[]>([]);
  const [newType, setNewType] = useState<ConversionBlockType>("cod_assurance");
  const [newSlot, setNewSlot] = useState(1);
  const [newDraft, setNewDraft] = useState<Draft>(() => defaultDraft("cod_assurance"));
  const [editingId, setEditingId] = useState<number | null>(null);
  const [editDraft, setEditDraft] = useState<Draft>({});
  const [fieldErrors, setFieldErrors] = useState<Record<string, string>>({});
  const [error, setError] = useState<string | null>(null);
  const [notice, setNotice] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);
  const [confirmDeleteId, setConfirmDeleteId] = useState<number | null>(null);

  const load = useCallback(async () => {
    try {
      const response = await landingsApi.listBlocks(landingId);
      setBlocks(response.blocks);
      setSlots(response.slots);
    } catch (err) {
      setError(
        err instanceof ApiError ? err.message : "No se pudieron cargar los componentes.",
      );
    }
  }, [landingId]);

  useEffect(() => {
    void load();
    // `sequenceSignature` changes when banners or CTA positions change, which
    // changes the available positions.
  }, [load, sequenceSignature]);

  function reset() {
    setError(null);
    setNotice(null);
    setFieldErrors({});
  }

  function handleFailure(err: unknown, fallback: string) {
    if (err instanceof ApiError) {
      setError(err.message);
      if (err.fieldErrors) setFieldErrors(err.fieldErrors);
    } else {
      setError(fallback);
    }
  }

  function slotLabel(slotIndex: number): string {
    return slots[slotIndex] ?? `${slotIndex}-${slotIndex + 1} · al final`;
  }

  async function handleCreate(event: React.FormEvent) {
    event.preventDefault();
    reset();
    setBusy(true);
    try {
      const response = await landingsApi.createBlock(landingId, {
        block_type: newType,
        slot_index: newSlot,
        config: newDraft,
      });
      setBlocks(response.blocks);
      setSlots(response.slots);
      setNewDraft(defaultDraft(newType));
      setNotice(`Componente "${BLOCK_TYPES[newType].label}" agregado.`);
    } catch (err) {
      handleFailure(err, "No se pudo agregar el componente.");
    } finally {
      setBusy(false);
    }
  }

  async function handleSaveEdit(blockId: number) {
    reset();
    setBusy(true);
    try {
      const response = await landingsApi.updateBlock(landingId, blockId, { config: editDraft });
      setBlocks(response.blocks);
      setEditingId(null);
      setNotice("Contenido actualizado.");
    } catch (err) {
      handleFailure(err, "No se pudo guardar el contenido.");
    } finally {
      setBusy(false);
    }
  }

  async function handleMove(block: LandingBlock, slotIndex: number) {
    reset();
    setBusy(true);
    try {
      const response = await landingsApi.updateBlock(landingId, block.id, {
        slot_index: slotIndex,
      });
      setBlocks(response.blocks);
      setNotice(`Movido a ${slotLabel(slotIndex)}.`);
    } catch (err) {
      handleFailure(err, "No se pudo mover el componente.");
    } finally {
      setBusy(false);
    }
  }

  async function handleToggle(block: LandingBlock) {
    reset();
    setBusy(true);
    try {
      const response = await landingsApi.updateBlock(landingId, block.id, {
        enabled: !block.enabled,
      });
      setBlocks(response.blocks);
    } catch (err) {
      handleFailure(err, "No se pudo cambiar el estado del componente.");
    } finally {
      setBusy(false);
    }
  }

  async function handleDelete(blockId: number) {
    reset();
    setBusy(true);
    try {
      const response = await landingsApi.deleteBlock(landingId, blockId);
      setBlocks(response.blocks);
      setConfirmDeleteId(null);
      setNotice("Componente eliminado.");
    } catch (err) {
      handleFailure(err, "No se pudo eliminar el componente.");
    } finally {
      setBusy(false);
    }
  }

  return (
    <section className="landings-panel" aria-labelledby="blocks-heading">
      <h2 className="landings-panel__title" id="blocks-heading">
        Componentes de conversión
      </h2>
      <p className="landings-page__muted">
        Se insertan entre los elementos de la landing. Las posiciones se numeran como
        &quot;1-2&quot; (entre el primer y el segundo elemento). El diseño de cada componente
        es fijo: tú eliges cuál, dónde y qué dice.
      </p>

      {error && (
        <p className="landings-page__error" role="alert">
          {error}
        </p>
      )}
      {notice && (
        <p className="landings-page__notice" role="status">
          {notice}
        </p>
      )}

      {blocks.length === 0 ? (
        <p className="landings-page__muted">
          Todavía no hay componentes. Agrega el de pago contraentrega para empezar: es el que
          más objeciones quita en venta contraentrega.
        </p>
      ) : (
        <ul className="lblocks__list" aria-label="Componentes colocados">
          {blocks.map((block) => (
            <li className="lblocks__item" key={block.id}>
              <div className="lblocks__item-head">
                <div>
                  <p className="lblocks__item-title">{BLOCK_TYPES[block.block_type].label}</p>
                  <p className="landings-page__muted">
                    Posición actual: {slotLabel(block.slot_index)}
                  </p>
                </div>
                <div className="lblocks__item-actions">
                  <label className="lblocks__toggle">
                    <input
                      type="checkbox"
                      checked={block.enabled}
                      disabled={busy}
                      onChange={() => void handleToggle(block)}
                    />
                    Visible
                  </label>
                  <button
                    type="button"
                    className="landings-table__action"
                    onClick={() => {
                      reset();
                      setEditingId(editingId === block.id ? null : block.id);
                      setEditDraft(draftFromBlock(block));
                    }}
                  >
                    {editingId === block.id ? "Cerrar" : "Editar contenido"}
                  </button>
                  {confirmDeleteId === block.id ? (
                    <>
                      <button
                        type="button"
                        className="landings-table__action landings-table__action--danger"
                        disabled={busy}
                        onClick={() => void handleDelete(block.id)}
                      >
                        Confirmar
                      </button>
                      <button
                        type="button"
                        className="landings-table__action"
                        onClick={() => setConfirmDeleteId(null)}
                      >
                        Cancelar
                      </button>
                    </>
                  ) : (
                    <button
                      type="button"
                      className="landings-table__action landings-table__action--danger"
                      onClick={() => setConfirmDeleteId(block.id)}
                    >
                      Eliminar
                    </button>
                  )}
                </div>
              </div>

              <div className="landings-field">
                <label
                  className="landings-field__label"
                  htmlFor={`block-${block.id}-slot`}
                >
                  Posición
                </label>
                <select
                  id={`block-${block.id}-slot`}
                  className="landings-field__input"
                  value={block.slot_index}
                  disabled={busy}
                  onChange={(event) => void handleMove(block, Number(event.target.value))}
                >
                  {slots.map((label, index) => (
                    <option key={label} value={index}>
                      {label}
                    </option>
                  ))}
                  {block.slot_index >= slots.length && (
                    <option value={block.slot_index}>{slotLabel(block.slot_index)}</option>
                  )}
                </select>
              </div>

              {editingId === block.id && (
                <div className="lblocks__edit">
                  <ContentEditor
                    type={block.block_type}
                    draft={editDraft}
                    onChange={setEditDraft}
                    idPrefix={`block-${block.id}`}
                    // Errors belong to the editor that submitted: showing them
                    // in both this panel and the add form below would announce
                    // the same problem twice.
                    fieldErrors={editingId === block.id ? fieldErrors : {}}
                    defaultAccentColor={defaultAccentColor}
                  />
                  <button
                    type="button"
                    className="landings-table__action landings-table__action--primary"
                    disabled={busy}
                    onClick={() => void handleSaveEdit(block.id)}
                  >
                    Guardar contenido
                  </button>
                </div>
              )}
            </li>
          ))}
        </ul>
      )}

      <form className="lblocks__add" onSubmit={handleCreate} aria-label="Agregar componente">
        <h3 className="lblocks__add-title">Agregar componente</h3>

        <div className="landings-field">
          <label className="landings-field__label" htmlFor="new-block-type">
            Componente
          </label>
          <select
            id="new-block-type"
            className="landings-field__input"
            value={newType}
            onChange={(event) => {
              const type = event.target.value as ConversionBlockType;
              setNewType(type);
              setNewDraft(defaultDraft(type));
              setFieldErrors({});
            }}
          >
            {BLOCK_TYPE_ORDER.map((type) => (
              <option key={type} value={type}>
                {BLOCK_TYPES[type].label}
              </option>
            ))}
          </select>
          <p className="landings-page__muted">{BLOCK_TYPES[newType].purpose}</p>
          <FieldError id="new-block-type-error" message={fieldErrors.block_type} />
        </div>

        <div className="landings-field">
          <label className="landings-field__label" htmlFor="new-block-slot">
            Posición
          </label>
          <select
            id="new-block-slot"
            className="landings-field__input"
            value={newSlot}
            onChange={(event) => setNewSlot(Number(event.target.value))}
          >
            {slots.map((label, index) => (
              <option key={label} value={index}>
                {label}
              </option>
            ))}
          </select>
          <FieldError id="new-block-slot-error" message={fieldErrors.slot_index} />
        </div>

        <ContentEditor
          type={newType}
          draft={newDraft}
          onChange={setNewDraft}
          idPrefix="new-block"
          fieldErrors={editingId === null ? fieldErrors : {}}
          defaultAccentColor={defaultAccentColor}
        />

        <button
          type="submit"
          className="landings-table__action landings-table__action--primary"
          disabled={busy}
        >
          Agregar componente
        </button>
      </form>
    </section>
  );
}
