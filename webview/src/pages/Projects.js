import React, { useEffect, useState } from 'react';
import { Link } from 'react-router-dom';
import { BookOpen, CircleAlert, CircleCheck, Clock, FlaskConical, Plus } from 'lucide-react';
import { api } from '../api';
import { Logo, PageHeader, ThemeToggle } from '../components/app/Chrome';
import { pickPanels, thumbUrl } from '../lib/media';
import { describeError } from '../lib/errors';

/** Top bar shared by the account-level pages (library, new project). */
export function AccountShell({ children }) {
  return (
    <div className="min-h-screen bg-bg text-text">
      <header className="glass sticky top-0 z-40 border-b border-border/60">
        <div className="mx-auto flex h-16 max-w-7xl items-center gap-4 px-4 sm:px-6">
          <Logo to="/projects" />
          <div className="ml-auto flex items-center gap-2">
            <Link
              to="/research"
              className="inline-flex h-9 items-center gap-1.5 rounded-xl border border-border px-3 text-sm text-muted transition-colors hover:border-accent/60 hover:text-text"
            >
              <FlaskConical className="h-4 w-4" aria-hidden="true" /> Research
            </Link>
            <ThemeToggle />
          </div>
        </div>
      </header>
      <main className="mx-auto max-w-7xl px-4 py-10 sm:px-6">{children}</main>
    </div>
  );
}

function statusOf(p) {
  if (p.ingested) return { label: `${p.chapter_count} chapters`, tone: 'text-success', icon: CircleCheck };
  if (p.source_uploaded) return { label: 'Ready to ingest', tone: 'text-warning', icon: Clock };
  return { label: 'No source yet', tone: 'text-muted', icon: CircleAlert };
}

function ProjectCard({ project }) {
  const [cover, setCover] = useState(null);
  const [failed, setFailed] = useState(false);
  useEffect(() => {
    let alive = true;
    api
      .listOutput(project.id)
      .then((out) => {
        const [first] = pickPanels(out, 1);
        if (alive && first) setCover(thumbUrl(project.id, first, 480));
      })
      .catch(() => {});
    return () => {
      alive = false;
    };
  }, [project.id]);
  const s = statusOf(project);
  const StatusIcon = s.icon;

  return (
    <Link
      to={`/p/${encodeURIComponent(project.id)}`}
      className="group relative flex aspect-[4/5] flex-col justify-end overflow-hidden rounded-3xl border border-border bg-surface transition-[border-color,transform] duration-200 hover:-translate-y-0.5 hover:border-accent/60"
    >
      {cover && !failed ? (
        <img
          src={cover}
          alt=""
          loading="lazy"
          onError={() => setFailed(true)}
          className="absolute inset-0 h-full w-full object-cover opacity-70 transition-[opacity,transform] duration-500 group-hover:scale-105 group-hover:opacity-90"
        />
      ) : (
        <div className="hero-glow absolute inset-0" aria-hidden="true" />
      )}
      <div className="absolute inset-0 bg-gradient-to-t from-black via-black/60 to-transparent" aria-hidden="true" />
      <div className="relative p-6">
        <span className="inline-flex items-center rounded-full border border-white/15 bg-black/40 px-2.5 py-0.5 text-xs font-medium capitalize text-white/80 backdrop-blur">
          {(project.content_type || 'novel').replace(/_/g, ' ')}
        </span>
        <h2 className="mt-3 font-display text-2xl font-bold tracking-tight text-white">{project.title || project.id}</h2>
        <div className={`mt-2 inline-flex items-center gap-1.5 text-sm ${s.tone}`}>
          <StatusIcon className="h-4 w-4" aria-hidden="true" />
          <span className="text-white/80">{s.label}</span>
        </div>
      </div>
    </Link>
  );
}

export default function Projects() {
  const [projects, setProjects] = useState(null);
  const [error, setError] = useState(null);

  useEffect(() => {
    let alive = true;
    api
      .listProjects()
      .then((list) => alive && setProjects(list || []))
      .catch((e) => alive && setError(describeError(e, 'Could not load projects.')));
    return () => {
      alive = false;
    };
  }, []);

  return (
    <AccountShell>
      <PageHeader
        eyebrow="Library"
        title="Your projects"
        description="Each project is one book: its cast, its chapters, and everything generated from them."
        actions={
          <Link
            to="/projects/new"
            className="inline-flex h-10 items-center gap-2 rounded-xl bg-primary px-4 text-sm font-semibold text-white shadow-glow transition-colors hover:bg-primary-2"
          >
            <Plus className="h-4 w-4" aria-hidden="true" /> New project
          </Link>
        }
      />

      {error && (
        <div className="rounded-2xl border border-danger/40 bg-danger/10 px-4 py-3 text-sm text-danger" role="alert">
          {error}
        </div>
      )}

      {!projects && !error && (
        <div className="grid gap-5 sm:grid-cols-2 lg:grid-cols-4" aria-busy="true">
          {Array.from({ length: 4 }).map((_, i) => (
            <div key={i} className="aspect-[4/5] animate-pulse rounded-3xl border border-border bg-surface" />
          ))}
        </div>
      )}

      {projects && (
        <div className="grid gap-5 sm:grid-cols-2 lg:grid-cols-4">
          {projects.map((p) => (
            <ProjectCard key={p.id} project={p} />
          ))}
          <Link
            to="/projects/new"
            className="group flex aspect-[4/5] flex-col items-center justify-center gap-3 rounded-3xl border border-dashed border-border text-muted transition-colors hover:border-accent/60 hover:text-text"
          >
            <span className="flex h-12 w-12 items-center justify-center rounded-2xl bg-surface2 transition-colors group-hover:bg-primary group-hover:text-white">
              <Plus className="h-5 w-5" aria-hidden="true" />
            </span>
            <span className="font-medium">New project</span>
            <span className="flex items-center gap-1.5 text-xs">
              <BookOpen className="h-3.5 w-3.5" aria-hidden="true" /> Start from an EPUB
            </span>
          </Link>
        </div>
      )}
    </AccountShell>
  );
}
