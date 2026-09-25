import React, { useEffect, useState } from 'react';
import { Link } from 'react-router-dom';
import { Moon, Sun } from 'lucide-react';
import { applyTheme, getStoredTheme } from '../../theme';

/** Wordmark + a sound-wave mark (story in, voice out). Pure SVG, no asset. */
export function Logo({ to = '/', className = '' }) {
  return (
    <Link to={to} className={`group inline-flex items-center gap-2.5 ${className}`} aria-label="EchoTales home">
      <span className="relative flex h-8 w-8 items-center justify-center rounded-xl bg-accent-gradient shadow-glow">
        <svg viewBox="0 0 24 24" className="h-4 w-4 text-black" fill="none" stroke="currentColor" strokeWidth="2.4" strokeLinecap="round" aria-hidden="true">
          <path d="M4 10v4M8 7v10M12 4v16M16 8v8M20 11v2" />
        </svg>
      </span>
      <span className="font-display text-lg font-bold tracking-tight text-text">EchoTales</span>
    </Link>
  );
}

export function ThemeToggle({ className = '' }) {
  const [theme, setTheme] = useState(() => getStoredTheme() || 'dark');
  useEffect(() => {
    const onChange = (e) => setTheme(e.detail);
    window.addEventListener('echotales:theme', onChange);
    return () => window.removeEventListener('echotales:theme', onChange);
  }, []);
  const next = theme === 'dark' ? 'light' : 'dark';
  return (
    <button
      type="button"
      onClick={() => applyTheme(next)}
      aria-label={`Switch to ${next} theme`}
      title={`Switch to ${next} theme`}
      className={`inline-flex h-9 w-9 items-center justify-center rounded-xl border border-border text-muted transition-colors hover:border-accent/60 hover:text-text ${className}`}
    >
      {theme === 'dark' ? <Sun className="h-4 w-4" aria-hidden="true" /> : <Moon className="h-4 w-4" aria-hidden="true" />}
    </button>
  );
}

/** Consistent top-of-page header for every workspace page. */
export function PageHeader({ eyebrow, title, description, actions }) {
  return (
    <header className="flex flex-wrap items-end justify-between gap-4 pb-8">
      <div className="min-w-0">
        {eyebrow && (
          <div className="text-xs font-semibold uppercase tracking-[0.14em] text-accent">{eyebrow}</div>
        )}
        <h1 className="mt-1.5 font-display text-3xl font-bold tracking-tight text-text sm:text-4xl">{title}</h1>
        {description && <p className="mt-2 max-w-2xl text-sm text-muted">{description}</p>}
      </div>
      {actions && <div className="flex shrink-0 flex-wrap items-center gap-2">{actions}</div>}
    </header>
  );
}

/** A single KPI tile. `hint` is the small line under the number. */
export function StatCard({ icon: Icon, label, value, hint, tone = 'default' }) {
  const toneRing = tone === 'warn' ? 'text-warning' : tone === 'good' ? 'text-success' : 'text-accent';
  return (
    <div className="rounded-2xl border border-border bg-surface p-5 transition-colors hover:border-accent/40">
      <div className="flex items-center justify-between">
        <span className="text-sm text-muted">{label}</span>
        {Icon && <Icon className={`h-4 w-4 ${toneRing}`} aria-hidden="true" />}
      </div>
      <div className="mt-3 font-display text-3xl font-bold tracking-tight text-text tabular-nums">{value}</div>
      {hint && <div className="mt-1 text-xs text-muted">{hint}</div>}
    </div>
  );
}

/** Full-page centred message for loading and connection errors. */
export function CenterMessage({ title, children }) {
  return (
    <div className="flex min-h-[60vh] flex-col items-center justify-center gap-2 px-6 text-center">
      {title && <p className="font-display text-xl font-semibold text-text">{title}</p>}
      <div className="max-w-md text-sm text-muted">{children}</div>
    </div>
  );
}
