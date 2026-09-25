/** EchoTales design system tokens -- "cinematic dark" (2026-09-26 redesign).
 *
 * Replaces the earlier editorial-archive direction (Fraunces serif, brass
 * accent, 2px corners, mono eyebrows everywhere), which the product owner
 * found too quiet for a product whose output is illustrated panels and
 * voiced audio. Direction adapted from Runway's system in the
 * awesome-design-md library: a near-black canvas where the generated art
 * carries the colour, one geometric sans family, and a single electric
 * violet accent used sparingly.
 *
 * Every colour is a CSS variable triple (index.css) so the dark default and
 * the light theme stay single-sourced. `accent` is for text, icons and focus
 * rings; `primary` is the button fill, a deeper violet, because white text on
 * the lighter accent is only 4.35:1 -- below WCAG AA.
 */
module.exports = {
  content: ['./src/**/*.{js,jsx,ts,tsx}', './public/index.html'],
  darkMode: ['selector', '[data-theme="dark"]'],
  theme: {
    extend: {
      fontFamily: {
        display: ['"Inter Tight"', 'Inter', 'ui-sans-serif', 'system-ui', 'sans-serif'],
        sans: ['Inter', 'ui-sans-serif', 'system-ui', 'sans-serif'],
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
        'primary-2': 'rgb(var(--c-primary-2) / <alpha-value>)',
        cyan: 'rgb(var(--c-cyan) / <alpha-value>)',
        success: 'rgb(var(--c-success) / <alpha-value>)',
        warning: 'rgb(var(--c-warning) / <alpha-value>)',
        danger: 'rgb(var(--c-danger) / <alpha-value>)',
      },
      fontSize: {
        '6xl': ['3.75rem', { lineHeight: '1.02', letterSpacing: '-0.03em' }],
        '7xl': ['4.75rem', { lineHeight: '1', letterSpacing: '-0.035em' }],
        '8xl': ['6rem', { lineHeight: '0.98', letterSpacing: '-0.04em' }],
      },
      boxShadow: {
        popover: '0 24px 60px rgb(0 0 0 / 0.5), 0 0 0 1px rgb(var(--c-border) / 1)',
        'depth-1': '0 1px 2px rgb(0 0 0 / 0.25), 0 0 0 1px rgb(var(--c-border) / 1)',
        'depth-2': '0 8px 24px rgb(0 0 0 / 0.35), 0 0 0 1px rgb(var(--c-border) / 1)',
        'depth-3': '0 20px 50px rgb(0 0 0 / 0.45), 0 0 0 1px rgb(var(--c-border) / 1)',
        glow: '0 0 0 1px rgb(var(--c-accent) / 0.35), 0 10px 40px -10px rgb(var(--c-primary) / 0.6)',
      },
      backgroundImage: {
        'accent-gradient': 'linear-gradient(135deg, rgb(var(--c-accent)) 0%, rgb(var(--c-cyan)) 100%)',
      },
      keyframes: {
        'toast-in': { '0%': { opacity: 0, transform: 'translateY(6px)' }, '100%': { opacity: 1, transform: 'translateY(0)' } },
        reveal: { '0%': { opacity: 0, transform: 'translateY(12px)' }, '100%': { opacity: 1, transform: 'translateY(0)' } },
        marquee: { '0%': { transform: 'translateX(0)' }, '100%': { transform: 'translateX(-50%)' } },
        'ken-burns': { '0%': { transform: 'scale(1.04)' }, '100%': { transform: 'scale(1.12)' } },
      },
      animation: {
        'toast-in': 'toast-in 200ms ease-out',
        reveal: 'reveal 520ms cubic-bezier(0.16, 1, 0.3, 1) both',
        marquee: 'marquee 60s linear infinite',
        'ken-burns': 'ken-burns 24s ease-out alternate infinite',
      },
    },
  },
  plugins: [],
};
