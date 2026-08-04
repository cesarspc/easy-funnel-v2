/**
 * Conversion components panel (Requirements 3.27-3.31, 8.19).
 *
 * Covers what the Administrator actually does: read the placement slots the
 * backend derived from the sequence, place a component in one of them, move it,
 * hide it, remove it — and see a field-specific error bound to its control when
 * the content is incomplete.
 */

import { render, screen, waitFor, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { LandingBlocksPanel } from "./LandingBlocksPanel";
import { ApiError, landingsApi } from "../../api";
import type { LandingBlock, LandingBlockListResponse } from "../../api";

vi.mock("../../api", async () => {
  const actual = await vi.importActual<typeof import("../../api")>("../../api");
  return {
    ...actual,
    landingsApi: {
      listBlocks: vi.fn(),
      createBlock: vi.fn(),
      updateBlock: vi.fn(),
      deleteBlock: vi.fn(),
    },
  };
});

/** 3 banners with a CTA after each: 6 elements, so 7 slots. */
const SLOTS = [
  "0-1 · antes de banner 1",
  "1-2 · entre banner 1 y CTA 1",
  "2-3 · entre CTA 1 y banner 2",
  "3-4 · entre banner 2 y CTA 2",
  "4-5 · entre CTA 2 y banner 3",
  "5-6 · entre banner 3 y CTA 3",
  "6-7 · entre CTA 3 y el final",
];

function response(blocks: LandingBlock[]): LandingBlockListResponse {
  return {
    blocks,
    slots: SLOTS,
    allowed_block_types: [
      "cod_assurance",
      "benefits",
      "offer_price",
      "how_it_works",
      "reviews",
      "faq",
      "guarantee",
    ],
  };
}

const ASSURANCE: LandingBlock = {
  id: 11,
  block_type: "cod_assurance",
  slot_index: 1,
  order_index: 0,
  enabled: true,
  config: { note: "Cobertura nacional" },
};

function renderPanel() {
  return render(<LandingBlocksPanel landingId={7} sequenceSignature="3:1,2,3" />);
}

describe("LandingBlocksPanel", () => {
  beforeEach(() => {
    vi.mocked(landingsApi.listBlocks).mockResolvedValue(response([]));
  });

  afterEach(() => {
    vi.clearAllMocks();
  });

  it("offers every placement slot of the sequence, labelled as the merchant reads them", async () => {
    renderPanel();

    const positionSelect = await screen.findByLabelText("Posición");
    const options = Array.from(positionSelect.querySelectorAll("option")).map(
      (option) => option.textContent,
    );
    expect(options).toHaveLength(7);
    expect(options[1]).toBe("1-2 · entre banner 1 y CTA 1");
    expect(options[2]).toBe("2-3 · entre CTA 1 y banner 2");
  });

  it("lists the seven pre-defined components with what each one is for", async () => {
    renderPanel();

    const typeSelect = await screen.findByLabelText("Componente");
    expect(typeSelect.querySelectorAll("option")).toHaveLength(7);
    expect(screen.getByText(/Quita el miedo a pagar por adelantado/)).toBeInTheDocument();
  });

  it("exposes no presentation control at all", async () => {
    renderPanel();
    await screen.findByLabelText("Componente");

    for (const forbidden of [/padding/i, /color/i, /tipografía/i, /ancho/i, /margen/i, /fondo/i]) {
      expect(screen.queryByLabelText(forbidden)).not.toBeInTheDocument();
    }
  });

  it("places a component in the chosen slot", async () => {
    vi.mocked(landingsApi.createBlock).mockResolvedValue(response([ASSURANCE]));
    const user = userEvent.setup();
    renderPanel();

    const addForm = await screen.findByRole("form", { name: "Agregar componente" });
    await user.selectOptions(within(addForm).getByLabelText("Posición"), "1");
    await user.type(
      within(addForm).getByLabelText("Nota adicional (opcional)"),
      "Cobertura nacional",
    );
    await user.click(within(addForm).getByRole("button", { name: "Agregar componente" }));

    await waitFor(() =>
      expect(landingsApi.createBlock).toHaveBeenCalledWith(7, {
        block_type: "cod_assurance",
        slot_index: 1,
        config: { note: "Cobertura nacional" },
      }),
    );
    const list = await screen.findByRole("list", { name: "Componentes colocados" });
    expect(within(list).getByText("Pago contraentrega")).toBeInTheDocument();
    expect(
      within(list).getByText("Posición actual: 1-2 · entre banner 1 y CTA 1"),
    ).toBeInTheDocument();
  });

  it("sends exactly three steps for the how-it-works component", async () => {
    vi.mocked(landingsApi.createBlock).mockResolvedValue(response([]));
    const user = userEvent.setup();
    renderPanel();

    await user.selectOptions(await screen.findByLabelText("Componente"), "how_it_works");
    await user.click(screen.getByRole("button", { name: "Agregar componente" }));

    await waitFor(() => expect(landingsApi.createBlock).toHaveBeenCalled());
    const payload = vi.mocked(landingsApi.createBlock).mock.calls[0][1];
    expect((payload.config.steps as string[]).length).toBe(3);
  });

  it("binds a field-specific rejection to the control that produced it", async () => {
    vi.mocked(landingsApi.createBlock).mockRejectedValue(
      new ApiError(422, "Add between 2 and 5 benefits.", {
        items: "Add between 2 and 5 benefits.",
      }),
    );
    const user = userEvent.setup();
    renderPanel();

    await user.selectOptions(await screen.findByLabelText("Componente"), "benefits");
    await user.click(screen.getByRole("button", { name: "Agregar componente" }));

    const addForm = await screen.findByRole("form", { name: "Agregar componente" });
    expect(
      await within(addForm).findByText("Add between 2 and 5 benefits."),
    ).toBeInTheDocument();
  });

  it("moves a placed component to another slot", async () => {
    vi.mocked(landingsApi.listBlocks).mockResolvedValue(response([ASSURANCE]));
    vi.mocked(landingsApi.updateBlock).mockResolvedValue(
      response([{ ...ASSURANCE, slot_index: 4 }]),
    );
    const user = userEvent.setup();
    renderPanel();

    const list = await screen.findByRole("list", { name: "Componentes colocados" });
    await user.selectOptions(within(list).getByLabelText("Posición"), "4");

    await waitFor(() =>
      expect(landingsApi.updateBlock).toHaveBeenCalledWith(7, 11, { slot_index: 4 }),
    );
    expect(
      await within(list).findByText("Posición actual: 4-5 · entre CTA 2 y banner 3"),
    ).toBeInTheDocument();
  });

  it("hides a component from the public landing without deleting it", async () => {
    vi.mocked(landingsApi.listBlocks).mockResolvedValue(response([ASSURANCE]));
    vi.mocked(landingsApi.updateBlock).mockResolvedValue(
      response([{ ...ASSURANCE, enabled: false }]),
    );
    const user = userEvent.setup();
    renderPanel();

    await user.click(await screen.findByLabelText("Visible"));

    await waitFor(() =>
      expect(landingsApi.updateBlock).toHaveBeenCalledWith(7, 11, { enabled: false }),
    );
    expect(await screen.findByLabelText("Visible")).not.toBeChecked();
  });

  it("requires confirmation before removing a component", async () => {
    vi.mocked(landingsApi.listBlocks).mockResolvedValue(response([ASSURANCE]));
    vi.mocked(landingsApi.deleteBlock).mockResolvedValue(response([]));
    const user = userEvent.setup();
    renderPanel();

    await user.click(await screen.findByRole("button", { name: "Eliminar" }));
    expect(landingsApi.deleteBlock).not.toHaveBeenCalled();

    await user.click(screen.getByRole("button", { name: "Confirmar" }));
    await waitFor(() => expect(landingsApi.deleteBlock).toHaveBeenCalledWith(7, 11));
  });

  it("edits the content of a placed component", async () => {
    vi.mocked(landingsApi.listBlocks).mockResolvedValue(response([ASSURANCE]));
    vi.mocked(landingsApi.updateBlock).mockResolvedValue(response([ASSURANCE]));
    const user = userEvent.setup();
    renderPanel();

    const list = await screen.findByRole("list", { name: "Componentes colocados" });
    await user.click(within(list).getByRole("button", { name: "Editar contenido" }));
    const note = within(list).getByLabelText("Nota adicional (opcional)");
    await user.clear(note);
    await user.type(note, "Entrega en 1 a 3 días");
    await user.click(within(list).getByRole("button", { name: "Guardar contenido" }));

    await waitFor(() =>
      expect(landingsApi.updateBlock).toHaveBeenCalledWith(7, 11, {
        config: { note: "Entrega en 1 a 3 días" },
      }),
    );
  });

  it("keeps showing a component whose slot no longer exists in the sequence", async () => {
    vi.mocked(landingsApi.listBlocks).mockResolvedValue(
      response([{ ...ASSURANCE, slot_index: 20 }]),
    );
    renderPanel();

    const list = await screen.findByRole("list", { name: "Componentes colocados" });
    expect(within(list).getByText("Posición actual: 20-21 · al final")).toBeInTheDocument();
  });

  it("reports a load failure instead of rendering an empty panel silently", async () => {
    vi.mocked(landingsApi.listBlocks).mockRejectedValue(new ApiError(500, "Boom"));
    renderPanel();

    expect(await screen.findByRole("alert")).toHaveTextContent("Boom");
  });
});
