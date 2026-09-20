import { render, screen, waitFor } from "@testing-library/react";
import { BrowserRouter } from "react-router-dom";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { App } from "./App";

describe("App shell", () => {
  beforeEach(() => {
    vi.stubGlobal(
      "fetch",
      vi.fn().mockImplementation((url: string) => Promise.resolve(
        url.includes("/public/store")
          ? {
              ok: true,
              status: 200,
              json: async () => ({
                store_name: "Tienda de Prueba", legal_name: "", primary_color: "#e85d04",
                logo_url: null, favicon_url: null, homepage_image_url: null,
                whatsapp_number: "", whatsapp_message: "", support_email: "",
                home_eyebrow: "Compra local", home_headline: "Una tienda configurable",
                home_description: "", home_cta_label: "Comprar", trust_items: [],
                secondary_headline: "Contacto", secondary_description: "", footer_text: "",
                seo_title: "Tienda de Prueba", seo_description: "",
                gtm_container_id: "", meta_pixel_id: "",
              }),
            }
          : { ok: false, status: 401, json: async () => ({ detail: "Not authenticated" }) },
      )),
    );
  });

  afterEach(() => {
    vi.unstubAllGlobals();
  });

  it("renders the home route", async () => {
    render(
      <BrowserRouter>
        <App />
      </BrowserRouter>,
    );

    expect(await screen.findByRole("heading", { name: "Tienda de Prueba" })).toBeInTheDocument();
    await waitFor(() => expect(fetch).toHaveBeenCalled());
  });
});
