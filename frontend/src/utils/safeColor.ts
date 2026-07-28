/**
 * Validates a color string is a safe #rgb or #rrggbb hex value.
 * Returns the color if valid, undefined otherwise.
 * Prevents arbitrary CSS injection from API boundary values.
 */
const HEX_COLOR_RE = /^#(?:[0-9a-fA-F]{3}|[0-9a-fA-F]{6})$/;

export function safeColor(value: string | null | undefined): string | undefined {
  if (!value) return undefined;
  return HEX_COLOR_RE.test(value) ? value : undefined;
}
