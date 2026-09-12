/** EchoTales design system tokens -- editorial archive, not SaaS dashboard.
 * Dark ("ink") is the default theme (`:root`); `[data-theme="light"]` ("paper")
 * on <html> overrides the same variable set. Every color is a CSS var so both
 * themes stay single-sourced instead of duplicated Tailwind classes.
 *
 * Three type families, each with a distinct job (never interchangeable):
 * `font-display` (Fraunces) for literary/story moments, `font-sans` (Source
 * Sans 3, deliberately not Inter) for application chrome, `font-mono`
 * (JetBrains Mono) for metadata, evidence sourcing, and system state.
 *
 * Corners are sharp by design (max 2px) -- rounded-everything reads as
 * generic SaaS. Shadows are hairline rules, not drop shadows or glows.
 */
module.exports = {
  content: ['./src/**/*.{js,jsx,ts,tsx}', './public/index.html'],
  darkMode: ['selector', '[data-theme="dark"]'],
  theme: {
    fontSize: {
      xs: ['0.6875rem', { lineHeight: '1rem', letterSpacing: '0.04em' }],
      sm: ['0.8125rem', { lineHeight: '1.3rem' }],
      base: ['0.9375rem', { lineHeight: '1.6rem' }],
      lg: ['1.125rem', { lineHeight: '1.7rem' }],
      xl: ['1.375rem', { lineHeight: '1.8rem' }],
      '2xl': ['1.75rem', { lineHeight: '2.1rem' }],
      '3xl': ['2.25rem', { lineHeight: '2.5rem' }],
      '4xl': ['3.25rem', { lineHeight: '3.4rem' }],
      '5xl': ['4.5rem', { lineHeight: '4.5rem' }],
    },
    extend: {
      colors: {
        bg: 'rgb(var(--c-bg) / <alpha-value>)',
        surface: 'rgb(var(--c-surface) / <alpha-value>)',
        surface2: 'rgb(var(--c-surface-2) / <alpha-value>)',
        border: 'rgb(var(--c-border) / <alpha-value>)',
        text: 'rgb(var(--c-text) / <alpha-value>)',
        muted: 'rgb(var(--c-muted) / <alpha-value>)',
        accent: 'rgb(var(--c-accent) / <alpha-value>)',
        'accent-2': 'rgb(var(--c-accent-2) / <alpha-value>)',
        success: 'rgb(var(--c-success) / <alpha-value>)',
        warning: 'rgb(var(--c-warning) / <alpha-value>)',
        danger: 'rgb(var(--c-danger) / <alpha-value>)',
      },
      fontFamily: {
        display: ['Fraunces', 'ui-serif', 'Georgia', 'serif'],
        sans: ['"Source Sans 3"', 'ui-sans-serif', 'system-ui', 'sans-serif'],
        mono: ['"JetBrains Mono"', 'ui-monospace', 'SFMono-Regular', 'monospace'],
      },
      spacing: {
        13: '3.25rem',
        18: '4.5rem',
        22: '5.5rem',
      },
      borderRadius: {
        none: '0px',
        sm: '2px',
        DEFAULT: '2px',
        md: '2px',
        lg: '2px',
      },
      boxShadow: {
        rule: 'inset 0 -1px 0 0 rgb(var(--c-border) / 1)',
        popover: '0 20px 48px rgb(0 0 0 / 0.45), 0 0 0 1px rgb(var(--c-border) / 1)',
      },
      keyframes: {
        'toast-in': { '0%': { opacity: 0, transform: 'translateY(6px)' }, '100%': { opacity: 1, transform: 'translateY(0)' } },
        reveal: { '0%': { opacity: 0, transform: 'translateY(10px)' }, '100%': { opacity: 1, transform: 'translateY(0)' } },
      },
      animation: {
        'toast-in': 'toast-in 200ms ease-out',
        reveal: 'reveal 420ms cubic-bezier(0.16, 1, 0.3, 1)',
      },
    },
  },
  plugins: [],
};
