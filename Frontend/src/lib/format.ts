/**
 * Number/currency formatting helpers.
 *
 * Compact formatters condense large values to K / M / B (e.g. 11_800_000 ->
 * "$11.8M") for a cleaner layout and faster scanning in cards and chips.
 * Values below 1,000 render in full. Use the `*Full` variants for tooltips /
 * `title` attributes so the exact figure is one hover away.
 */

const compactCurrencyFmt = new Intl.NumberFormat('en-US', {
  style: 'currency',
  currency: 'USD',
  notation: 'compact',
  maximumFractionDigits: 1,
});

const compactNumberFmt = new Intl.NumberFormat('en-US', {
  notation: 'compact',
  maximumFractionDigits: 1,
});

const fullCurrencyFmt = new Intl.NumberFormat('en-US', {
  style: 'currency',
  currency: 'USD',
  maximumFractionDigits: 0,
});

/** e.g. 442450 -> "$442.5K", 11_800_000 -> "$11.8M", 450 -> "$450". */
export function formatCompactCurrency(value: number): string {
  return compactCurrencyFmt.format(value);
}

/** e.g. 12_500 -> "12.5K", 847 -> "847". */
export function formatCompactNumber(value: number): string {
  return compactNumberFmt.format(value);
}

/** Exact currency, no abbreviation — for tooltips / title attributes. */
export function formatCurrencyFull(value: number): string {
  return fullCurrencyFmt.format(value);
}
