import React from 'react';
import { useNavigate, useParams, useSearchParams } from 'react-router-dom';
import { Clapperboard, FolderOpen } from 'lucide-react';
import CharacterDashboard from '../../components/CharacterDashboard';
import GenerationWorkspace from '../../components/GenerationWorkspace';
import OutputLibrary from '../../components/OutputLibrary';
import ProjectHome from '../../components/ProjectHome';
import { PageHeader, ThemeToggle } from '../../components/app/Chrome';
import { useProject } from '../../lib/ProjectContext';

/* Thin routed wrappers around the existing feature components. The
   components own their data fetching and error states; these pages own the
   URL (which character is open, which studio tab is showing) and the
   consistent page header. */

export function Cast() {
  const { novelId } = useProject();
  const { selfId } = useParams();
  const navigate = useNavigate();
  return (
    <CharacterDashboard
      novelId={novelId}
      selectedId={selfId || null}
      onSelect={(id) => navigate(id ? encodeURIComponent(id) : '..', { relative: 'path' })}
    />
  );
}

const STUDIO_TABS = [
  { key: 'generate', label: 'Generate', icon: Clapperboard },
  { key: 'library', label: 'Library', icon: FolderOpen },
];

export function Studio() {
  const { novelId } = useProject();
  const [params, setParams] = useSearchParams();
  const tab = params.get('tab') === 'library' ? 'library' : 'generate';
  return (
    <div className="mx-auto w-full max-w-6xl px-4 py-10 sm:px-8">
      <PageHeader
        eyebrow="Studio"
        title={tab === 'library' ? 'Output library' : 'Generate'}
        description={
          tab === 'library'
            ? 'Every video, audio clip and panel rendered for this book.'
            : 'Queue a placeholder render for a chapter and follow its progress.'
        }
      />
      <div role="group" aria-label="Studio view" className="mb-8 inline-flex rounded-2xl border border-border bg-surface p-1">
        {STUDIO_TABS.map(({ key, label, icon: Icon }) => (
          <button
            key={key}
            type="button"
            aria-pressed={tab === key}
            onClick={() => setParams(key === 'generate' ? {} : { tab: key }, { replace: true })}
            className={
              'inline-flex items-center gap-2 rounded-xl px-4 py-2 text-sm font-medium transition-colors ' +
              (tab === key ? 'bg-primary text-white shadow-glow' : 'text-muted hover:text-text')
            }
          >
            <Icon className="h-4 w-4" aria-hidden="true" /> {label}
          </button>
        ))}
      </div>
      <div>
        {tab === 'library' ? <OutputLibrary novelId={novelId} hideHeader /> : <GenerationWorkspace novelId={novelId} hideHeader />}
      </div>
    </div>
  );
}

export function Settings() {
  const { novelId, refreshProjects } = useProject();
  const navigate = useNavigate();
  return (
    <div className="mx-auto w-full max-w-4xl px-4 py-10 sm:px-8">
      <PageHeader eyebrow="Settings" title="Project settings" description="Source, ingestion status and appearance." />
      <div className="space-y-8">
        <section className="rounded-3xl border border-border bg-surface p-6">
          <h2 className="font-display text-lg font-bold tracking-tight">Source &amp; pipeline</h2>
          <ProjectHome novelId={novelId} hideHeader onChanged={refreshProjects} onNewProject={() => navigate('/projects/new')} />
        </section>
        <section className="flex items-center justify-between gap-4 rounded-3xl border border-border bg-surface p-6">
          <div>
            <h2 className="font-display text-lg font-bold tracking-tight">Appearance</h2>
            <p className="mt-1 text-sm text-muted">Dark is the default; the light theme suits long reading sessions in daylight.</p>
          </div>
          <ThemeToggle />
        </section>
        <section className="rounded-3xl border border-border bg-surface p-6">
          <h2 className="font-display text-lg font-bold tracking-tight">Project id</h2>
          <p className="mt-2 font-mono text-sm text-muted">{novelId}</p>
        </section>
      </div>
    </div>
  );
}
