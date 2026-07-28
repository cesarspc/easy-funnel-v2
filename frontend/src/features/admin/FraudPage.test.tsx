import { render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { MemoryRouter } from "react-router-dom";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { FraudPage } from "./FraudPage";
import { ApiError, fraudApi } from "../../api";
import type { BlacklistEntry, FraudConfig, GeoIpRule } from "../../api";

vi.mock("../../api", async () => {
  const actual = await vi.importActual<typeof import("../../api")>("../../api");
  return {
    ...actual,
    fraudApi: {
      getConfig: vi.fn(),
      updateConfig: vi.fn(),
      listBlacklist: vi.fn(),
      addBlacklistEntry: vi.fn(),
      removeBlacklistEntry: vi.fn(),
      listGeoIpRules: vi.fn(),
      createGeoIpRule: vi.fn(),
      updateGeoIpRule: vi.fn(),
      deleteGeoIpRule: vi.fn(),
    },
  };
});

const CONFIG: FraudConfig = {
  id: 1,
  duplicate_window_hours: 24,
  duplicate_match_fields: ["phone", "ip"],
  rate_limit_max: 5,
  rate_limit_window_minutes: 10,
};

const BLACKLIST_ENTRY: BlacklistEntry = {
  id: 9,
  entry_type: "phone",
  value_normalized: "3001234567",
  reason: "Pedidos falsos repetidos",
  created_at: "2026-01-10T10:00:00Z",
};

const GEOIP_RULE: GeoIpRule = {
  id: 4,
  location_code: "VE",
  action: "flag",
  enabled: true,
  created_at: "2026-01-05T10:00:00Z",
  updated_at: "2026-01-05T10:00:00Z",
};

function renderPage() {
  return render(
    <MemoryRouter>
      <FraudPage />
    </MemoryRouter>,
  );
}

describe("FraudPage", () => {
  beforeEach(() => {
    vi.mocked(fraudApi.getConfig).mockResolvedValue(CONFIG);
    vi.mocked(fraudApi.listBlacklist).mockResolvedValue({ entries: [BLACKLIST_ENTRY] });
    vi.mocked(fraudApi.listGeoIpRules).mockResolvedValue({ rules: [GEOIP_RULE] });
  });

  afterEach(() => {
    vi.clearAllMocks();
  });

  it("renders the fraud configuration form with the stored values", async () => {
    renderPage();

    expect(await screen.findByLabelText("Ventana de duplicados (horas)")).toHaveValue(24);
    expect(screen.getByLabelText("Máximo de intentos")).toHaveValue(5);
    expect(screen.getByLabelText("Ventana de intentos (minutos)")).toHaveValue(10);
    expect(screen.getByRole("checkbox", { name: "Teléfono" })).toBeChecked();
    expect(screen.getByRole("checkbox", { name: "Dirección IP" })).toBeChecked();
  });

  it("renders the blacklist table with the normalized value from the backend", async () => {
    renderPage();

    expect(await screen.findByText("3001234567")).toBeInTheDocument();
    expect(screen.getByText("Pedidos falsos repetidos")).toBeInTheDocument();
  });

  it("renders the GeoIP rules table", async () => {
    renderPage();

    expect(await screen.findByText("VE")).toBeInTheDocument();
    expect(screen.getByText("Marcar")).toBeInTheDocument();
  });

  it("links to the orders list for reviewing flagged orders", async () => {
    renderPage();
    await screen.findByText("VE");

    const link = screen.getByRole("link", { name: /Ver pedidos marcados/i });
    expect(link).toHaveAttribute("href", "/admin/orders");
  });

  it("saves the fraud configuration and shows a confirmation", async () => {
    const user = userEvent.setup();
    vi.mocked(fraudApi.updateConfig).mockResolvedValue({ ...CONFIG, rate_limit_max: 8 });
    renderPage();
    await screen.findByLabelText("Ventana de duplicados (horas)");

    await user.clear(screen.getByLabelText("Máximo de intentos"));
    await user.type(screen.getByLabelText("Máximo de intentos"), "8");
    await user.click(screen.getByRole("button", { name: "Guardar configuración" }));

    await waitFor(() =>
      expect(fraudApi.updateConfig).toHaveBeenCalledWith({
        duplicate_window_hours: 24,
        duplicate_match_fields: ["phone", "ip"],
        rate_limit_max: 8,
        rate_limit_window_minutes: 10,
      }),
    );
    expect(await screen.findByText("Configuración guardada.")).toBeInTheDocument();
  });

  it("binds a rejected rate_limit_max value to its control", async () => {
    const user = userEvent.setup();
    vi.mocked(fraudApi.updateConfig).mockRejectedValue(
      new ApiError(422, "Must be a positive whole number.", {
        rate_limit_max: "Must be a positive whole number.",
      }),
    );
    renderPage();
    await screen.findByLabelText("Ventana de duplicados (horas)");

    await user.click(screen.getByRole("button", { name: "Guardar configuración" }));

    const rateLimitInput = await screen.findByLabelText("Máximo de intentos");
    await waitFor(() => expect(rateLimitInput).toHaveAttribute("aria-invalid", "true"));
    expect(rateLimitInput).toHaveAccessibleDescription("Must be a positive whole number.");
  });

  it("adds a blacklist entry and displays the value the backend returns", async () => {
    const user = userEvent.setup();
    vi.mocked(fraudApi.addBlacklistEntry).mockResolvedValue({
      id: 10,
      entry_type: "ip",
      value_normalized: "203.0.113.5",
      reason: "IP con muchos pedidos falsos",
      created_at: "2026-02-01T10:00:00Z",
    });
    renderPage();
    await screen.findByText("3001234567");

    await user.selectOptions(screen.getByLabelText("Tipo"), "ip");
    await user.type(screen.getByLabelText("Valor"), "203.0.113.5");
    await user.type(screen.getByLabelText("Motivo (1-500 caracteres)"), "IP con muchos pedidos falsos");
    await user.click(screen.getByRole("button", { name: "Agregar a la lista negra" }));

    await waitFor(() =>
      expect(fraudApi.addBlacklistEntry).toHaveBeenCalledWith({
        entry_type: "ip",
        value_normalized: "203.0.113.5",
        reason: "IP con muchos pedidos falsos",
      }),
    );
    expect(await screen.findByText("203.0.113.5")).toBeInTheDocument();
  });

  it("binds a duplicate blacklist entry rejection without touching the existing row", async () => {
    const user = userEvent.setup();
    vi.mocked(fraudApi.addBlacklistEntry).mockRejectedValue(
      new ApiError(409, "Entry already exists"),
    );
    renderPage();
    await screen.findByText("3001234567");

    await user.type(screen.getByLabelText("Valor"), "3001234567");
    await user.type(screen.getByLabelText("Motivo (1-500 caracteres)"), "Duplicado");
    await user.click(screen.getByRole("button", { name: "Agregar a la lista negra" }));

    expect(await screen.findByText("Entry already exists")).toBeInTheDocument();
    // The existing entry is still there, unaffected.
    expect(screen.getByText("3001234567")).toBeInTheDocument();
  });

  it("requires confirmation before removing a blacklist entry, and says history is preserved", async () => {
    const user = userEvent.setup();
    vi.mocked(fraudApi.removeBlacklistEntry).mockResolvedValue({ message: "Entry removed" });
    renderPage();
    await screen.findByText("3001234567");

    const deleteButtons = screen.getAllByRole("button", { name: "Eliminar" });
    await user.click(deleteButtons[0]);
    expect(fraudApi.removeBlacklistEntry).not.toHaveBeenCalled();

    await user.click(screen.getByRole("button", { name: "Confirmar" }));

    await waitFor(() => expect(fraudApi.removeBlacklistEntry).toHaveBeenCalledWith(9));
    expect(
      await screen.findByText(/se conservan/i),
    ).toBeInTheDocument();
  });

  it("creates a GeoIP rule with the selected action", async () => {
    const user = userEvent.setup();
    vi.mocked(fraudApi.createGeoIpRule).mockResolvedValue({
      id: 5,
      location_code: "RU",
      action: "block",
      enabled: true,
      created_at: "2026-02-01T10:00:00Z",
      updated_at: "2026-02-01T10:00:00Z",
    });
    renderPage();
    await screen.findByText("VE");

    await user.type(screen.getByLabelText(/Código de ubicación/), "ru");
    await user.selectOptions(screen.getByLabelText("Acción"), "block");
    await user.click(screen.getByRole("button", { name: "Crear regla" }));

    await waitFor(() =>
      expect(fraudApi.createGeoIpRule).toHaveBeenCalledWith({
        location_code: "ru",
        action: "block",
      }),
    );
    expect(await screen.findByText("RU")).toBeInTheDocument();
  });

  it("binds a duplicate location_code rejection to the GeoIP form", async () => {
    const user = userEvent.setup();
    vi.mocked(fraudApi.createGeoIpRule).mockRejectedValue(new ApiError(409, "Rule already exists"));
    renderPage();
    await screen.findByText("VE");

    await user.type(screen.getByLabelText(/Código de ubicación/), "VE");
    await user.click(screen.getByRole("button", { name: "Crear regla" }));

    expect(await screen.findByText("Rule already exists")).toBeInTheDocument();
  });

  it("toggles a GeoIP rule's enabled state", async () => {
    const user = userEvent.setup();
    vi.mocked(fraudApi.updateGeoIpRule).mockResolvedValue({ ...GEOIP_RULE, enabled: false });
    renderPage();
    await screen.findByText("VE");

    await user.click(screen.getByRole("button", { name: "Habilitada" }));

    await waitFor(() =>
      expect(fraudApi.updateGeoIpRule).toHaveBeenCalledWith(4, { enabled: false }),
    );
  });

  it("requires confirmation before deleting a GeoIP rule, and says history is preserved", async () => {
    const user = userEvent.setup();
    vi.mocked(fraudApi.deleteGeoIpRule).mockResolvedValue({ message: "Rule deleted" });
    renderPage();
    await screen.findByText("VE");

    const deleteButtons = screen.getAllByRole("button", { name: "Eliminar" });
    await user.click(deleteButtons[deleteButtons.length - 1]);
    expect(fraudApi.deleteGeoIpRule).not.toHaveBeenCalled();

    await user.click(screen.getByRole("button", { name: "Confirmar" }));

    await waitFor(() => expect(fraudApi.deleteGeoIpRule).toHaveBeenCalledWith(4));
    expect(await screen.findByText(/se conservan/i)).toBeInTheDocument();
  });
});
