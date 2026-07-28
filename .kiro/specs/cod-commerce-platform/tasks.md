# Implementation Plan

This plan turns the COD Commerce Platform design into an incremental, test-driven build ordered so every step compiles, is exercised by tests, and wires into the running system with no orphaned code. The platform is cloud-native: a Cloudflare Pages SPA, a single FastAPI container on Koyeb, Neon PostgreSQL via Prisma, Upstash Redis for rate-limit/fraud counters, and Cloudflare R2 for images. Tasks progress from scaffolding and schema through domains, services, API routers, the SPA, admin features, operational reads, deployment, and end-to-end validation. Coding tasks only; each references the acceptance criteria and design sections it satisfies.

- [x] 1. Establish repository scaffolding and tooling
  - Create the backend Python package layout (`backend/app/{api,core,db,domains,schemas,services,redis}`, `backend/tests`) with `main.py` app factory placeholder and a health route wired in, plus a `backend/Dockerfile` skeleton for the single Koyeb container.
  - Create the frontend Vite + React + React Router + TypeScript (strict) project under `frontend/src/{api,components,features,routes,styles,test}` with a minimal booting SPA shell and a Cloudflare Pages build/SPA-fallback config.
  - Add the `prisma/schema.prisma` skeleton with the Neon datasource and generator for Prisma Client Python.
  - Pin exact backend deps (FastAPI, uvicorn, prisma (Prisma Client Python), pydantic, Argon2, Pillow, PyJWT/python-jose, an S3/R2 client such as boto3, an Upstash Redis client, Hypothesis, pytest, ruff, mypy) and frontend deps (React, React Router, Vitest/RTL, fast-check, testing-library a11y helpers) to reviewed versions.
  - Add lint/format/type/test config so the canonical validation commands run: `ruff check`, `ruff format --check`, `mypy backend/app`, `pytest`, `pnpm --prefix frontend run lint/typecheck/test/build`, and `prisma validate`.
  - Add a smoke test that imports the FastAPI app factory and asserts the health route responds, and a frontend test that renders the SPA shell.
  - _Requirements: 1.9, 1.10, 1.11, 1.12, 1.13_
  - _Design: Overview; Technology Stack and Constraints; Project Structure_

- [x] 2. Create the Prisma client, Neon connection, and migration harness
  - [x] 2.1 Wire the Prisma client and migration integration
    - Implement `db/` Prisma client wrapper (single client instance, no dedicated pooler), reading the Neon connection string from env, with UTC handling.
    - Set up `prisma migrate` as the versioned, ordered, forward-safe migration mechanism and a one-off migrate/deploy entrypoint (never ad-hoc auto-create in deployed environments).
    - Add an integration test that applies all migrations to a throwaway Postgres database and asserts a clean migrate deploy, plus a `prisma validate` check.
    - _Requirements: 1.10, 9.19_
    - _Design: Technology Stack and Constraints; Component and Service Design → db_
  - [x] 2.2 Wire the Upstash Redis client module
    - Implement `redis/` Upstash client and helpers with atomic sliding-window increment + expire, reading the Redis URL/token from env, plus a documented non-triggering fallback when Redis is unavailable.
    - Unit tests (Redis test double / Upstash-compatible mock): atomic increment returns count including the current call, TTL/window expiry drops old attempts, unavailable-Redis fallback path returns a non-triggering result.
    - _Requirements: 9.3, 6.12_
    - _Design: Component and Service Design → redis; Fraud Evaluation Design → rate limiting_

- [x] 3. Author the Prisma schema models and migrations
  - [x] 3.1 Products, landings, banners, image assets/variants
    - Prisma models + migration for `products` (name/sku/price/description/status/retired_at, `@@unique(sku)`, price/name/status checks), `landings` (`@@unique(product_id)`, `@@unique(slug)`, cta_mode/interval/positions checks, form_presentation), `banners` (`@@unique([landing_id, order_index])`, alt_text check, FK to image_assets), `image_assets` (opaque_key unique, source/variant R2 object keys, status check), `image_variants` (`@@unique([image_asset_id, width, format])`, object_key, version).
    - Add indexes `idx_products_sku`, `idx_landings_slug`, `idx_banners_landing_order`, `idx_image_assets_opaque`, `idx_variants_asset`.
    - Migration tests: constraints reject duplicate SKU/slug, second landing per product, duplicate order index; price stored as Decimal/numeric.
    - _Requirements: 2.5, 3.1, 3.2, 3.5, 3.6, 4.11_
    - _Design: Data Model → products/landings/banners/image_assets/image_variants_
  - [x] 3.2 Orders, fraud flags, and fraud configuration
    - Prisma models + migration for `orders` (all customer/attribution/metadata fields, status check, restrict FKs, denormalized landing_slug), `fraud_flags` (flag_type check, jsonb detail, restrict FK), `fraud_config` singleton (`CHECK id=1`, window/threshold checks, match-fields array), `blacklist_entries` (`@@unique([entry_type, value_normalized])`), `geoip_rules` (`@@unique(location_code)`, action check). Note: rolling-window rate-limit counting lives in Upstash Redis, not a Postgres table.
    - Add indexes `idx_orders_status_created`, `idx_orders_product_landing_created`, `idx_orders_created`, `idx_orders_dupe`, `idx_fraud_flags_order`, `idx_blacklist_lookup`, `idx_geoip_rules_enabled`.
    - Migration tests: restrict FKs prevent erasing referenced products/landings; status/action/window checks enforced; singleton config guard.
    - _Requirements: 5.9, 5.18, 6.3, 6.11, 2.15_
    - _Design: Data Model → orders/fraud_flags/fraud_config/blacklist_entries/geoip_rules; Rate-limit counters (Redis)_
  - [x] 3.3 Analytics, admin users, and audit models
    - Prisma models + migration for `landing_views` (no contact fields), `cta_clicks`, `admin_users` (username unique, Argon2id hash column, role), `audit_log` (actor/action/target/result/timestamp).
    - Add indexes `idx_landing_views_landing_created`, `idx_cta_clicks_landing_created`, `idx_audit_created`.
    - Add repository classes owning all Prisma queries for every model; Prisma models never cross the API boundary.
    - Migration test: full clean migrate deploy plus a migrate from the prior schema revision using synthetic data.
    - _Requirements: 8.14, 7.5, 7.6, 10.3, 10.10_
    - _Design: Data Model → landing_views/cta_clicks/admin_users/audit_log; Component and Service Design → db_

- [x] 4. Implement core settings, logging, and request context
  - Implement `core/settings` env loader (Neon, Upstash Redis, R2 credentials + bucket + public host, JWT, GeoIP, deployment values) and structured logging with redaction filters for passwords, JWTs, Neon/Redis/R2 credentials, and full addresses.
  - Implement the request-context dependency that extracts client IP from the trusted Cloudflare/Koyeb forwarded header and captures/truncates the user agent to 512 chars.
  - Add unit tests for env parsing, log redaction of sensitive fields, and IP/user-agent capture + truncation boundaries.
  - _Requirements: 5.10, 5.11, 10.5, 10.7, 9.3_
  - _Design: Component and Service Design → core; Security and Privacy Design → PII redaction_

- [x] 5. Implement authentication core (JWT + password hashing + login rate limit)
  - [x] 5.1 JWT issuance/validation and Argon2id hashing
    - Implement Argon2id hashing with unique salt, JWT issuance (iat/exp/iss/aud/subject) signed with an approved algorithm from env, and validation rejecting expired/tampered/unsupported-algorithm tokens.
    - Implement `require_admin` FastAPI dependency and session hydration helper.
    - Unit tests: hash never plaintext, valid token authorizes, expired/altered/`alg:none` rejected, generic errors leak nothing.
    - _Requirements: 7.1, 7.3, 7.4, 7.6, 7.8_
    - _Design: Security and Privacy Design → JWT issuance/validation, Password hashing_
  - [x] 5.2 Login rate limiting (Upstash Redis) and auth audit
    - Implement rolling-window login attempt tracking on Upstash Redis keyed on identifier/IP that rejects with 429 once threshold exceeded and recovers as the window clears.
    - Record `login.success`/`login.failure` audit entries (result + timestamp, never password/JWT).
    - Unit tests (Redis mock): threshold boundary, window recovery, generic invalid-credential error, audit rows written without secrets.
    - _Requirements: 7.2, 7.9, 7.10, 10.11_
    - _Design: Security and Privacy Design → Login rate limiting, Audit logging_

- [x] 6. Implement the products domain and lifecycle service
  - Implement `domains/products` validation (name 1–160, description 0–5000, price 0.01–999999999.99 two-decimal, non-empty unique SKU, status allowlist) and lifecycle rules (paused/active/retired, reject activate/edit of retired, one-landing invariant coordination, soft-deletion preserving references).
  - Implement `ProductLifecycleService` composing product creation + atomic single draft landing creation, activate/pause/retire transitions inside Prisma transactions, with audit hooks.
  - Unit tests: creation validation and field-specific errors, default `paused`, one-landing invariant, duplicate SKU 409, soft-deletion preserves data, retired rejects activation/edit, list excludes retired by default.
  - _Requirements: 2.1, 2.2, 2.3, 2.4, 2.5, 2.6, 2.7, 2.8, 2.9, 2.10, 2.11, 2.12, 2.13, 2.14, 2.15, 2.16, 2.17, 2.18, 2.19, 2.20, 2.21, 2.22_
  - _Design: Component and Service Design → domains/products, ProductLifecycleService_

- [x] 7. Implement the landings/banners domain and publication service
  - [x] 7.1 Slug, banner ordering, and CTA placement rules
    - Implement `domains/landings` slug validation/uniqueness (live + retired), banner ordering (unique contiguous indexes, gap-closing on removal, ≤15 bound), and CTA placement computation for `after_every`, `every_n` (interval 1–15), `fixed_positions` (non-empty unique in-range set).
    - Unit tests + property tests: reorder yields unique indexes and a permutation of the same banners; any valid CTA config + 1–15 banners yields positions matching the mode and within sequence.
    - _Requirements: 3.1, 3.2, 3.3, 3.4, 3.5, 3.6, 3.7, 3.8, 3.9, 3.10, 3.11, 3.12, 3.13, 3.14, 3.15, 3.16_
    - _Design: Component and Service Design → domains/landings; Testing Strategy → property-based tests (banner reorder, CTA positions)_
  - [x] 7.2 Publication validation and public not-found policy
    - Implement `LandingPublicationService` publish/unpublish (require 1–15 valid banners + valid CTA config) and form-presentation persistence, with audit hooks.
    - Implement the public availability resolver returning an identical generic not-found for unknown/draft/paused/retired slugs (no information disclosure).
    - Unit tests: publish gating, publish rejection on zero banners/invalid CTA, identical not-found across all denied states, published+active renders in stored order.
    - _Requirements: 3.19, 3.20, 3.21, 3.22, 3.23, 3.24, 2.11, 2.12, 2.14_
    - _Design: Component and Service Design → domains/landings, LandingPublicationService; API Design → Public Landing_

- [x] 8. Implement the image pipeline domain and banner upload service
  - [x] 8.1 Validation, EXIF stripping, variant generation, R2 upload, opaque keys
    - Implement `domains/images` Pillow pipeline: decode-to-confirm type allowlist (JPEG/PNG/WebP), enforce width 480–8000, height 1–8000, ≤40,000,000 px, ≤10 MiB; EXIF stripping; WebP+JPEG variants at {480,768,1200,1600} skipping widths > source, aspect-preserving; opaque R2 key generation with independent safe fallback and reject-if-both-fail; upload objects to R2.
    - Unit + property tests (R2-compatible/S3 mock): field-specific 422 on each limit violation; EXIF removed; generated widths from configured set, ≤ source, aspect preserved within tolerance; opaque key ignores client filename; fallback key unaffected by client input/primary failure.
    - _Requirements: 4.1, 4.2, 4.3, 4.4, 4.5, 4.6, 4.7, 4.8, 4.9, 4.10, 10.8, 10.13, 10.19, 10.20_
    - _Design: Image Pipeline Design; Testing Strategy → property-based tests (source dimensions)_
  - [x] 8.2 Atomic completion and upload-outage behavior
    - Implement atomic finalize (upload all required R2 objects → mark `image_assets` complete → associate banner only when every upload succeeds), partial-object cleanup on failure, and versioned immutable R2 URL derivation.
    - Implement `BannerUploadService` creating a banner at the next unique index when <15 banners, rejecting the 16th, and returning a non-sensitive 503 during upload-pipeline outage with no partial banner while existing R2 variants keep serving.
    - Integration tests (R2 mock): successful completion associates asset+variants+banner; forced mid-pipeline failure leaves no usable banner and no partial R2 objects; outage rejects new upload while existing variants remain served.
    - _Requirements: 4.11, 4.12, 4.20, 4.21, 4.22, 3.6_
    - _Design: Image Pipeline Design → atomic completion, outage behavior; API Design → banners endpoints_

- [x] 9. Implement the orders domain (validation, normalization, status graph)
  - Implement `domains/orders` field validation/normalization (name 2–120, department/city 2–100, address 5–250, quantity 1–99) and Colombian phone normalization producing canonical `+57`+10-digit form and a stable matching key.
  - Implement the centralized legal status-transition graph (`pending→confirmed→shipped→delivered`; `pending|confirmed|shipped→cancelled`; `flagged_fraud→pending|cancelled`) rejecting illegal transitions without mutation.
  - Unit + property tests: all field boundaries; phone normalization idempotent and equivalent representations share one key; only documented transitions change status.
  - _Requirements: 5.1, 5.2, 5.3, 5.4, 5.5, 5.6, 5.7, 5.8, 5.19, 5.20, 5.21, 5.22_
  - _Design: Component and Service Design → domains/orders; Testing Strategy → property-based tests (phone normalization, status transitions)_

- [x] 10. Implement the fraud domain and configuration/blacklist/geoip management
  - [x] 10.1 Fraud config, blacklist, and GeoIP rule management
    - Implement config resolution with defaults (24h window, {phone,ip} fields, 5 attempts/10 min), config update validation (reject non-positive window/threshold, empty match fields, unsupported action without replacing active config), blacklist add/remove (validity requirements, duplicate-same-type 409, preserve historical flags), and GeoIP rule CRUD.
    - Unit tests: default resolution, config rejection cases, blacklist normalization/add/remove, GeoIP unsupported-action rejection, duplicate-entry rejection.
    - _Requirements: 6.6, 6.7, 6.8, 6.20, 6.21, 6.24_
    - _Design: Fraud Evaluation Design; Data Model → fraud_config/blacklist_entries/geoip_rules_
  - [x] 10.2 The four fraud checks and multi-flag aggregation
    - Implement `domains/fraud` duplicate detection (Postgres, inclusive rolling window, all configured match fields equal), blacklist matching (Postgres, normalized phone/IP), independent phone/IP rate limits (Upstash Redis counts include current attempt, flag when count exceeds max), and GeoIP evaluation (flag+block both flagged, unresolved and unavailable continue without matching), each producing one machine-readable flag.
    - Unit + property tests: duplicate boundary (only in-window all-fields-equal triggers); Redis attempt-stream counts exclude out-of-window and trigger at threshold, including concurrent atomic increments; GeoIP match/unknown/unavailable/flag/block; multi-flag aggregation preserves every triggered rule identity.
    - _Requirements: 6.1, 6.2, 6.3, 6.4, 6.5, 6.9, 6.10, 6.11, 6.12, 6.13, 6.14, 6.15, 6.16, 6.17, 6.18, 6.19, 6.23_
    - _Design: Fraud Evaluation Design; Testing Strategy → property-based tests (duplicate window, rate-limit stream, fraud aggregation)_

- [x] 11. Implement the GeoIP resolver over the bundled database
  - Implement a local GeoLite2 resolver returning country/region, `unresolved`, or `unavailable` without any external geolocation API, reading the active (bundled/last-known-good) database path from settings.
  - Unit tests: resolved location, unresolved address, unavailable database each return the correct distinct outcome consumed by the fraud domain.
  - _Requirements: 6.16, 6.17, 6.18, 1.17_
  - _Design: Fraud Evaluation Design → GeoIP evaluation; Architecture (local GeoLite2 in container)_

- [x] 12. Implement the order-submission orchestration service
  - Implement `OrderSubmissionService.submit`: validate/normalize all fields → resolve active product + published landing and capture attribution (product id, landing id+slug snapshot, IP, truncated UA) → atomically increment Upstash Redis phone/IP rate-limit counters (count includes current attempt) → open one Prisma transaction, run duplicate/blacklist/GeoIP checks synchronously → persist exactly one `pending` order (no flags) or one `flagged_fraud` order plus one `fraud_flags` row per rule → commit; roll back with a non-sensitive failure on persistence error leaving no partial order.
  - Integration + property tests: clean submission → single `pending`; any triggered rule set → single `flagged_fraud` with all flags; `pending` iff no rule triggered; concurrent same-key submissions classify correctly (Redis atomic counts + Postgres transaction); forced persistence failure leaves no partial order; retries never create unclassified orders.
  - _Requirements: 5.9, 5.12, 5.13, 5.14, 5.15, 5.16, 5.17, 5.18, 6.1, 6.12, 6.22, 6.23_
  - _Design: Component and Service Design → order-submission orchestration; Fraud Evaluation Design → concurrency and durability; Testing Strategy → property-based tests (fraud classification)_

- [x] 13. Implement analytics domain and query service
  - Implement `domains/analytics` view/click recording (no contact fields) and per-day / per-landing aggregation for orders-per-day, per-landing views/clicks/orders/conversion rate, and flagged-order counts/flagged-fraud rate, with zero-guarded denominators.
  - Implement `AnalyticsQueryService` composing date-range Prisma queries used by the API.
  - Unit tests: view/click recording, per-day and per-landing aggregation over inclusive ranges, conversion rate 0 when views=0, flagged-fraud rate 0 when orders=0.
  - _Requirements: 8.11, 8.12, 8.13, 8.14, 8.15, 8.21_
  - _Design: Component and Service Design → domains/analytics, AnalyticsQueryService; Data Model → landing_views/cta_clicks_

- [x] 14. Implement the CSV export service with formula-injection neutralization
  - Implement `CsvExportService` generating a header row + spreadsheet-import encoding for orders matching active filters, neutralizing any value beginning with a formula control character (`=`, `+`, `-`, `@`, tab, CR) while keeping it merchant-readable, and failing atomically with no partial file on encoding failure.
  - Unit + property tests: exported customer strings round-trip as data and cannot become executable formulas; atomic failure produces no partial CSV; export includes only filtered records.
  - _Requirements: 8.16, 8.17, 8.18, 8.22, 10.12_
  - _Design: Security and Privacy Design → CSV formula-injection neutralization; Testing Strategy → property-based tests (CSV round-trip)_

- [x] 15. Wire the auth and operational-read API routers
  - Implement thin `/api/auth` routers (`login`, `logout`, `session`) mapping to the auth core with generic error responses, Upstash Redis login rate limiting (429), and auditing; choose the JWT transport (prefer secure HttpOnly SameSite cookie) with CSRF defense on state-changing requests.
  - Implement the scoped, authenticated, read-only `/api/admin/ops` router (`health` incl. Neon/Upstash/R2 reachability, `version`, `jobs`) returning only Non_Sensitive_Operational_Information and rejecting mutations or excluded content (403/404).
  - Router tests: login success/failure, expired/invalid session rejection, ops endpoints require session and omit sensitive categories, mutation attempts rejected.
  - _Requirements: 7.1, 7.2, 7.3, 7.4, 7.8, 7.9, 7.11, 7.12, 7.13, 7.14, 7.15, 10.21_
  - _Design: API Design → Auth, Operational Read Interface; Security and Privacy Design_

- [x] 16. Wire the product and landing/banner admin API routers
  - Implement thin `/api/admin/products` routers (create with atomic draft landing, list with `include_retired`, get, patch, activate, pause, soft-delete) mapping to `ProductLifecycleService`, with 422/409 mapping and audit.
  - Implement thin `/api/admin/landings` routers (get, patch config, banner upload multipart → Pillow → R2, banner patch/reorder, banner delete, publish, unpublish) mapping to landing/banner services, with 422/409/503 mapping and audit.
  - Router integration tests: product CRUD + lifecycle status codes; landing config validation; banner upload/reorder/delete; publish gating; audit rows on availability/publication/ordering changes.
  - _Requirements: 2.1, 2.8, 2.9, 2.13, 2.17, 2.19, 2.20, 3.1, 3.5, 3.6, 3.7, 3.8, 3.19, 3.20, 10.9, 10.10_
  - _Design: API Design → Products, Landings & Banners; Component and Service Design_

- [x] 17. Wire the public landing and checkout API routers
  - Implement thin `/api/public/landings/{slug}` (payload with ordered banners, responsive candidates as R2/Cloudflare URLs, intrinsic dimensions, JPEG fallback, computed CTA insertion points, presentation; identical 404 for unknown/draft/paused/retired), `/view`, and `/cta-click` recording routers.
  - Implement the thin `/api/public/orders` router mapping to `OrderSubmissionService` (422 validation, 201 on persisted result, 503 non-sensitive persistence failure).
  - Router integration tests: public payload only for active+published, identical not-found for denied states, view/click recorded, order submission returns result only after persistence, validation errors field-specific.
  - _Requirements: 3.21, 3.22, 3.23, 3.24, 4.13, 4.14, 5.7, 5.8, 5.13, 5.14, 5.16, 5.17, 8.14, 8.15_
  - _Design: API Design → Public Landing, Checkout / Orders_

- [x] 18. Wire the order-management, fraud, and analytics admin API routers
  - Implement thin `/api/admin/orders` routers (list with ANDed status/product/landing/date filters + pagination, detail with fraud flags, transition mapping to the status graph with 409 on illegal, CSV export using active filters) with audit on transitions and export access.
  - Implement thin `/api/admin/fraud` routers (config get/put, blacklist get/post/delete, geoip-rules crud) and `/api/admin/analytics` routers (orders-per-day, landings, fraud) mapping to their services, with audit on fraud mutations.
  - Router integration tests: combined filters, illegal transition rejection, CSV export contents, config/blacklist/geoip validation + audit, analytics date-range responses and zero-rate cases.
  - _Requirements: 5.19, 5.20, 5.21, 5.22, 6.20, 6.21, 6.22, 6.24, 8.4, 8.5, 8.6, 8.7, 8.8, 8.9, 8.10, 8.11, 8.12, 8.13, 8.16, 10.9, 10.10_
  - _Design: API Design → Checkout/Orders, Fraud Config/Blacklist/GeoIP, Analytics_

- [x] 19. Build the frontend API client and shared components
  - Implement the typed `api/` client mirroring backend schemas with centralized auth transport and error handling that maps backend field errors to form controls; keep no long-lived secrets in browser code.
  - Implement reusable `components/`: responsive banner renderer (`srcset`/`sizes` pointing at R2/Cloudflare URLs, WebP + JPEG fallback, intrinsic dimensions, alt text, lazy loading below the fold), CTA control, accessible form fields, and a modal with focus capture/return.
  - Component + a11y tests: error-to-field mapping, responsive image attributes and lazy loading, modal focus management, keyboard operation and validation announcements.
  - _Requirements: 4.13, 4.14, 8.19, 8.20, 10.4, 10.14_
  - _Design: Component and Service Design → frontend api/ and components/; Security and Privacy Design → output encoding, redirect allowlist_

- [x] 20. Build the public landing and COD checkout flow
  - Implement the `/p/:slug` route: fetch payload, record a view on display, insert CTAs per configured mode, render 1–15 banners mobile-first without overflow/overlap, record a CTA click on activation, and open the COD form inline or as an accessible modal (focus in, return to activating CTA on close).
  - Implement the checkout feature: client validation matching Colombian phone rules, submit to `/api/public/orders`, map server field errors, and render a generic not-found view for unknown/draft/paused/retired slugs.
  - Frontend unit + property (fast-check) + a11y tests: rendering across 1–15 banners, CTA positions per mode and edge intervals/positions, inline vs modal, client validation + server-error mapping, not-found behavior, keyboard/accessibility on the critical flow.
  - _Requirements: 3.12, 3.13, 3.14, 3.17, 3.18, 3.23, 3.24, 3.25, 5.1, 5.2, 5.3, 5.4, 5.5, 5.6, 8.14, 8.15_
  - _Design: Component and Service Design → routes (public); Testing Strategy → frontend + property-based tests (CTA positions)_

- [x] 21. Build the admin dashboard features
  - [x] 21.1 Admin auth guard and product/landing management UI
    - Implement `/admin/login` and UI route guards (backend authorization authoritative), product management (create/view/edit/soft-delete labeled as retirement/activate/pause with preservation messaging), and landing management (banner upload/removal/ordered up-down controls only, alt text, slug, CTA mode, presentation, publish/unpublish).
    - Component tests: guarded routes redirect unauthenticated users, product controls and retirement wording, banner ordering controls, publish gating feedback.
    - _Requirements: 8.1, 8.2, 8.3, 7.5, 7.8_
    - _Design: Component and Service Design → routes (admin); Frontend Conventions_
  - [x] 21.2 Order management, fraud settings, and analytics UI
    - Implement order list with filters (status/product/landing/inclusive date range), order detail with attribution/metadata/fraud flags, permitted status-transition actions with rejection handling, fraud settings controls (duplicate window/match fields/blacklist/rate limit/geoip), analytics dashboards (orders-per-day, per-landing conversion, fraud rate), and CSV export request using active filters.
    - Component + a11y tests: combined filters, status action success/rejection display, fraud-flag presentation, fraud settings validation mapping, analytics rendering incl. zero rates, CSV request behavior, keyboard/focus and error announcement.
    - _Requirements: 8.4, 8.5, 8.6, 8.7, 8.8, 8.9, 8.10, 8.11, 8.12, 8.13, 8.16, 8.19, 8.20, 8.21, 6.22_
    - _Design: Component and Service Design → frontend feature modules; Security and Privacy Design → CSV neutralization, a11y_

- [x] 22. Implement scheduled operational tasks
  - [x] 22.1 Neon backup monitoring and restore verification
    - Implement `BackupMonitorTask` that records the latest Neon managed-backup result and a periodic backup-verification outcome (confirming a Neon backup/recovery point can restore a valid database) for the Operational Read Interface, and records a failure result without altering existing valid backups. No custom pg_dump job.
    - Tests: backup result recorded, verification reports restore outcome, recorded failure preserves existing backups (using synthetic data / stubbed Neon status).
    - _Requirements: 9.12, 9.13, 9.14, 9.15_
    - _Design: Deployment and Operations Design → Backups (Neon managed); Component and Service Design → services (tasks)_
  - [x] 22.2 GeoIP update task (validate-before-activate)
    - Implement in-instance `GeoIpUpdateTask` that downloads a replacement GeoLite2 database to ephemeral container storage, validates it, and only then atomically activates it, preserving the last known-good (bundled) file and recording failure on validation error.
    - Tests: successful validate+activate swaps the active database; failed validation preserves last-known-good and records failure.
    - _Requirements: 9.16, 9.17_
    - _Design: Deployment and Operations Design → GeoIP updates; infrastructure/geoip_
  - [x] 22.3 Image orphan cleanup task (R2)
    - Implement in-instance `ImageCleanupTask` deriving liveness from DB references (protecting referenced and `in_progress` assets), deleting only unreferenced R2 objects, idempotent, logging each outcome, tolerating already-missing objects, and never touching in-flight-operation objects.
    - Tests (R2 mock): removes only orphans, protects live/historical/in-progress references, records missing-object result and continues, idempotent re-run.
    - _Requirements: 4.16, 4.17, 4.18_
    - _Design: Image Pipeline Design → orphan cleanup; Component and Service Design → services (tasks)_
  - [x] 22.4 Expose task status to the operational read interface
    - Wire the last Neon-backup/GeoIP-update/image-cleanup success/failure + timestamps into `/api/admin/ops/jobs`.
    - Test: ops jobs endpoint reflects recorded task results without leaking excluded content.
    - _Requirements: 7.14, 10.21, 9.14, 9.17_
    - _Design: API Design → Operational Read Interface_

- [x] 23. Author the backend container and cloud deployment configuration
  - [x] 23.1 Backend Dockerfile and Koyeb service manifest
    - Author the `backend/Dockerfile` (pinned base image, dependency install, Prisma client generation, GeoLite2 bundled at build, non-root, health endpoint) and the Koyeb service/deploy manifest (env vars for Neon/Upstash/R2/JWT/GeoIP, health check, restart policy, single instance).
    - Validate the image builds and the container starts and serves the health route; assert no secrets are baked into the image.
    - _Requirements: 1.12, 9.1, 9.2, 9.3, 9.4, 9.7, 9.8, 9.18, 9.19_
    - _Design: Deployment and Operations Design → Backend (Koyeb); Technology Stack and Constraints_
  - [x] 23.2 Cloudflare Pages, DNS/routing, R2, and env example
    - Author the Cloudflare Pages build/SPA-fallback config, Cloudflare DNS/routing notes (SPA to Pages, `/api` to Koyeb, image URLs from R2), R2 bucket config (CORS, immutable cache, public host), and `.env.example` (names + safe examples only). Configure HTTP→HTTPS and compression at the edge.
    - Validate the frontend production build (`pnpm --prefix frontend run build`) and Pages config; assert only Cloudflare Pages + Koyeb receive public traffic and Neon/Upstash endpoints stay private; confirm R2 immutable cache headers on variant URLs.
    - _Requirements: 9.5, 9.6, 9.7, 9.9, 9.10, 9.11, 9.20, 9.21, 4.15, 4.19, 4.22, 1.14_
    - _Design: Architecture; Deployment and Operations Design → Frontend/DNS/R2_

- [x] 24. Assemble end-to-end integration and performance/accessibility validation
  - Implement E2E tests proving the critical path (publish active product → open `/p/{slug}` → click CTA → submit COD form → apply fraud rules → find order and flags in admin) and each branch: clean `pending`, duplicate, blacklist, rate-limit (Redis), GeoIP flag, GeoIP block, and draft/paused/retired denial (identical not-found); assert atomic single-order classification and no partial order on persistence failure.
  - Implement the production-build 4G LCP measurement with image variants served from R2/Cloudflare, recording profile, fixture sizes, run count, and measured LCP (< 2.5s claimed only from production build), plus automated a11y assertions on critical flows.
  - Run the full backend and frontend suites, static checks, `prisma validate` + migrate check, backend Docker image build, and frontend production build; wire everything so no code path is orphaned.
  - _Requirements: 1.1, 3.25, 3.26, 5.13, 5.14, 5.15, 5.16, 5.17, 6.19, 8.19, 8.20_
  - _Design: Testing Strategy → integration/E2E, property-based, accessibility, performance validation, build/config validation_

## Task Dependency Graph

```mermaid
graph TD
    T1[1. Scaffolding & tooling]
    T2[2. Prisma client, Neon & Redis]
    T3[3. Prisma schema models & migrations]
    T4[4. Settings, logging, request context]
    T5[5. Auth core]
    T6[6. Products domain & lifecycle]
    T7[7. Landings/banners domain & publication]
    T8[8. Image pipeline & banner upload (R2)]
    T9[9. Orders domain]
    T10[10. Fraud domain & config/blacklist/geoip]
    T11[11. GeoIP resolver]
    T12[12. Order-submission orchestration]
    T13[13. Analytics domain & service]
    T14[14. CSV export service]
    T15[15. Auth & ops routers]
    T16[16. Product/landing admin routers]
    T17[17. Public landing & checkout routers]
    T18[18. Orders/fraud/analytics admin routers]
    T19[19. Frontend API client & components]
    T20[20. Public landing & checkout flow]
    T21[21. Admin dashboard features]
    T22[22. Scheduled operational tasks]
    T23[23. Backend container & cloud deployment]
    T24[24. E2E & performance/a11y validation]

    T1 --> T2
    T2 --> T3
    T1 --> T4
    T3 --> T4
    T2 --> T5
    T4 --> T5
    T3 --> T6
    T3 --> T7
    T3 --> T8
    T3 --> T9
    T3 --> T10
    T2 --> T10
    T4 --> T11
    T6 --> T12
    T7 --> T12
    T9 --> T12
    T10 --> T12
    T11 --> T12
    T2 --> T12
    T3 --> T13
    T9 --> T14
    T5 --> T15
    T5 --> T16
    T6 --> T16
    T7 --> T16
    T8 --> T16
    T7 --> T17
    T12 --> T17
    T13 --> T17
    T12 --> T18
    T14 --> T18
    T13 --> T18
    T10 --> T18
    T1 --> T19
    T19 --> T20
    T17 --> T20
    T19 --> T21
    T16 --> T21
    T18 --> T21
    T8 --> T22
    T11 --> T22
    T14 --> T22
    T15 --> T22
    T23 --> T24
    T20 --> T24
    T21 --> T24
    T22 --> T24
    T18 --> T24
```
