import { useStore } from "../features/store/StoreContext";
import "./MerchantLanding.css";

export function MerchantLanding() {
  const { store, loading, error, reload } = useStore();
  if (loading) return <main className="bodega-premium-landing" aria-busy="true" />;
  if (error || !store) {
    return <main className="bodega-premium-landing"><section className="bodega-premium-secondary"><h1>No se pudo cargar la tienda</h1><button className="bodega-premium-secondary-button" onClick={() => void reload()}>Reintentar</button></section></main>;
  }

  const contact = () => {
    if (!store.whatsapp_number) return;
    const number = store.whatsapp_number.replace(/\D/g, "");
    window.open(`https://wa.me/${number}?text=${encodeURIComponent(store.whatsapp_message)}`, "_blank", "noopener,noreferrer");
  };

  return (
    <div className="bodega-premium-landing" lang="es" style={{ "--bodega-primary": store.primary_color } as React.CSSProperties}>
      <header className="bodega-premium-header"><div className="bodega-premium-header-container">
        {store.logo_url ? <img src={store.logo_url} alt={store.store_name} className="store-logo-image" /> : <h1 className="bodega-premium-logo">{store.store_name}</h1>}
        {(store.whatsapp_number || store.support_email) && <nav className="bodega-premium-nav"><a href="#contacto" className="bodega-premium-nav-link">Contacto</a></nav>}
      </div></header>
      <section className="bodega-premium-hero" style={store.homepage_image_url ? { backgroundImage: `linear-gradient(rgba(26,28,30,.82),rgba(26,28,30,.82)),url(${store.homepage_image_url})` } : undefined}>
        <div className="bodega-premium-hero-container"><div className="bodega-premium-hero-content">
          <p className="bodega-premium-eyebrow">{store.home_eyebrow}</p>
          <h2 className="bodega-premium-headline">{store.home_headline}</h2>
          <p className="bodega-premium-subheadline">{store.home_description}</p>
          {store.whatsapp_number && <div className="bodega-premium-cta-container"><button className="bodega-premium-cta-button" onClick={contact}>{store.home_cta_label}</button></div>}
          {store.trust_items.length > 0 && <div className="bodega-premium-trust">{store.trust_items.map(item => <div className="bodega-premium-trust-item" key={item}><span className="bodega-premium-trust-text">✓ {item}</span></div>)}</div>}
        </div></div>
      </section>
      <section id="contacto" className="bodega-premium-secondary"><div className="bodega-premium-secondary-container">
        <h3 className="bodega-premium-secondary-headline">{store.secondary_headline}</h3>
        <p className="bodega-premium-secondary-copy">{store.secondary_description}</p>
        {store.whatsapp_number && <button className="bodega-premium-secondary-button" onClick={contact}>{store.home_cta_label}</button>}
        {!store.whatsapp_number && store.support_email && <a href={`mailto:${store.support_email}`}>{store.support_email}</a>}
      </div></section>
      <footer className="bodega-premium-footer"><div className="bodega-premium-footer-container">
        <p className="bodega-premium-footer-text">© {new Date().getFullYear()} {store.legal_name || store.store_name}. Todos los derechos reservados.</p>
        <p className="bodega-premium-footer-meta">{store.footer_text}</p>
      </div></footer>
    </div>
  );
}

export default MerchantLanding;
