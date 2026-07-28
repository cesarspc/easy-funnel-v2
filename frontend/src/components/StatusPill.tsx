/**
 * Status pill for Order_Status (and Product status). Renders as a quiet
 * dot + label — the dot carries the color, never a filled background or
 * colored text, per DESIGN.md's Named Status Only Rule.
 */

import type { JSX } from "react";
import "./StatusPill.css";

export type OrderStatus =
  | "pending"
  | "confirmed"
  | "shipped"
  | "delivered"
  | "cancelled"
  | "flagged_fraud";

export type ProductStatus = "active" | "paused" | "retired";

export type LandingStatus = "draft" | "published";

export type PillStatus = OrderStatus | ProductStatus | LandingStatus;

const LABELS: Record<PillStatus, string> = {
  pending: "Pendiente",
  confirmed: "Confirmado",
  shipped: "Enviado",
  delivered: "Entregado",
  cancelled: "Cancelado",
  flagged_fraud: "Marcado para revisión",
  active: "Activo",
  paused: "Pausado",
  retired: "Retirado",
  draft: "Borrador",
  published: "Publicado",
};

// Product statuses map onto the same visual vocabulary as the closest
// semantic Order_Status meaning, per DESIGN.md's fixed named palette.
const TONE_CLASS: Record<PillStatus, string> = {
  pending: "status-pill--pending",
  confirmed: "status-pill--confirmed",
  shipped: "status-pill--shipped",
  delivered: "status-pill--delivered",
  cancelled: "status-pill--cancelled",
  flagged_fraud: "status-pill--flagged",
  active: "status-pill--delivered",
  paused: "status-pill--pending",
  retired: "status-pill--cancelled",
  draft: "status-pill--pending",
  published: "status-pill--delivered",
};

export interface StatusPillProps {
  status: PillStatus;
}

export function StatusPill({ status }: StatusPillProps): JSX.Element {
  return (
    <span className={`status-pill ${TONE_CLASS[status]}`}>
      <span className="status-pill__dot" aria-hidden="true" />
      {LABELS[status]}
    </span>
  );
}
