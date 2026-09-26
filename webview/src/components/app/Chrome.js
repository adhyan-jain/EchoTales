import React, { useEffect, useState } from 'react';
import { Link } from 'react-router-dom';
import { Moon, Sun } from 'lucide-react';
import { applyTheme, getStoredTheme } from '../../theme';

/** Wordmark only: set in the reading serif, the way a book's title would be. */
export function Logo({ to = '/', className = '' }) {
  return (
    <Link to={to} className={`inline-flex items-baseline ${className}`} aria-label="EchoTales home">
      <span className="font-display text-xl font-semibold tracking-tight text-text">
        Echo<span className="italic text-accent">Tales</span>
      </span>
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
          <div className="text-sm text-muted">{eyebrow}</div>
        )}
        <h1 className="mt-1 font-display text-4xl font-medium tracking-tight text-text sm:text-5xl">{title}</h1>
        {description && <p className="mt-2 max-w-2xl text-sm text-muted">{description}</p>}
      </div>
      {actions && <div className="flex shrink-0 flex-wrap items-center gap-2">{actions}</div>}
    </header>
  );
}

/** One figure in a ledger row: label, number, note. No box, no icon. */
export function StatCard({ label, value, hint, tone = 'default' }) {
  const colour = tone === 'warn' ? 'text-warning' : 'text-text';
  return (
    <div className="px-1 py-5 lg:px-6 lg:first:pl-0">
      <div className="text-sm text-muted">{label}</div>
      <div className={`mt-1 font-display text-4xl font-medium tabular-nums ${colour}`}>{value}</div>
      {hint && <div className="mt-1 text-xs text-muted">{hint}</div>}
    </div>
  );
}

/** Full-page centred message for loading and connection errors. */
export function CenterMessage({ title, children }) {
  return (
    <div className="flex min-h-[60vh] flex-col items-center justify-center gap-2 px-6 text-center">
      {title && <h1 className="font-display text-2xl font-medium text-text">{title}</h1>}
      <div className="max-w-md text-sm text-muted">{children}</div>
    </div>
  );
}

/**
 * A project page that could not load. A project that does not exist (404) is
 * a dead end the user can leave -- the raw server text used to be all they
 * got -- so it links back to the library; other failures offer a retry.
 */
export function ProjectProblem({ error, status, onRetry, subject = 'this project' }) {
  const missing = status === 404;
  return (
    <CenterMessage title={missing ? 'Project not found' : `Couldn’t load ${subject}`}>
      <p>{missing ? 'This server has no project with that name. It may have been renamed or removed.' : error}</p>
      <div className="mt-4 flex justify-center gap-3">
        <Link to="/projects" className="rounded-xl border border-border px-4 py-2 text-sm font-medium text-text hover:border-accent/60">
          All projects
        </Link>
        {!missing && onRetry && (
          <button type="button" onClick={onRetry} className="rounded-lg bg-primary px-4 py-2 text-sm font-semibold text-on-primary hover:bg-primary-2">
            Try again
          </button>
        )}
      </div>
    </CenterMessage>
  );
}
