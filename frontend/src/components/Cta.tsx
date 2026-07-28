/** CTA (Call to Action) control (Requirement 3.12-3.14). */

import type { ButtonHTMLAttributes, ReactNode, JSX } from "react";
import "./Cta.css";

export interface CtaProps extends ButtonHTMLAttributes<HTMLButtonElement> {
  /** CTA text */
  label: string;
  /** Optional icon */
  icon?: ReactNode;
  /** Whether the CTA is disabled */
  disabled?: boolean;
  /** Optional click handler */
  onClick?: () => void;
}

/**
 * Renders a CTA control for COD order activation.
 */
export function Cta({ label, icon, disabled, onClick, ...props }: CtaProps): JSX.Element {
  return (
    <button
      type="button"
      onClick={onClick}
      disabled={disabled}
      className="cta-button"
      {...props}
    >
      {icon && <span className="cta-icon">{icon}</span>}
      <span className="cta-label">{label}</span>
    </button>
  );
}
