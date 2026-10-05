---
name: "Kotoba"
description: "A quiet Android companion for local JSON translation."
colors:
  surface: "#f6f7f2"
  raised: "#ecefe7"
  ink: "#243b2e"
  muted: "#58675a"
  primary: "#375746"
  on-primary: "#fff"
  soft: "#dce9d2"
  line: "#cdd5c9"
  error: "#963c35"
  error-bg: "#ffebe5"
  warning: "#66531d"
  warning-bg: "#f5edd5"
  focus: "#427759"
  dark-surface: "#171e19"
  dark-raised: "#232d25"
  dark-ink: "#e0e9db"
  dark-muted: "#b4c3b1"
  dark-primary: "#b0cfa5"
  dark-on-primary: "#193123"
  dark-soft: "#354d38"
  dark-line: "#445447"
  dark-error: "#ffc0b6"
  dark-error-bg: "#4b2825"
  dark-warning: "#e4d099"
  dark-warning-bg: "#3b3423"
  dark-focus: "#b0cfa5"
  connected: "#477348"
typography:
  headline:
    fontFamily: "Roboto, \"Segoe UI\", sans-serif"
    fontSize: "2.5rem"
    fontWeight: 500
    lineHeight: 1.1
    letterSpacing: "-.035em"
  job-title:
    fontFamily: "Roboto, \"Segoe UI\", sans-serif"
    fontSize: "1.85rem"
    fontWeight: 500
    lineHeight: 1.1
    letterSpacing: "-.035em"
  body:
    fontFamily: "Roboto, \"Segoe UI\", sans-serif"
    fontSize: "1rem"
    fontWeight: 400
    lineHeight: 1.55
  action:
    fontFamily: "Roboto, \"Segoe UI\", sans-serif"
    fontSize: ".93rem"
    fontWeight: 600
  label:
    fontFamily: "Roboto, \"Segoe UI\", sans-serif"
    fontSize: ".86rem"
    fontWeight: 550
  caption:
    fontFamily: "Roboto, \"Segoe UI\", sans-serif"
    fontSize: ".78rem"
    fontWeight: 400
    lineHeight: 1.5
  code:
    fontFamily: "monospace"
    fontSize: ".72rem"
    lineHeight: 1.5
rounded:
  small: "8px"
  field: "10px"
  message: "12px"
  surface: "16px"
  pill: "20px"
  action: "28px"
spacing:
  tight: "8px"
  compact: "12px"
  regular: "16px"
  roomy: "20px"
  section: "24px"
components:
  button-primary:
    backgroundColor: "{colors.primary}"
    textColor: "{colors.on-primary}"
    typography: "{typography.action}"
    rounded: "{rounded.action}"
    padding: "13px 18px"
    width: "100%"
  button-secondary:
    textColor: "{colors.ink}"
    typography: "{typography.action}"
    rounded: "{rounded.action}"
    padding: "13px 18px"
    width: "100%"
  button-text:
    textColor: "{colors.primary}"
    padding: "8px 0"
  field:
    backgroundColor: "{colors.surface}"
    textColor: "{colors.ink}"
    rounded: "{rounded.field}"
    padding: "13px"
    width: "100%"
  navigation:
    backgroundColor: "{colors.raised}"
    textColor: "{colors.muted}"
  state-completed:
    backgroundColor: "{colors.soft}"
    textColor: "{colors.primary}"
    rounded: "{rounded.pill}"
    padding: "8px 12px"
  document:
    backgroundColor: "{colors.raised}"
    rounded: "{rounded.surface}"
  progress:
    backgroundColor: "{colors.raised}"
    rounded: "{rounded.surface}"
    padding: "24px 20px"
  job-row:
    textColor: "{colors.ink}"
    padding: "16px 0"
    width: "100%"
  snackbar:
    backgroundColor: "{colors.ink}"
    textColor: "{colors.surface}"
    rounded: "{rounded.small}"
    padding: "9px 12px 9px 16px"
---

# Design System: Kotoba

## Overview

**Creative North Star: "The Facing-Page Desk"**

Kotoba is a quiet reading desk for translation work: warm surfaces, deep green ink and leaf-toned actions keep the document and its state readable. The source and translated file remain distinct; typography and ruled rows provide structure without decorative imagery.

The interface uses Android system typography, generous touch targets and an OS-driven dark palette. Tonal containers group document, progress and connection information; history stays a simple list. This documents the implemented React/Tauri Android system, using the direction already delegated by the user.

**Key Characteristics:**
- Warm paper and green ink, paired with a complete dark palette.
- System typography and large touch controls.
- Flat tonal containers, ruled history and linear progress.
- Code-led visual assets with no illustrative raster imagery.

## Colors

The palette reads as warm paper, green ink and restrained leaf-colored actions. The frontmatter records the literal CSS custom-property values; `dark-` entries are the corresponding OS dark-theme overrides, not an additional decorative palette.

### Primary

- **Green ink action** (`primary` / `dark-primary`): filled main actions, active navigation, progress fills and functional icons.
- **Action lettering** (`on-primary` / `dark-on-primary`): the foreground inside filled actions.
- **Leaf wash** (`soft` / `dark-soft`): active navigation capsules, completed-state badges, selection and secondary pressed states.
- **Focus green** (`focus` / `dark-focus`): keyboard and input focus outlines.
- **Connected green** (`connected`): the light-theme connection dot; dark mode uses the primary color.

### Neutral

- **Reading paper** (`surface` / `dark-surface`): application background and form fields.
- **Document paper** (`raised` / `dark-raised`): document, progress and PC containers plus the navigation surface.
- **Text ink** (`ink` / `dark-ink`): primary reading content; inverted for the snackbar.
- **Quiet ink** (`muted` / `dark-muted`): labels, supporting text and inactive navigation.
- **Ruled edge** (`line` / `dark-line`): separators, outlines and progress tracks.

Semantic feedback extends these roles: `error` on `error-bg` identifies failures, while `warning` on `warning-bg` identifies interruptions or review needs. Dark counterparts preserve the same meaning. Avoid inferring status from hue alone.

## Typography

The application uses Roboto with Segoe UI and sans-serif fallbacks, without a downloaded display font. The root size is 16px. Paragraphs use the body line height; ordinary supporting copy is generally smaller than the root size. Sizes remain in rem to follow font scaling.

- **Headline:** the principal page heading; its frontmatter role is the default phone size. At widths up to 360px it becomes 2.15rem, and from 700px it becomes 2.7rem.
- **Job title:** the smaller filename heading allows wrapping anywhere and explicit word breaking.
- **Body:** the base reading rhythm. Page introductions use .98rem with muted ink.
- **Action and label:** medium-to-semibold text for buttons and field names.
- **Caption:** secondary explanations with generous line height.
- **Code:** monospace field previews and review paths. Pairing codes use a slightly larger .78rem size.
- **Numbers:** file inspection counts and progress counts use tabular numerals for stability; progress totals remain visually subordinate.

## Layout

Phone layout is a centered single column capped at 600px. The top bar has a 72px minimum height; main content has 24px side padding. Page headings receive space below them before the next group. The document import target is at least 225px high. The app includes safe-area inset padding and reserves 100px plus the bottom inset for fixed navigation.

The phone navigation is fixed to the bottom, with three equal destinations, a minimum 80px surface height and minimum 60px buttons. At 700px it becomes a 96px vertical rail: the shell grows to 820px, reserves 96px on the left, and centers main content within 660px with 40px side padding. At widths up to 360px, main side padding becomes 18px and the header tightens. There is no multi-column dashboard layout.

Most controls offer at least 48px of height; primary and secondary actions offer at least 54px. The target-language select is explicitly at least 48px high. Filenames, messages, endpoints and code paths wrap instead of requiring horizontal scrolling. Empty-state supporting text is capped at 32ch.

## Elevation & Depth

The interface is flat by default. Tonal paper surfaces, thin borders and ruled list rows provide grouping. The snackbar alone has a compact ambient shadow, documented in the sidecar; it appears above navigation. Content has no gradients, blur or decorative elevation.

## Shapes

Rounded document, progress and PC surfaces share the surface radius. Fields use the tighter field radius; feedback messages use the message radius. Main actions are elongated pills, and status or navigation capsules use the pill radius. History rows remain unboxed and separated by a single thin line. Progress tracks are thin and softly rounded. These shapes do not imply a general card grid.

## Components

### Buttons

Primary actions use green ink with contrasting lettering and occupy the available width. Secondary actions keep the page background and add a ruled outline. Text actions are compact and unfilled. Primary press feedback darkens with a brightness filter; secondary press feedback uses the leaf wash. Disabled buttons use .48 opacity and a disabled cursor. Buttons and disclosure summaries have a 3px focus outline with 3px offset. There is no dedicated pointer-hover treatment in the shipped touch interface.

### Fields and language choice

Fields have a thin outline, paper background and internal padding, with visible labels and supporting text. Inputs, textareas and selects use a 2px focus outline with 2px offset. Textareas resize vertically; the pairing code is monospace. The native target-language select keeps its native affordance and a 48px minimum height. Strict-code selection is a native checkbox with a 26px control, 12px margins and a label row at least 66px high.

### Navigation and state labels

Three permanent destinations read Traduire, Historique and Mon PC. Active navigation uses primary text plus a leaf capsule behind its icon; the active page is marked with `aria-current`. Completed labels use the same leaf wash, failed labels the error palette, and other labels the raised surface. Connection status combines a dot with readable words and a navigation affordance.

### Document surface

The full import surface is actionable and names the file format and 50 Mo limit. Selecting a file replaces its contents in place with the wrapped filename, size and integrity note. Inspection replaces the footer with a real selected-text count. The structure stays consistent through the workflow; it is not an illustrative upload card.

### History row and progress surface

History rows are at least 88px high, with document icon, wrapped filename, subordinate status metadata and a chevron. Metadata carries target language and either running counts or a date and time including seconds. Active jobs add a 3px linear progress bar. Detail progress uses a 6px bar, tabular completed count, subordinate total and readable status message. The progress container shares the document surface language.

### Feedback and motion

Inline errors use `role="alert"`; connectivity and transient success messages use status announcements. Review warnings remain visible above the relevant actions. Snackbars sit above phone navigation and last six seconds unless dismissed. Only the options chevron, progress fill and loading spinner move: .2s ease-out rotation, .3s ease-out width changes, and a 1.1s linear looping spin. Reduced-motion preference removes animations and transitions.

Icons in the UI are line SVGs. The application identity icon is hand-authored SVG compiled into native icon resources. The design is code-led and uses no illustrative raster assets. Android system-bar colors and icon contrast track configuration/theme changes; these native surfaces should remain visually continuous with the web content.

## Do's and Don'ts

### Do:
- Do use the OS theme palette consistently across content and Android system bars.
- Do preserve 48px minimum language selection and icon-button targets, and 54px primary actions.
- Do allow filenames, messages and technical paths to wrap.
- Do show history time and destination language alongside state.
- Do keep the import limit explicit: 50 Mo.
- Do pair progress and status colors with readable text.

### Don't:
- Don't add decorative raster illustrations to the file-processing flow.
- Don't replace linear progress with a decorative ring.
- Don't turn the ruled history into nested cards.
- Don't hide review warnings or treat cached history as proof of connectivity.
