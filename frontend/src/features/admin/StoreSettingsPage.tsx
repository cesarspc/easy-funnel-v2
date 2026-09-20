import { useEffect, useState, type ChangeEvent, type FormEvent } from "react";
import { ApiError, storeApi, type StoreSettings } from "../../api";
import { useStore } from "../store/StoreContext";
import "./StoreSettingsPage.css";

const TEXT_FIELDS: { key: keyof StoreSettings; label: string; multiline?: boolean }[] = [
  { key: "store_name", label: "Nombre de la tienda" },
  { key: "legal_name", label: "Razón social" },
  { key: "whatsapp_number", label: "WhatsApp (+57...)" },
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

export function StoreSettingsPage() {
  const [draft, setDraft] = useState<StoreSettings | null>(null);
  const [message, setMessage] = useState("");
  const { reload } = useStore();
  useEffect(() => { void storeApi.get().then(setDraft).catch(() => setMessage("No se pudo cargar la configuración.")); }, []);

  function change(event: ChangeEvent<HTMLInputElement | HTMLTextAreaElement>) {
    if (!draft) return;
    setDraft({ ...draft, [event.target.name]: event.target.value });
  }

  async function save(event: FormEvent) {
    event.preventDefault();
    if (!draft) return;
    setMessage("");
    try {
      const { logo_url: _logo, favicon_url: _favicon, homepage_image_url: _home, ...payload } = draft;
      setDraft(await storeApi.update(payload));
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
        {TEXT_FIELDS.map(field => <label key={field.key}>{field.label}{field.multiline ? <textarea name={field.key} value={String(draft[field.key] ?? "")} onChange={change} /> : <input name={field.key} value={String(draft[field.key] ?? "")} onChange={change} />}</label>)}
        <label>Color principal<input type="color" name="primary_color" value={draft.primary_color} onChange={change} /></label>
        <label>Mensajes de confianza (uno por línea)<textarea value={draft.trust_items.join("\n")} onChange={event => setDraft({ ...draft, trust_items: event.target.value.split("\n").map(v => v.trim()).filter(Boolean).slice(0, 3) })} /></label>
      </div>
      <fieldset><legend>Imágenes de marca</legend>{(["logo", "favicon", "homepage_image"] as const).map(kind => <label key={kind}>{kind.replace("_", " ")}<input type="file" accept="image/png,image/jpeg,image/webp" onChange={event => void upload(kind, event.target.files?.[0])} /></label>)}</fieldset>
      {message && <p role="status">{message}</p>}<button type="submit">Guardar configuración</button>
    </form>
  </section>;
}
