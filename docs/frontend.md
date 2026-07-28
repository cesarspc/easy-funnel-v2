# Frontend Development

## Stack

- **Framework**: React 18+
- **Build Tool**: Vite
- **Language**: TypeScript (strict mode)
- **Router**: React Router
- **Deployment**: Cloudflare Pages (static SPA)
- **Architecture**: Single-page application (SPA) serving both public storefront and private admin

## TypeScript Standards

Use strict mode. Avoid `any`; narrow `unknown` at boundaries.

```typescript
// ✓ Good
const data: unknown = await response.json();
if (isValidOrder(data)) {
  processOrder(data);
}

// ✗ Bad
const data: any = await response.json();
processOrder(data);
```

## API Client

### Centralized Transport

Keep API request/response types aligned with backend contract. Centralize auth/error handling in the API client.

```typescript
// api/client.ts
export class ApiClient {
  private async request<T>(endpoint: string, options?: RequestInit): Promise<T> {
    const response = await fetch(`/api${endpoint}`, {
      ...options,
      headers: {
        'Content-Type': 'application/json',
        ...this.authHeaders(),
        ...options?.headers,
      },
    });
    
    if (!response.ok) {
      throw await this.handleError(response);
    }
    
    return response.json();
  }
}
```

### Type Safety

Use generated or manually maintained types matching backend schemas.

```typescript
// ✓ Good — typed client
interface OrderCreate {
  landing_slug: string;
  full_name: string;
  phone: string;
  department: string;
  city: string;
  address: string;
  quantity: number;
}

const order = await api.post<OrderResponse>('/public/orders', payload);

// ✗ Bad — untyped
const order = await fetch('/api/public/orders', { ... });
```

## Mobile-First Design

Build for paid social traffic arriving on narrow phone screens.

### Test Narrow Widths First

- Test `/p/:slug` at 375px, 360px, and 320px before desktop
- Banners must not overflow
- CTAs must not overlap
- Form must remain usable

### Responsive Images

Provide proper `srcset`/`sizes` for WebP with JPEG fallback:

```tsx
<picture>
  <source
    type="image/webp"
    srcSet={`
      ${variant480w} 480w,
      ${variant768w} 768w,
      ${variant1200w} 1200w,
      ${variant1600w} 1600w
    `}
    sizes="(max-width: 768px) 100vw, (max-width: 1200px) 80vw, 1200px"
  />
  <img
    src={fallbackJpeg}
    alt={banner.alt_text}
    width={banner.width}
    height={banner.height}
    loading="lazy"
  />
</picture>
```

Rules:
- Provide dimensions/aspect ratio to reduce layout shift
- Meaningful alt text (never "image" or empty unless decorative)
- Lazy loading for below-the-fold banners

## Public Landing (`/p/:slug`)

### Banner Rendering

- Support 1-15 banners without overflow or overlapping CTAs
- Render banners in stored order
- Implement only ordered controls (up/down or order index) — no drag canvas

### CTA Placement Modes

Support all three modes:
1. **After every banner**: CTA after each banner
2. **Every N banners**: CTA after every configured count (e.g., every 3 banners)
3. **Fixed positions**: CTAs at specific banner indices (e.g., positions 2, 5, 8)

Compute CTA positions server-side or in a pure function; never mutate banner list.

### COD Form

The COD form is a **pop-up only**. It never renders at the end of the landing:
tapping any CTA opens it as a dialog over the banner the buyer was looking at,
and closing it returns them to the same scroll position. `form_presentation` is
still stored and editable in the Admin Dashboard, but the public page ignores it.

```tsx
// ✓ Good — accessible pop-up
<Modal
  isOpen={isOpen}
  onClose={handleClose}
  title="Completa tu pedido"
  subtitle="Pago contraentrega: pagas al recibir."
>
  <CodForm landingSlug={slug} productName={name} unitPrice={price} onSuccess={onSuccess} />
</Modal>
```

Rules:
- Render through a portal on `document.body` so no banner/CTA-band ancestor can clip it
- Trap focus inside the dialog; move focus to the panel, not the first input (focusing an
  input raises the mobile keyboard and hides the offer recap)
- Close on Escape and on a backdrop tap; return focus to the activating CTA
- Prevent scroll on the background; only the field list scrolls
- Bottom sheet on phones, centered dialog from 640px up
- Keep the primary action sticky and visible, with the amount on it

Conversion rules for the form body:
- Restate the offer inside the pop-up (product, unit price, quantity, total) — never ask
  for an address before repeating what is being ordered and what will be paid
- State the COD promise where the commitment is asked for ("no pagas nada ahora")
- One column, 16px minimum controls (smaller triggers iOS zoom), correct `autoComplete`,
  `inputMode`, and `enterKeyHint` per field so mobile autofill can finish the form
- Validate on blur, never mid-keystroke; clear a field's error as soon as it is edited
- On submit with errors, focus the first invalid control; map backend 422 `{field, message}`
  onto the same controls
- No countdowns, invented scarcity, or unverifiable claims

### Client Validation

Client validation improves UX but **never substitutes for backend validation**.

Colombian phone rules must match backend normalization:
- Accept `+57` or `57` prefix or raw 10-digit number starting with `3`
- Strip spaces, hyphens, parentheses
- Validate result matches `+57` + 10 digits starting with `3`

Show field-specific errors returned from backend.

## Admin Dashboard (`/admin/*`)

### Route Protection

Protect admin routes in the UI, but **treat backend authorization as authoritative**.

```tsx
// ✓ Good
<Route element={<RequireAuth />}>
  <Route path="/admin/orders" element={<OrdersPage />} />
</Route>

// Backend still validates every admin API call
```

### Functionality

- Manage landings: upload/remove/reorder banners (up-down controls only), edit alternative text, slug, CTA placement mode, COD form presentation, and publish/unpublish
- Filter orders by status, date range, fraud flags
- Display fraud flags clearly (which rules triggered, why)
- Transition order status through legal state graph
- Request CSV export (backend enforces auth + spreadsheet-safe encoding)

### Security

Do **not** put long-lived secrets in:
- Browser code
- Vite environment variables
- Local storage
- Logs or analytics events
- URLs

Prefer secure, HttpOnly, SameSite cookies for JWT transport when compatible with deployment.

## Accessibility

Preserve:
- Keyboard operation (Tab, Enter, Escape)
- Visible focus indicators
- Semantic HTML (`<button>`, `<form>`, headings, labels)
- Accessible labels and ARIA when needed
- Modal focus management
- Useful validation announcements (live regions)

Test critical flows with keyboard only.

## No External Dependencies

Do **not** add:
- Third-party trackers
- Hosted fonts (use system fonts or bundle locally)
- Remote scripts or CDN links
- External image URLs (all images via R2)
- Analytics SaaS

Serve all required assets locally or from approved cloud infrastructure (Cloudflare).

## Testing Requirements

Frontend tests must cover:

- Public/mobile landing rendering across 1-15 banners
- CTA positions for every mode and edge interval/position values
- Inline and accessible modal COD forms
- Client validation and server error mapping
- Draft/paused/not-found behavior
- Admin filters, status actions, fraud flag presentation, CSV request behavior
- Responsive image attributes and loading policy
- Keyboard and accessibility checks for critical flows

Use property-based tests (fast-check) for CTA placement logic if applicable.

## Build and Deployment

### Production Build

```bash
pnpm --prefix frontend run build
```

Output is a static SPA deployed to Cloudflare Pages.

### Cloudflare Pages Configuration

Configure SPA fallback (serve `index.html` for all routes except `/api`):

```toml
# wrangler.toml or pages config
[[redirects]]
  from = "/*"
  to = "/index.html"
  status = 200
  conditions = {header = {name = "X-Forwarded-Path", value = "^(?!/api).*"}}
```

### Environment Variables

Frontend build-time variables should **not** contain secrets. Publicly visible values only (e.g., `VITE_API_BASE_URL` if needed).

## Performance

A public landing with representative banners must achieve **LCP < 2.5 seconds** under a mobile 4G network profile.

Record:
- Profile settings (latency, bandwidth)
- Fixture sizes (banner count, image sizes)
- Run count
- Measured result

Do **not** claim the target from development-server timings. Test a production build with locally served image variants.
