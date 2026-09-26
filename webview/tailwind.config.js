/** EchoTales design system tokens (2026-09-26, second pass).
 *
 * History: the first direction was an editorial archive (Fraunces, brass,
 * 2px corners, mono eyebrows on everything) and read as too quiet; the second
 * was "cinematic dark" -- violet accent, radial glows, gradient logo, Inter
 * ExtraBold, 24px-radius cards, icon-in-the-corner stat tiles -- and read as
 * template output ("AI slop", product owner, 2026-09-26). This pass keeps the
 * dark, art-led canvas and removes the tells: a warm ink neutral instead of
 * blue-black, one amber accent (the light of a projector, not a gradient),
 * a serif for the book itself, 6-12px radii, hairline rules instead of
 * boxes-within-boxes, and no glow, glass or gradient anywhere.
 *
 * Colours are CSS variable triples (index.css) so dark and light stay
 * single-sourced. `accent` is for text, icons and focus rings; `primary` is
 * the button fill and `on-primary` the ink on it.
 */
module.exports = {
  content: ['./src/**/*.{js,jsx,ts,tsx}', './public/index.html'],
  darkMode: ['selector', '[data-theme="dark"]'],
  theme: {
    extend: {
      fontFamily: {
        display: ['Newsreader', 'Georgia', 'ui-serif', 'serif'],
        serif: ['Newsreader', 'Georgia', 'ui-serif', 'serif'],
        sans: ['"Instrument Sans"', 'ui-sans-serif', 'system-ui', 'sans-serif'],
        mono: ['"JetBrains Mono"', 'ui-monospace', 'SFMono-Regular', 'monospace'],
      },
      colors: {
        bg: 'rgb(var(--c-bg) / <alpha-value>)',
        surface: 'rgb(var(--c-surface) / <alpha-value>)',
        surface2: 'rgb(var(--c-surface-2) / <alpha-value>)',
        border: 'rgb(var(--c-border) / <alpha-value>)',
        text: 'rgb(var(--c-text) / <alpha-value>)',
        muted: 'rgb(var(--c-muted) / <alpha-value>)',
        accent: 'rgb(var(--c-accent) / <alpha-value>)',
        'accent-2': 'rgb(var(--c-accent-2) / <alpha-value>)',
        primary: 'rgb(var(--c-primary) / <alpha-value>)',
        'on-primary': 'rgb(var(--c-on-primary) / <alpha-value>)',
        'primary-2': 'rgb(var(--c-primary-2) / <alpha-value>)',
        cyan: 'rgb(var(--c-cyan) / <alpha-value>)',
        success: 'rgb(var(--c-success) / <alpha-value>)',
        warning: 'rgb(var(--c-warning) / <alpha-value>)',
        danger: 'rgb(var(--c-danger) / <alpha-value>)',
      },
      // Serif display sizes want far less negative tracking than a
      // geometric sans; -0.04em on Inter was one of the template tells.
      fontSize: {
        '6xl': ['3.75rem', { lineHeight: '1.05', letterSpacing: '-0.015em' }],
        '7xl': ['4.5rem', { lineHeight: '1.02', letterSpacing: '-0.02em' }],
        '8xl': ['5.5rem', { lineHeight: '1', letterSpacing: '-0.02em' }],
      },
      borderRadius: { lg: '6px', xl: '8px', '2xl': '10px', '3xl': '12px' },
      // Depth is a hairline and, for floating layers only, a shadow. No glow.
      boxShadow: {
        popover: '0 18px 48px rgb(0 0 0 / 0.45), 0 0 0 1px rgb(var(--c-border) / 1)',
        'depth-1': '0 0 0 1px rgb(var(--c-border) / 1)',
        'depth-2': '0 0 0 1px rgb(var(--c-text) / 0.18)',
        'depth-3': '0 12px 32px rgb(0 0 0 / 0.35), 0 0 0 1px rgb(var(--c-border) / 1)',
        glow: 'none',
      },
      keyframes: {
        'toast-in': { '0%': { opacity: 0, transform: 'translateY(6px)' }, '100%': { opacity: 1, transform: 'translateY(0)' } },
        reveal: { '0%': { opacity: 0, transform: 'translateY(12px)' }, '100%': { opacity: 1, transform: 'translateY(0)' } },
      },
      animation: {
        'toast-in': 'toast-in 200ms ease-out',
        reveal: 'reveal 520ms cubic-bezier(0.16, 1, 0.3, 1) both',
      },
    },
  },
  plugins: [],
};
