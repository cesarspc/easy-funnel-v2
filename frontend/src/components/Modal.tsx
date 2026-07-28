/**
 * Accessible pop-up dialog with focus capture/return (Requirements 3.17-3.18,
 * 8.19-8.20). This is how the public COD form is presented: the CTA opens it
 * over the banner sequence instead of the form living at the end of the page.
 *
 * Three behaviors matter for a cold-traffic buyer on a phone:
 * - It renders through a portal on `document.body`, so no banner or CTA band
 *   ancestor can clip it with `overflow`/`transform`.
 * - Focus moves to the dialog panel, not to the first field. Focusing an
 *   input would raise the on-screen keyboard immediately and hide the offer
 *   recap the buyer just opened; they tap the first field themselves.
 * - Escape and a backdrop tap both close it, and focus returns to the CTA
 *   that opened it.
 */

import { useRef, useEffect, useId, type ReactNode, type JSX } from "react";
import { createPortal } from "react-dom";
import "./Modal.css";

export interface ModalProps {
  /** Whether the modal is open */
  isOpen: boolean;
  /** Callback when modal closes */
  onClose: () => void;
  /** Modal title */
  title: string;
  /** Optional line under the title (offer recap, reassurance) */
  subtitle?: ReactNode;
  /** Modal content */
  children: ReactNode;
  /** Optional ARIA description */
  ariaDescription?: string;
}

const FOCUSABLE_SELECTOR =
  'button:not([disabled]), [href], input:not([disabled]), select:not([disabled]), textarea:not([disabled]), [tabindex]:not([tabindex="-1"])';

/**
 * Renders an accessible modal dialog overlay.
 * - Traps focus inside the modal
 * - Closes on Escape or backdrop tap
 * - Returns focus to the activating element on close
 * - Prevents background scroll
 */
export function Modal({
  isOpen,
  onClose,
  title,
  subtitle,
  children,
  ariaDescription,
}: ModalProps): JSX.Element | null {
  const panelRef = useRef<HTMLDivElement>(null);
  const previouslyFocusedRef = useRef<HTMLElement | null>(null);
  const baseId = useId();
  const titleId = `${baseId}-title`;
  const descriptionId = `${baseId}-description`;

  useEffect(() => {
    if (!isOpen) return;

    if (document.activeElement instanceof HTMLElement) {
      previouslyFocusedRef.current = document.activeElement;
    }

    const handleKeyDown = (e: KeyboardEvent) => {
      if (e.key === "Escape") {
        onClose();
        return;
      }

      if (e.key === "Tab" && panelRef.current) {
        const focusable = Array.from(
          panelRef.current.querySelectorAll<HTMLElement>(FOCUSABLE_SELECTOR),
        ).filter((element) => element.offsetParent !== null || element === document.activeElement);
        if (focusable.length === 0) return;

        const first = focusable[0];
        const last = focusable[focusable.length - 1];

        if (e.shiftKey && document.activeElement === first) {
          e.preventDefault();
          last.focus();
        } else if (!e.shiftKey && document.activeElement === last) {
          e.preventDefault();
          first.focus();
        }
      }
    };

    document.addEventListener("keydown", handleKeyDown);
    const previousOverflow = document.body.style.overflow;
    document.body.style.overflow = "hidden";

    // The panel itself takes focus so screen readers announce the dialog and
    // its recap, without the keyboard covering the sheet on a phone.
    panelRef.current?.focus();

    return () => {
      document.removeEventListener("keydown", handleKeyDown);
      document.body.style.overflow = previousOverflow;
      previouslyFocusedRef.current?.focus();
    };
  }, [isOpen, onClose]);

  if (!isOpen) return null;

  return createPortal(
    <div
      className="modal-backdrop"
      // A tap on the backdrop closes; a tap that started inside the sheet and
      // ended on the backdrop (drag-select) does not, because the handler only
      // fires when the target is the backdrop itself.
      onMouseDown={(event) => {
        if (event.target === event.currentTarget) onClose();
      }}
    >
      <div
        className="modal"
        ref={panelRef}
        role="dialog"
        aria-modal="true"
        aria-labelledby={titleId}
        aria-describedby={ariaDescription ? descriptionId : undefined}
        tabIndex={-1}
      >
        <div className="modal-header">
          <div className="modal-heading">
            <h2 id={titleId} className="modal-title">
              {title}
            </h2>
            {subtitle && <p className="modal-subtitle">{subtitle}</p>}
          </div>
          <button
            type="button"
            className="modal-close"
            onClick={onClose}
            aria-label="Cerrar"
          >
            <span aria-hidden="true">&times;</span>
          </button>
        </div>
        <div className="modal-body">
          {ariaDescription && (
            <p id={descriptionId} className="sr-only">
              {ariaDescription}
            </p>
          )}
          {children}
        </div>
      </div>
    </div>,
    document.body,
  );
}
