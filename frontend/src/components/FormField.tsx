/** Accessible form fields with error mapping (Requirement 8.19). */

import type { InputHTMLAttributes, ReactNode, JSX } from "react";
import "./FormField.css";

export interface FormFieldProps extends InputHTMLAttributes<HTMLInputElement | HTMLTextAreaElement> {
  /** Field name */
  name: string;
  /** Field label */
  label: string;
  /** Error message for this field */
  error?: string;
  /** Optional description */
  description?: string;
  /** Optional icon */
  icon?: ReactNode;
  /** Optional textarea instead of input */
  textarea?: boolean;
  /**
   * Fixed value implied for the control (e.g. the `+57` country code) that
   * is never part of the editable value and never shown to the buyer — the
   * placeholder and numeric keyboard already communicate the expected
   * format, so a visible prefix chip only added visual noise without
   * changing how the phone number itself is captured or submitted.
   */
  prefixText?: ReactNode;
  /**
   * Optional autocomplete suggestions rendered as a native `<datalist>`.
   * The control stays free text, so a value outside the list still submits —
   * the list only saves typing on a phone keyboard.
   */
  suggestions?: readonly string[];
}

/**
 * Renders an accessible form field with error support.
 * Maps backend field errors to form controls.
 */
export function FormField({
  name,
  label,
  error,
  description,
  icon,
  textarea = false,
  prefixText,
  suggestions,
  ...props
}: FormFieldProps): JSX.Element {
  const baseClass = "form-field";
  const inputClass = error ? `${baseClass}-input--error` : `${baseClass}-input`;

  const InputElement = textarea ? "textarea" : "input";
  const listId = suggestions ? `${name}-options` : undefined;

  const describedBy =
    [error ? `${name}-error` : null, description ? `${name}-description` : null]
      .filter(Boolean)
      .join(" ") || undefined;

  const control = (
    <InputElement
      id={name}
      name={name}
      className={inputClass}
      aria-invalid={!!error}
      aria-describedby={describedBy}
      list={listId}
      {...props}
    />
  );

  return (
    <div className={baseClass} data-field-name={name}>
      <label htmlFor={name} className={`${baseClass}-label`}>
        {icon && <span className={`${baseClass}-icon`}>{icon}</span>}
        {label}
      </label>

      {description && (
        <p className={`${baseClass}-description`} id={`${name}-description`}>
          {description}
        </p>
      )}

      {prefixText ? (
        <div className={`${inputClass} form-field-input--prefixed`} data-has-prefix="true">
          <InputElement
            id={name}
            name={name}
            className="form-field-input--prefixed-control"
            aria-invalid={!!error}
            aria-describedby={describedBy}
            list={listId}
            {...props}
          />
        </div>
      ) : (
        control
      )}

      {suggestions && (
        <datalist id={listId}>
          {suggestions.map((option) => (
            <option key={option} value={option} />
          ))}
        </datalist>
      )}

      {error && (
        <p className={`${baseClass}-error`} id={`${name}-error`} role="alert">
          {error}
        </p>
      )}
    </div>
  );
}
