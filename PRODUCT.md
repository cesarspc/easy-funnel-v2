# Product

<!-- impeccable:product-schema 1 -->

## Platform

web

## Users

- **Administrator (primary, single role in v1):** the merchant operating Easy Funnel. Manages products across multiple, unrelated niches (not one fixed category) from one Admin Dashboard: creates products, builds each product's banner-based Landing, configures CTA placement and fraud rules, reviews and progresses Orders, and exports COD orders for courier handoff. Works at a desk, session-based, repeatedly throughout the day — this is an operational tool, not a marketing surface for them.
- **Buyer (public, unauthenticated):** a Colombian consumer who lands on a single product's page (`/p/{slug}`) from a paid ad or organic/social referral. Has no account, no prior relationship with the platform, and is almost always on mobile. Comes in cold, needs to trust the offer fast enough to submit real name/phone/address for cash-on-delivery, then leaves. Never sees the Admin Dashboard or any cross-product storefront.

## Product Purpose

Easy Funnel lets one merchant run COD (cash-on-delivery) sales for many unrelated low-ticket physical products, each behind its own banner-landing-page funnel, without Shopify/GemPages/a separate form tool. Success is a completed flow: banner landing → CTA → COD form submission → automatic fraud check → order appears in the Admin Dashboard ready for fulfillment. There is no fixed product category or visual theme for the storefront side — each Landing's imagery and offer come from whatever niche product the Administrator is currently selling.

## Positioning

Unlike Shopify + GemPages + a bolted-on form app, Easy Funnel is one small system purpose-built for exactly this flow and nothing else: no payment gateway, no theme marketplace, no page builder, no multi-currency/multi-language — just banner landings, a COD form, synchronous server-side fraud checks, and an order admin, self-hosted end to end (own image pipeline, own GeoIP, own fraud rules) instead of depending on external SaaS per step.

## Operating Context

- Public Landings are per-product, reached only via direct link (`/p/{slug}`) from ads or organic sharing — there is no public cross-product storefront/catalog page in v1.
- Each Landing is composed by the Administrator from up to 15 ordered banner images plus a configurable CTA placement pattern; the CTA opens the COD form inline or as a modal.
- The COD form captures full name, Colombian phone number, department, city, address, and quantity, then is evaluated by fraud checks (duplicate detection, manual blacklist, rate limiting, GeoIP rules) before the order lands as `pending` or `flagged_fraud`.
- The Administrator's daily loop lives in the Admin Dashboard: products, per-product Landing/banner editing, order list with status transitions, fraud configuration (blacklist, rate limits, GeoIP rules), analytics, and CSV export for couriers.
- Interface language is Spanish (`lang="es"`) for the public-facing side, matching the Colombian buyer audience.
- Primary device split: buyers are predominantly mobile (ad-driven traffic); the Administrator uses the dashboard primarily on desktop.

## Capabilities and Constraints

- No online payment gateway or checkout — COD only.
- No multi-currency, no multi-language, no drag-and-drop page builder, no theme marketplace, no app marketplace, no subscriptions, no multi-warehouse routing, no POS.
- No external CDN or paid image/geolocation SaaS — images self-hosted on Cloudflare R2 with a self-hosted image pipeline; GeoIP self-hosted (MaxMind GeoLite2).
- Single Administrator role in v1 (no multi-user roles/permissions yet).
- Public Landing visual content (banner images, product copy) is fully merchant-controlled per product and out of scope for a fixed design system — design work applies to the *chrome* around that content: CTA, COD form (inline and modal), field validation/error states, trust/loading/empty/not-found states, and the Admin Dashboard shell itself.
- Design work proceeded in two ordered phases: the Admin Dashboard shell shipped its visual system first; the public Landing chrome (CTA, COD form, modal, states) is designed separately and later, since it serves a Persuade audience (cold buyers) under different rules than the Operate-mode dashboard.
- Fraud outcomes are reviewable in-dashboard only; no v1 email/Telegram/WhatsApp alerts.

## Brand Commitments

- Platform name: **Easy Funnel**.
- The Admin Dashboard's visual system (palette, typography, components) is committed in the project's DESIGN.md — that identity is currently under revision toward a dark-mode, light-purple accent direction; treat the palette as in-flux until that revision lands, not as newly undefined.
- The public Landing chrome (CTA, COD form, modal, states) has no visual system yet — it is the next surface planned for design work, distinct from and designed after the Admin Dashboard's.
- No fixed niche/vertical identity: the platform must not visually commit to any one product category, since the Administrator sells across unrelated niches.

## Evidence on Hand

- No real product content, banner imagery, testimonials, or sample orders on hand yet. Do not fabricate merchant products, customer names, testimonials, or order data — use clearly-labeled placeholder/sample content where the UI needs example data (e.g., dashboard previews, empty states).

## Product Principles

1. **The Core Flow is the whole product.** Every surface earns its place only if it serves banner landing → CTA → COD form → fraud check → order in admin; nothing else gets visual investment ahead of that.
2. **Design the chrome, not the merchandise.** The platform's visual identity lives in the CTA, form, states, and dashboard shell — never in an assumed product category, since niches rotate.
3. **Cold-traffic trust, mobile-first.** Buyers arrive with zero relationship to the brand on a phone, from an ad; the CTA and COD form must read as trustworthy and frictionless in seconds, not just functional.
4. **Dashboard calm over dashboard spectacle.** The Administrator's tool is Operate-mode: low visual noise, high scanability, comfortable for repeated daily use — not a place for loud marketing-grade expression.
5. **Self-hosted discipline shows up as restraint.** No dependency on external design/CDN/SaaS polish crutches (icon services, font CDNs, animation libraries beyond what's already in the stack) — craft comes from precision, not add-ons.

## Accessibility & Inclusion

- Requirements.md mandates: visible focus and full keyboard operability for every interactive control (product/Landing/order/fraud/analytics/export), field-level errors associated with their control and exposed to assistive technology, and modal focus trapping with focus return to the activating control. Treat these as binding, not optional, for both the Admin Dashboard and public Landing chrome.
