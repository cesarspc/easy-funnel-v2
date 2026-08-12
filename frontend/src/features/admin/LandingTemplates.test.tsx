import { render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { afterEach, describe, expect, it, vi } from "vitest";
import { LoadTemplateDialog, SaveTemplateControl } from "./LandingTemplates";
import { ApiError, landingTemplatesApi, landingsApi } from "../../api";
import type { LandingDetail, LandingTemplate } from "../../api";

vi.mock("../../api", async () => {
  const actual = await vi.importActual<typeof import("../../api")>("../../api");
  return {
    ...actual,
    landingTemplatesApi: {
      list: vi.fn(),
      save: vi.fn(),
      remove: vi.fn(),
    },
    landingsApi: {
      loadTemplate: vi.fn(),
    },
  };
});

function template(overrides: Partial<LandingTemplate> = {}): LandingTemplate {
  return {
    id: 1,
    name: "Suplementos",
    banner_count: 3,
    block_count: 2,
    created_at: "2026-08-11T00:00:00+00:00",
    updated_at: "2026-08-11T00:00:00+00:00",
    ...overrides,
  };
}

const LOADED_DETAIL = {
  id: 7,
  product_id: 3,
  product_name: "Audífonos",
  product_sku: "AUD-001",
  product_status: "active",
  slug: "audifonos",
  status: "draft",
  cta_mode: "after_every",
  cta_interval: null,
  cta_positions: [],
  form_presentation: "inline",
  cta_band_style: "gradient",
  accent_color: "#2563eb",
  form_accent_color: null,
  offer_count: 3,
  offers: [],
  banner_count: 3,
  cta_text: null,
  cta_animation: null,
  cta_text_overrides: {},
  blocks_dark_mode: false,
  banners: [],
  resolved_cta_positions: [],
} as unknown as LandingDetail;

afterEach(() => {
  vi.clearAllMocks();
});

describe("SaveTemplateControl", () => {
  it("states that images are excluded and which banner count the template will require", () => {
    render(<SaveTemplateControl landingId={7} bannerCount={3} />);

    const hint = screen.getByText(/No guarda las imágenes/);
    expect(hint).toHaveTextContent("3 banners");
  });

  it("uses singular wording for a one-banner landing", () => {
    render(<SaveTemplateControl landingId={7} bannerCount={1} />);

    expect(screen.getByText(/No guarda las imágenes/)).toHaveTextContent("1 banner");
  });

  it("cannot be submitted until a name is typed", async () => {
    const user = userEvent.setup();
    render(<SaveTemplateControl landingId={7} bannerCount={2} />);

    const button = screen.getByRole("button", { name: "Guardar plantilla" });
    expect(button).toBeDisabled();

    await user.type(screen.getByLabelText(/Guardar esta configuración/), "Mi funnel");

    expect(button).toBeEnabled();
  });

  it("saves the configuration under the typed name", async () => {
    const user = userEvent.setup();
    vi.mocked(landingTemplatesApi.save).mockResolvedValue(template({ name: "Mi funnel" }));
    render(<SaveTemplateControl landingId={7} bannerCount={2} />);

    await user.type(screen.getByLabelText(/Guardar esta configuración/), "Mi funnel");
    await user.click(screen.getByRole("button", { name: "Guardar plantilla" }));

    expect(landingTemplatesApi.save).toHaveBeenCalledWith({
      landing_id: 7,
      name: "Mi funnel",
      overwrite: false,
    });
    expect(await screen.findByRole("status")).toHaveTextContent(
      "Plantilla «Mi funnel» guardada.",
    );
  });

  it("asks before replacing a template whose name is already used", async () => {
    const user = userEvent.setup();
    vi.mocked(landingTemplatesApi.save).mockRejectedValueOnce(
      new ApiError(409, "Ya existe una plantilla llamada «Mi funnel».", {
        name: "Ya existe una plantilla llamada «Mi funnel».",
      }),
    );
    render(<SaveTemplateControl landingId={7} bannerCount={2} />);

    await user.type(screen.getByLabelText(/Guardar esta configuración/), "Mi funnel");
    await user.click(screen.getByRole("button", { name: "Guardar plantilla" }));

    // The conflict is surfaced and nothing was overwritten yet.
    expect(await screen.findByRole("alert")).toHaveTextContent("Ya existe una plantilla");
    expect(screen.getByRole("button", { name: "Reemplazar" })).toBeInTheDocument();
    expect(landingTemplatesApi.save).toHaveBeenCalledTimes(1);
  });

  it("overwrites only after the merchant confirms", async () => {
    const user = userEvent.setup();
    vi.mocked(landingTemplatesApi.save)
      .mockRejectedValueOnce(new ApiError(409, "Ya existe una plantilla llamada «Mi funnel»."))
      .mockResolvedValueOnce(template({ name: "Mi funnel" }));
    render(<SaveTemplateControl landingId={7} bannerCount={2} />);

    await user.type(screen.getByLabelText(/Guardar esta configuración/), "Mi funnel");
    await user.click(screen.getByRole("button", { name: "Guardar plantilla" }));
    await user.click(await screen.findByRole("button", { name: "Reemplazar" }));

    expect(landingTemplatesApi.save).toHaveBeenLastCalledWith({
      landing_id: 7,
      name: "Mi funnel",
      overwrite: true,
    });
    expect(await screen.findByRole("status")).toHaveTextContent(
      "Plantilla «Mi funnel» actualizada.",
    );
  });

  it("cancelling the overwrite leaves the existing template alone", async () => {
    const user = userEvent.setup();
    vi.mocked(landingTemplatesApi.save).mockRejectedValueOnce(
      new ApiError(409, "Ya existe una plantilla llamada «Mi funnel»."),
    );
    render(<SaveTemplateControl landingId={7} bannerCount={2} />);

    await user.type(screen.getByLabelText(/Guardar esta configuración/), "Mi funnel");
    await user.click(screen.getByRole("button", { name: "Guardar plantilla" }));
    await user.click(await screen.findByRole("button", { name: "Cancelar" }));

    expect(screen.queryByRole("button", { name: "Reemplazar" })).not.toBeInTheDocument();
    expect(landingTemplatesApi.save).toHaveBeenCalledTimes(1);
  });

  it("surfaces a validation error from the server", async () => {
    const user = userEvent.setup();
    vi.mocked(landingTemplatesApi.save).mockRejectedValue(
      new ApiError(422, "El nombre no puede superar 80 caracteres."),
    );
    render(<SaveTemplateControl landingId={7} bannerCount={2} />);

    await user.type(screen.getByLabelText(/Guardar esta configuración/), "Nombre");
    await user.click(screen.getByRole("button", { name: "Guardar plantilla" }));

    expect(await screen.findByRole("alert")).toHaveTextContent(
      "El nombre no puede superar 80 caracteres.",
    );
  });
});

describe("LoadTemplateDialog", () => {
  function renderDialog(bannerCount: number, onLoaded = vi.fn()) {
    render(
      <LoadTemplateDialog landingId={7} bannerCount={bannerCount} onLoaded={onLoaded} />,
    );
    return onLoaded;
  }

  it("does not read the template list until the dialog is opened", () => {
    renderDialog(3);
    expect(landingTemplatesApi.list).not.toHaveBeenCalled();
  });

  it("lists each template with its banner and component counts", async () => {
    const user = userEvent.setup();
    vi.mocked(landingTemplatesApi.list).mockResolvedValue({
      templates: [template({ id: 1, name: "Suplementos", banner_count: 3, block_count: 2 })],
    });
    renderDialog(3);

    await user.click(screen.getByRole("button", { name: "Cargar plantilla" }));

    expect(await screen.findByText("Suplementos")).toBeInTheDocument();
    expect(screen.getByText(/3 banners · 2 componentes/)).toBeInTheDocument();
  });

  it("says which banner count this landing has", async () => {
    const user = userEvent.setup();
    vi.mocked(landingTemplatesApi.list).mockResolvedValue({ templates: [] });
    renderDialog(4);

    await user.click(screen.getByRole("button", { name: "Cargar plantilla" }));

    expect(await screen.findByText(/Esta landing tiene 4 banners/)).toBeInTheDocument();
  });

  it("shows an empty state when nothing has been saved yet", async () => {
    const user = userEvent.setup();
    vi.mocked(landingTemplatesApi.list).mockResolvedValue({ templates: [] });
    renderDialog(3);

    await user.click(screen.getByRole("button", { name: "Cargar plantilla" }));

    expect(
      await screen.findByText(/Todavía no hay plantillas guardadas/),
    ).toBeInTheDocument();
  });

  it("disables a template whose banner count does not match, and says why", async () => {
    const user = userEvent.setup();
    vi.mocked(landingTemplatesApi.list).mockResolvedValue({
      templates: [template({ id: 5, name: "Cinco banners", banner_count: 5 })],
    });
    renderDialog(3);

    await user.click(screen.getByRole("button", { name: "Cargar plantilla" }));

    const option = await screen.findByRole("radio");
    expect(option).toBeDisabled();
    expect(screen.getByText(/no aplica a 3 banners/)).toBeInTheDocument();
  });

  it("keeps the confirm button unavailable while no applicable template is chosen", async () => {
    const user = userEvent.setup();
    vi.mocked(landingTemplatesApi.list).mockResolvedValue({
      templates: [template({ id: 5, banner_count: 5 })],
    });
    renderDialog(3);

    await user.click(screen.getByRole("button", { name: "Cargar plantilla" }));
    await screen.findByRole("radio");

    // Two controls share the label; the dialog's confirm is the second.
    const confirm = screen.getAllByRole("button", { name: "Cargar plantilla" })[1];
    expect(confirm).toBeDisabled();
  });

  it("applies the selected template and hands the updated landing back", async () => {
    const user = userEvent.setup();
    const onLoaded = vi.fn();
    vi.mocked(landingTemplatesApi.list).mockResolvedValue({
      templates: [template({ id: 9, name: "Tres banners", banner_count: 3 })],
    });
    vi.mocked(landingsApi.loadTemplate).mockResolvedValue(LOADED_DETAIL);
    renderDialog(3, onLoaded);

    await user.click(screen.getByRole("button", { name: "Cargar plantilla" }));
    await user.click(await screen.findByRole("radio"));
    await user.click(screen.getAllByRole("button", { name: "Cargar plantilla" })[1]);

    expect(landingsApi.loadTemplate).toHaveBeenCalledWith(7, 9);
    await waitFor(() => expect(onLoaded).toHaveBeenCalledWith(LOADED_DETAIL));
  });

  it("surfaces the server's banner-count refusal verbatim", async () => {
    const user = userEvent.setup();
    const onLoaded = vi.fn();
    vi.mocked(landingTemplatesApi.list).mockResolvedValue({
      templates: [template({ id: 9, banner_count: 3 })],
    });
    vi.mocked(landingsApi.loadTemplate).mockRejectedValue(
      new ApiError(
        422,
        "No se pudo cargar: la landing debe tener 3 banners y actualmente tiene 2.",
        { banner_count: "No se pudo cargar: la landing debe tener 3 banners y actualmente tiene 2." },
      ),
    );
    renderDialog(3, onLoaded);

    await user.click(screen.getByRole("button", { name: "Cargar plantilla" }));
    await user.click(await screen.findByRole("radio"));
    await user.click(screen.getAllByRole("button", { name: "Cargar plantilla" })[1]);

    expect(await screen.findByRole("alert")).toHaveTextContent(
      "la landing debe tener 3 banners y actualmente tiene 2",
    );
    expect(onLoaded).not.toHaveBeenCalled();
  });

  it("warns that conversion components are replaced and images are not touched", async () => {
    const user = userEvent.setup();
    vi.mocked(landingTemplatesApi.list).mockResolvedValue({ templates: [] });
    renderDialog(3);

    await user.click(screen.getByRole("button", { name: "Cargar plantilla" }));

    expect(
      await screen.findByText(/Las imágenes, el slug y el estado de\s+publicación no cambian/),
    ).toBeInTheDocument();
  });
});
