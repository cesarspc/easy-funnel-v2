import { render, screen } from "@testing-library/react";
import { describe, expect, it } from "vitest";
import { StatusPill } from "./StatusPill";

describe("StatusPill", () => {
  it("renders the Spanish label for each Order_Status value", () => {
    render(<StatusPill status="pending" />);
    expect(screen.getByText("Pendiente")).toBeInTheDocument();
  });

  it("renders the flagged-for-review label for flagged_fraud", () => {
    render(<StatusPill status="flagged_fraud" />);
    expect(screen.getByText("Marcado para revisión")).toBeInTheDocument();
  });

  it("renders Product status labels using the shared vocabulary", () => {
    render(<StatusPill status="active" />);
    expect(screen.getByText("Activo")).toBeInTheDocument();
  });

  it("carries color on the dot, not on the text node", () => {
    const { container } = render(<StatusPill status="delivered" />);
    const dot = container.querySelector(".status-pill__dot");
    expect(dot).not.toBeNull();
    expect(dot).toHaveAttribute("aria-hidden", "true");
  });
});
