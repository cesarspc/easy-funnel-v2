---
name: Easy Funnel Admin Dashboard
description: A graphite instrument panel for running COD orders, products, and fraud rules — color rationed to state and action, never decoration.
colors:
  graphite-panel: "#1c1f22"
  graphite-panel-raised: "#242830"
  graphite-line: "#33383f"
  paper: "#f7f6f3"
  paper-raised: "#ffffff"
  ink: "#1a1c1e"
  ink-quiet: "#5b6169"
  ink-faint: "#8a9099"
  hairline: "#e4e2dd"
  signal-amber: "#e8862c"
  signal-amber-deep: "#c56a17"
  status-pending: "#8a7245"
  status-confirmed: "#3d6b8f"
  status-shipped: "#5c5a8f"
  status-delivered: "#3f7d52"
  status-cancelled: "#8a9099"
  status-flagged: "#b8402f"
typography:
  body:
    fontFamily: "Inter, -apple-system, 'Segoe UI', Roboto, sans-serif"
    fontSize: "0.9375rem"
    fontWeight: 400
    lineHeight: 1.5
    letterSpacing: "normal"
  label:
    fontFamily: "Inter, -apple-system, 'Segoe UI', Roboto, sans-serif"
    fontSize: "0.75rem"
    fontWeight: 600
    lineHeight: 1.3
    letterSpacing: "0.04em"
  title:
    fontFamily: "Inter, -apple-system, 'Segoe UI', Roboto, sans-serif"
    fontSize: "1.125rem"
    fontWeight: 600
    lineHeight: 1.3
    letterSpacing: "-0.01em"
  data:
    fontFamily: "'IBM Plex Mono', ui-monospace, monospace"
    fontSize: "0.875rem"
    fontWeight: 400
    lineHeight: 1.4
    letterSpacing: "normal"
rounded:
  sm: "4px"
  md: "6px"
  lg: "10px"
spacing:
  xs: "4px"
  sm: "8px"
  md: "16px"
  lg: "24px"
  xl: "40px"
components:
  button-primary:
    backgroundColor: "{colors.signal-amber}"
    textColor: "#1a1206"
    rounded: "{rounded.md}"
    padding: "10px 18px"
  button-primary-hover:
    backgroundColor: "{colors.signal-amber-deep}"
    textColor: "#1a1206"
    rounded: "{rounded.md}"
    padding: "10px 18px"
  button-secondary:
    backgroundColor: "transparent"
    textColor: "{colors.ink}"
    rounded: "{rounded.md}"
    padding: "10px 18px"
---

# Design System: Easy Funnel Admin Dashboard

## Overview

**Creative North Star: "The Instrument Panel"**

Easy Funnel's Admin Dashboard is built like the control surface of a well-made piece of hardware: a graphite chrome that houses fixed rows of controls, a calm paper-light work surface where the actual data lives, and color reserved strictly for what is active, actionable, or in a specific named state. Nothing on screen competes with the task. The Administrator runs this dashboard for hours across a working day, often the same screens dozens of times — the panel disappears into the work, the way a mixing console or a synthesizer's front panel disappears once you know it.

This system deliberately refuses the generic admin-template default: white cards with soft drop shadows floating on light gray, colorful pill badges scattered for "visual interest," a different accent per section. Instead, exactly one accent (a warm signal amber, the "lit LED" of this panel) marks primary actions and the current/active state. Order status is a small, fixed, named vocabulary of quiet color — read as instrumentation, not decoration.

Public-facing Landing chrome (CTA, COD form, modal) is out of scope for this file; it is designed and documented separately since it serves a Persuade audience (cold buyers) under different rules. This file governs the Admin Dashboard only.

**Key Characteristics:**
- Graphite instrument chrome (sidebar, top bar) housing a calm paper-light work surface (tables, forms, panels)
- One accent color, rationed to primary actions and "current" marks only
- A small, fixed, named status vocabulary rendered as quiet dot-led pills, never loud fills
- One typeface for everything except tabular/numeric data, which gets a monospace face for alignment and scannability
- Flat by default; depth comes from the graphite/paper split and hairlines, not shadows

## Colors

Color is rationed like panel LEDs: almost everything is graphite or paper, and the few colors that exist each mean exactly one thing.

### Primary
- **Signal Amber** (`#e8862c`): the panel's one lit LED. Used only for primary action buttons, the active/current sidebar item, and focus-adjacent "this is live" marks. Never used decoratively or on more than one element's worth of a screen at a time.
- **Signal Amber Deep** (`#c56a17`): hover/active state of Signal Amber controls.

### Neutral — Chrome (graphite)
- **Graphite Panel** (`#1c1f22`): sidebar and top-bar ground. The instrument housing.
- **Graphite Panel Raised** (`#242830`): hovered/active rows and the current section marker inside chrome.
- **Graphite Line** (`#33383f`): hairlines and dividers inside chrome surfaces.

### Neutral — Work surface (paper)
- **Paper** (`#f7f6f3`): the main content ground. Calm, low-glare, built for a full day of reading tables.
- **Paper Raised** (`#ffffff`): cards, modals, and input fields sitting on Paper.
- **Ink** (`#1a1c1e`): primary text on Paper.
- **Ink Quiet** (`#5b6169`): secondary text, field labels, metadata.
- **Ink Faint** (`#8a9099`): placeholder text, disabled labels, timestamps.
- **Hairline** (`#e4e2dd`): borders and dividers on Paper surfaces.

### Status vocabulary (Order_Status)
- **Pending** (`#8a7245`, muted brass): submitted, awaiting confirmation.
- **Confirmed** (`#3d6b8f`, slate blue): confirmed, awaiting shipment.
- **Shipped** (`#5c5a8f`, slate violet): in transit.
- **Delivered** (`#3f7d52`, muted green): completed successfully.
- **Cancelled** (`#8a9099`, neutral gray): terminal, no further action.
- **Flagged for Review** (`#b8402f`, muted red): `flagged_fraud`, needs Administrator review.

**The One Lit LED Rule.** Signal Amber appears at most once per screen as a background fill. A repeatable per-row action (e.g. "Activate" on every paused row in a table) never uses the amber fill, since a table can render many rows at once — it uses the amber outline/text treatment instead, filling only on hover/confirm. The fill is reserved for the screen's one singular action (a page-level "New Product," "Export," "Save").

**The Named Status Only Rule.** No color is ever introduced to mean something outside the six Order_Status values above. A new status needs a named entry here before it needs a hex code in code.

## Typography

**Body/UI Font:** Inter (with -apple-system, "Segoe UI", Roboto, sans-serif fallback)
**Data Font:** IBM Plex Mono (with ui-monospace, monospace fallback)

**Character:** One disciplined grotesk carries headings, labels, buttons, and body text — Operate surfaces don't need a display/body pairing. Tabular and numeric data (prices, quantities, order IDs, timestamps, phone numbers) shift to a monospace face so columns align and digits don't jitter as they update.

### Hierarchy
- **Title** (600, 1.125rem, 1.3 line-height, -0.01em): page and panel headings.
- **Body** (400, 0.9375rem, 1.5 line-height): default UI text, form labels' associated copy, descriptions.
- **Label** (600, 0.75rem, 1.3 line-height, 0.04em tracking, uppercase): field labels, table column headers, status pill text, sidebar section headers.
- **Data** (400, 0.875rem monospace, 1.4 line-height): order IDs, prices, quantities, phone numbers, dates/timestamps, SKUs — anywhere alignment and scanning speed matter more than prose voice.

**The Silkscreen Label Rule.** Every label (`Label` style) is small, capitalized, tracked, and quiet — instrument silkscreen, never a shout. If a label needs to be louder to be noticed, the layout around it is wrong, not the label.

## Layout

Fixed rem scale, no fluid clamp() typography — this is a desk tool viewed at consistent DPI. Structural responsiveness only: the sidebar collapses to an icon rail below ~1024px and to an off-canvas drawer below ~640px; tables scroll horizontally rather than reflowing into cards.

Two-region shell: a fixed-width graphite sidebar (240px, collapsing to 64px icon rail) on the left holds top-level navigation (Products, Landings, Orders, Fraud, Analytics); the remaining width is the Paper work surface, with a slim top bar (session/logout, current section title) sitting on Paper, not on graphite. Content max-width is unconstrained for tables (data wants width) but forms and detail panels cap at ~720px for readability.

Spacing rhythm: 4/8/16/24/40px scale. More space above a heading than below it. Table rows are dense (40–44px row height) by design — Administrators scan many rows; Operate mode explicitly permits and rewards this density.

## Elevation & Depth

Flat by default. Depth comes from the graphite/paper split (chrome sits visually "in front of" or "behind" the work surface by contrast alone) and from 1px hairlines, not shadows. The one exception: modals and dropdown/popover overlays get a single soft, low-opacity shadow (`0 8px 24px rgba(0,0,0,0.18)`) strictly to separate them from the content behind, since they must escape their container (fixed-position or portal, never clipped by `overflow: hidden` ancestors).

**The Flat Instrument Rule.** Cards, table rows, and panels never carry a shadow at rest. A shadow appearing on something that isn't an overlay is a bug, not a style choice.

## Shapes

Restrained, slightly-rounded rectangles throughout (6px radius standard, 4px on compact controls like status pills and chips, 10px on modals/large panels). No pill-shaped buttons, no fully circular avatars-as-decoration. Borders are 1px hairlines at rest; focus and active states thicken to 2px rather than changing radius or shape.

## Components

### Buttons
- **Shape:** 6px radius (`{rounded.md}`), 1px border on secondary/ghost variants.
- **Primary:** Signal Amber fill (`#e8862c`), near-black ink text (`#1a1206` for contrast), 10px/18px padding. Reserved for the screen's one singular action — never a per-row repeatable action in a table.
- **Repeatable row action (e.g. "Activate" on any paused row):** Signal Amber outline and text at rest, filling with Signal Amber only on hover — since a table can show many of these at once, none of them are the fill at rest.
- **Secondary:** transparent background, Ink text, 1px Hairline border; hover raises to Paper Raised background.
- **Hover/Focus:** Primary darkens to Signal Amber Deep on hover; all buttons get a 2px Signal-Amber-tinted focus ring on `:focus-visible`, never removed.
- **Active (pressed):** every button shifts 1px down and darkens slightly (`brightness(0.94)`) on `:active`, the tactile confirmation that a press registered.
- **Destructive (e.g. cancel order, retire product):** Ink text and Hairline border at rest; only fills with the muted Flagged red on hover/confirm, so danger reveals itself on intent, not by sitting red at rest.

### Status Pills
- **Style:** small rounded-4px pill, transparent/near-Paper background, a 6px solid dot in the status color plus the status Label-style text in Ink (not colored text) — the dot carries the color, not the fill or the text.
- **State:** static display only in v1 (no interactive filter chips beyond the existing filter controls).

### Tables
- **Style:** Paper background, 1px Hairline row dividers (no zebra striping), Label-style column headers in Ink Quiet, Data-style monospace for numeric/ID columns.
- **Row state:** hover raises background to Paper Raised. A selected row (deferred — no v1 screen has row selection yet; when one ships, use a 2px Signal Amber left rule, the same "armed" mark the sidebar uses for its current route).
- **Density:** 40–44px row height, no internal card padding around the table itself.

### Inputs / Fields
- **Style:** Paper Raised background, 1px Hairline border, 6px radius, Body-style text.
- **Focus:** border shifts to Signal Amber at 2px, no glow/shadow.
- **Error:** border shifts to Flagged red at 2px; error copy in Flagged red, Body-style, directly beneath the field, associated via `aria-describedby`.
- **Disabled:** Paper background (matches ground, not Paper Raised), Ink Faint text, no border color change beyond lightening.

### Navigation (Sidebar)
- **Style:** Graphite Panel ground, Label-style item text in a light neutral (`#c9ccd1`) at rest.
- **Active/current:** item background lifts to Graphite Panel Raised, text turns full white, and a 2px Signal Amber rule marks the left edge — the sidebar's own chase-light, always showing exactly one "now."
- **Hover:** background lifts to Graphite Panel Raised without the amber mark (that mark is reserved for the actual current route).
- **Mobile:** collapses to an off-canvas drawer triggered from the top bar; icon rail is the intermediate tablet state.

## Do's and Don'ts

### Do:
- **Do** ration Signal Amber to one primary action and one "current" mark per screen — its scarcity is what makes it legible as signal.
- **Do** use the Data (monospace) type role for every numeric/ID/timestamp column so figures align and scan quickly.
- **Do** keep chrome (graphite) and work surface (paper) visually distinct at all times — a user should always know, at a glance, "I am in navigation" vs. "I am in the data."
- **Do** give every interactive component all of default, hover, focus, active, disabled, loading, and error states before shipping it.

### Don't:
- **Don't** add a second accent color for a new feature. Extend the named status vocabulary or use Ink/Hairline neutrals instead.
- **Don't** put a shadow on a card, table row, or panel at rest — shadows are reserved for overlays that must separate from the content behind them.
- **Don't** use a colored left-border as a generic callout/alert device — the only colored left-rule in this system is the sidebar's current-route mark and the table's selected-row mark, both meaning "this one, right now."
- **Don't** use a modal for a task that doesn't need interruption or protected focus — prefer inline expansion or a side panel first (this constrains the Admin Dashboard; the public COD form's own Modal_Mode is a distinct, product-required exception documented in the Landing chrome's own design record).
