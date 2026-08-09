/**
 * MerchantLanding.tsx
 *
 * Merchant-specific landing page for Bodega Premium.
 * Persuade mode: a minimal, elegant hero landing that earns trust through
 * restraint, premium typography, and the merchant's brand commitment.
 *
 * La Tope aesthetic: dark, minimal, strong hierarchy, ample whitespace,
 * forest-green brand accent (#30503b) as the sole chromatic voice.
 *
 * This component is intentionally merchant-specific and gitignored.
 */

import React from "react";
import "./MerchantLanding.css";

export const MerchantLanding: React.FC = () => {
  const handleWhatsAppCTA = () => {
    // WhatsApp CTA: wa.me/573221111222
    // Encode the message for WhatsApp
    const message = encodeURIComponent(
      "Hola, me gustaría conocer más sobre los productos de Bodega Premium."
    );
    window.open(
      `https://wa.me/573221111222?text=${message}`,
      "_blank",
      "noopener,noreferrer"
    );
  };

  return (
    <div className="bodega-premium-landing" lang="es">
      {/* Navigation bar */}
      <header className="bodega-premium-header">
        <div className="bodega-premium-header-container">
          <h1 className="bodega-premium-logo">Bodega Premium</h1>
          <nav className="bodega-premium-nav">
            <a href="#contacto" className="bodega-premium-nav-link">
              Contacto
            </a>
          </nav>
        </div>
      </header>

      {/* Hero section */}
      <section className="bodega-premium-hero">
        <div className="bodega-premium-hero-container">
          {/* Background pattern: subtle texture */}
          <div className="bodega-premium-hero-bg" aria-hidden="true"></div>

          {/* Hero content */}
          <div className="bodega-premium-hero-content">
            {/* Eyebrow / Preheader */}
            <p className="bodega-premium-eyebrow">Premium Selection</p>

            {/* Main headline */}
            <h2 className="bodega-premium-headline">
              Encuentra todo tipo de productos al mejor precio, con garantía
              directa por 30 días
            </h2>

            {/* Supporting copy */}
            <p className="bodega-premium-subheadline">
              Productos de calidad seleccionados especialmente para ti, con
              respaldo de 30 días. Compra con confianza, directamente desde
              Bodega Premium.
            </p>

            {/* CTA button */}
            <div className="bodega-premium-cta-container">
              <button
                className="bodega-premium-cta-button"
                onClick={handleWhatsAppCTA}
                aria-label="Contactar por WhatsApp"
              >
                <span className="bodega-premium-cta-icon">
                  <svg
                    width="20"
                    height="20"
                    viewBox="0 0 24 24"
                    fill="currentColor"
                    aria-hidden="true"
                  >
                    <path d="M17.472 14.382c-.297-.149-1.758-.867-2.03-.967-.273-.099-.471-.148-.67.15-.197.297-.767.966-.94 1.164-.173.199-.347.223-.644.075-.297-.15-1.255-.463-2.39-1.475-.883-.788-1.48-1.761-1.653-2.059-.173-.297-.018-.458.13-.606.134-.133.298-.347.446-.52.149-.174.198-.298.298-.497.099-.198.05-.371-.025-.52-.075-.149-.669-1.612-.916-2.207-.242-.579-.487-.5-.67-.51-.173-.008-.371-.01-.57-.01-.198 0-.52.074-.792.372-.272.297-1.04 1.016-1.04 2.479 0 1.462 1.065 2.875 1.213 3.074.149.198 2.096 3.2 5.076 4.487.709.306 1.262.489 1.694.625.712.227 1.36.195 1.871.118.571-.085 1.758-.719 2.006-1.413.248-.694.248-1.289.173-1.413-.074-.124-.272-.198-.57-.347m-5.421-7.403h-.004c-1.024 0-2.031.313-2.883.893L6.122 3.031 7.15 6.147c-.738.868-1.155 1.95-1.155 3.131 0 2.938 2.392 5.329 5.329 5.329 1.437 0 2.791-.565 3.783-1.588l3.06 1.025-1.12-3.127c.826-.934 1.326-2.153 1.326-3.476 0-2.938-2.392-5.329-5.329-5.329z" />
                  </svg>
                </span>
                <span className="bodega-premium-cta-text">
                  Escribir a WhatsApp
                </span>
              </button>
            </div>

            {/* Trust indicators */}
            <div className="bodega-premium-trust">
              <div className="bodega-premium-trust-item">
                <svg
                  className="bodega-premium-trust-icon"
                  width="24"
                  height="24"
                  viewBox="0 0 24 24"
                  fill="none"
                  stroke="currentColor"
                  strokeWidth="2"
                  aria-hidden="true"
                >
                  <path d="M12 22s8-4 8-10V5l-8-3-8 3v7c0 6 8 10 8 10z" />
                </svg>
                <span className="bodega-premium-trust-text">
                  Garantía 30 días
                </span>
              </div>
              <div className="bodega-premium-trust-item">
                <svg
                  className="bodega-premium-trust-icon"
                  width="24"
                  height="24"
                  viewBox="0 0 24 24"
                  fill="none"
                  stroke="currentColor"
                  strokeWidth="2"
                  aria-hidden="true"
                >
                  <polyline points="20 6 9 17 4 12" />
                </svg>
                <span className="bodega-premium-trust-text">
                  Productos verificados
                </span>
              </div>
              <div className="bodega-premium-trust-item">
                <svg
                  className="bodega-premium-trust-icon"
                  width="24"
                  height="24"
                  viewBox="0 0 24 24"
                  fill="none"
                  stroke="currentColor"
                  strokeWidth="2"
                  aria-hidden="true"
                >
                  <path d="M21 15a2 2 0 0 1-2 2H7l-4 4V5a2 2 0 0 1 2-2h14a2 2 0 0 1 2 2z" />
                </svg>
                <span className="bodega-premium-trust-text">
                  Soporte directo
                </span>
              </div>
            </div>
          </div>
        </div>
      </section>

      {/* Secondary call-to-action section */}
      <section className="bodega-premium-secondary">
        <div className="bodega-premium-secondary-container">
          <h3 className="bodega-premium-secondary-headline">
            ¿Preguntas sobre nuestros productos?
          </h3>
          <p className="bodega-premium-secondary-copy">
            Estamos aquí para ayudarte. Contáctanos por WhatsApp y te asesoraremos
            en tiempo real.
          </p>
          <button
            className="bodega-premium-secondary-button"
            onClick={handleWhatsAppCTA}
            aria-label="Contactar por WhatsApp"
          >
            Contactar ahora
          </button>
        </div>
      </section>

      {/* Footer */}
      <footer className="bodega-premium-footer">
        <div className="bodega-premium-footer-container">
          <p className="bodega-premium-footer-text">
            © {new Date().getFullYear()} Bodega Premium. Todos los derechos
            reservados.
          </p>
          <p className="bodega-premium-footer-meta">
            Compra segura con garantía de calidad
          </p>
        </div>
      </footer>
    </div>
  );
};

export default MerchantLanding;
