import { useEffect, useState, type ChangeEvent, type FormEvent } from "react";
import { ApiError, storeApi, type AdminStoreSettings, type StoreSettingsUpdate } from "../../api";
import { useStore } from "../store/StoreContext";
import "./StoreSettingsPage.css";

type TextField = { key: keyof AdminStoreSettings; label: string; multiline?: boolean; placeholder?: string };

const TEXT_FIELDS: TextField[] = [
  { key: "store_name", label: "Nombre de la tienda" },
  { key: "legal_name", label: "Razón social" },
  { key: "whatsapp_number", label: "WhatsApp (formato internacional, +…)" },
  { key: "whatsapp_message", label: "Mensaje de WhatsApp", multiline: true },
  { key: "support_email", label: "Correo de soporte" },
  { key: "home_eyebrow", label: "Texto superior" },
  { key: "home_headline", label: "Título principal", multiline: true },
  { key: "home_description", label: "Descripción principal", multiline: true },
  { key: "home_cta_label", label: "Texto del botón" },
  { key: "secondary_headline", label: "Título de contacto" },
  { key: "secondary_description", label: "Descripción de contacto", multiline: true },
  { key: "footer_text", label: "Texto del pie" },
  { key: "seo_title", label: "Título SEO" },
  { key: "seo_description", label: "Descripción SEO", multiline: true },
  { key: "gtm_container_id", label: "Google Tag Manager (opcional)" },
  { key: "meta_pixel_id", label: "Meta Pixel (opcional)" },
];

const REGIONAL_FIELDS: TextField[] = [
  { key: "country_code", label: "País (ISO 3166, ej. CO)", placeholder: "CO" },
  { key: "locale", label: "Idioma y formato (BCP 47, ej. es-CO)", placeholder: "es-CO" },
  { key: "currency", label: "Moneda (ISO 4217, ej. COP)", placeholder: "COP" },
  { key: "time_zone", label: "Zona horaria (IANA)", placeholder: "America/Bogota" },
  { key: "phone_country_code", label: "Indicativo telefónico (sin +)", placeholder: "57" },
  { key: "phone_national_pattern", label: "Patrón del número nacional (regex)", placeholder: "3[0-9]{9}" },
];

const READ_ONLY_FIELDS = [
  "logo_url", "favicon_url", "homepage_image_url", "mastershop_api_key_configured",
] as const;

function textInput(field: TextField, draft: AdminStoreSettings, change: (event: ChangeEvent<HTMLInputElement | HTMLTextAreaElement>) => void) {
  const value = String(draft[field.key] ?? "");
  return <label key={field.key}>{field.label}{field.multiline
    ? <textarea name={field.key} value={value} onChange={change} />
    : <input name={field.key} value={value} placeholder={field.placeholder} onChange={change} />}</label>;
}

export function StoreSettingsPage() {
  const [draft, setDraft] = useState<AdminStoreSettings | null>(null);
  const [apiKey, setApiKey] = useState("");
  const [clearApiKey, setClearApiKey] = useState(false);
  const [message, setMessage] = useState("");
  const { reload } = useStore();
  useEffect(() => { void storeApi.get().then(setDraft).catch(() => setMessage("No se pudo cargar la configuración.")); }, []);

  function change(event: ChangeEvent<HTMLInputElement | HTMLTextAreaElement | HTMLSelectElement>) {
    if (!draft) return;
    const { name, value, type } = event.target;
    setDraft({ ...draft, [name]: type === "number" ? Number(value) : value });
  }

  async function save(event: FormEvent) {
    event.preventDefault();
    if (!draft) return;
    setMessage("");
    try {
      // Read-only fields (uploaded asset URLs, key presence) are not sent back.
      const payload: StoreSettingsUpdate & Partial<AdminStoreSettings> = { ...draft };
      for (const key of READ_ONLY_FIELDS) delete payload[key];
      if (clearApiKey) payload.mastershop_api_key = "";
      else if (apiKey.trim()) payload.mastershop_api_key = apiKey.trim();
      setDraft(await storeApi.update(payload));
      setApiKey("");
      setClearApiKey(false);
      await reload();
      setMessage("Configuración guardada.");
    } catch (error) {
      setMessage(error instanceof ApiError ? error.message : "No se pudo guardar.");
    }
  }

  async function upload(kind: "logo" | "favicon" | "homepage_image", file?: File) {
    if (!file) return;
    try {
      setDraft(await storeApi.upload(kind, file));
      await reload();
      setMessage("Imagen actualizada.");
    } catch (error) {
      setMessage(error instanceof ApiError ? error.message : "No se pudo subir la imagen.");
    }
  }

  if (!draft) return <section><h1>Configuración de la tienda</h1><p>{message || "Cargando…"}</p></section>;
  return <section className="store-settings"><header><h1>Configuración de la tienda</h1><p>Estos cambios se aplican a esta instalación y no se sobrescriben al reiniciar.</p></header>
    <form onSubmit={save}>
      <div className="store-settings__grid">
        {TEXT_FIELDS.map(field => textInput(field, draft, change))}
        <label>Color principal<input type="color" name="primary_color" value={draft.primary_color} onChange={change} /></label>
        <label>Mensajes de confianza (uno por línea)<textarea value={draft.trust_items.join("\n")} onChange={event => setDraft({ ...draft, trust_items: event.target.value.split("\n").map(v => v.trim()).filter(Boolean).slice(0, 3) })} /></label>
      </div>
      <fieldset><legend>Mercado y región</legend>
        <div className="store-settings__grid">{REGIONAL_FIELDS.map(field => textInput(field, draft, change))}</div>
      </fieldset>
      <fieldset><legend>Fulfillment</legend>
        <div className="store-settings__grid">
          <label>Proveedor
            <select name="fulfillment_provider" value={draft.fulfillment_provider} onChange={change}>
              <option value="none">Ninguno</option>
              <option value="mastershop">MasterShop</option>
            </select>
          </label>
          <label>URL de pedidos MasterShop<input name="mastershop_orders_url" type="url" value={draft.mastershop_orders_url} onChange={change} /></label>
          <label>Tiempo máximo de espera (segundos)<input name="mastershop_timeout_seconds" type="number" min={1} max={30} step="0.5" value={draft.mastershop_timeout_seconds} onChange={change} /></label>
          <label>API key MasterShop
            <input name="mastershop_api_key" type="password" autoComplete="off" value={apiKey} disabled={clearApiKey}
              placeholder={draft.mastershop_api_key_configured ? "Configurada — escribe para reemplazar" : "Sin configurar"}
              onChange={event => setApiKey(event.target.value)} />
          </label>
          {draft.mastershop_api_key_configured && <label><span><input type="checkbox" checked={clearApiKey} onChange={event => setClearApiKey(event.target.checked)} /> Eliminar la API key guardada</span></label>}
        </div>
      </fieldset>
      <fieldset><legend>Imágenes de marca</legend>{(["logo", "favicon", "homepage_image"] as const).map(kind => <label key={kind}>{kind.replace("_", " ")}<input type="file" accept="image/png,image/jpeg,image/webp" onChange={event => void upload(kind, event.target.files?.[0])} /></label>)}</fieldset>
      {message && <p role="status">{message}</p>}<button type="submit">Guardar configuración</button>
    </form>
  </section>;
}
