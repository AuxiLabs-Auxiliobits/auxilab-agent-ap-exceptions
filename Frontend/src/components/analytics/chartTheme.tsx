/**
 * Shared Recharts styling for the Analytics screen so every chart (this-run
 * breakdown + cross-run trends) reads as one cohesive system: the same palette,
 * gradient bar fills, muted theme-aware axes, and a polished tooltip in light
 * and dark.
 */

// On-brand palette — corporate blue led, distinguishable on light + dark cards.
export const CHART_COLORS = {
  blue: '#2563EB',
  sky: '#0EA5E9',
  green: '#16A34A',
  amber: '#D97706',
  red: '#DC2626',
  violet: '#7C3AED',
  cyan: '#0891B2',
  slate: '#64748B',
} as const;

// Severity in exception-scale order: High (red) · Medium (amber) · Low (green).
export const SEVERITY_FILLS = [CHART_COLORS.red, CHART_COLORS.amber, CHART_COLORS.green];

// Categorical series (resolution paths, value-by-type, etc.).
export const CATEGORICAL = [
  CHART_COLORS.blue, CHART_COLORS.sky, CHART_COLORS.green, CHART_COLORS.amber,
  CHART_COLORS.red, CHART_COLORS.violet, CHART_COLORS.cyan, CHART_COLORS.slate,
];

// Muted, theme-aware axis ticks (legible in both themes).
export const AXIS_TICK = { fontSize: 11, fill: 'hsl(var(--muted-foreground))' } as const;

// Tooltip: popover surface, soft shadow, readable text in light AND dark.
export const TOOLTIP = {
  contentStyle: {
    background: 'hsl(var(--popover))',
    border: '1px solid hsl(var(--border))',
    borderRadius: 10,
    color: 'hsl(var(--popover-foreground))',
    boxShadow: '0 10px 30px -12px rgba(0,0,0,0.45)',
    fontSize: 12,
    padding: '8px 12px',
  },
  labelStyle: { color: 'hsl(var(--popover-foreground))', fontWeight: 600, marginBottom: 4 },
  itemStyle: { color: 'hsl(var(--popover-foreground))', padding: 0 },
} as const;

// Subtle hover band behind bars (instead of Recharts' heavy default).
export const BAR_CURSOR = { fill: 'hsl(var(--muted))', opacity: 0.5 } as const;
