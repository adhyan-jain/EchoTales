import React from 'react';
import { useNavigate, useParams, useSearchParams } from 'react-router-dom';
import { Clapperboard, FolderOpen, DollarSign, Palette, FileText, BookCheck } from 'lucide-react';
import CharacterDashboard from '../../components/CharacterDashboard';
import GenerationWorkspace from '../../components/GenerationWorkspace';
import OutputLibrary from '../../components/OutputLibrary';
import CostMeterWidget from '../../components/CostMeterWidget';
import AssetStudio from '../../components/AssetStudio';
import ScreenplayEditor from '../../components/ScreenplayEditor';
import BibleReview from '../../components/BibleReview';
import ProjectHome from '../../components/ProjectHome';
import VisualStyleSetting from '../../components/VisualStyleSetting';
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
  { key: 'screenplay', label: 'Screenplay', icon: FileText },
  { key: 'assets', label: 'Asset Studio', icon: Palette },
  { key: 'bible', label: 'Canon review', icon: BookCheck },
  // Shot QA is hidden until the shot routes call the keyframe engine with measured checks (product plan step 4).
  { key: 'cost', label: 'Cost Meter', icon: DollarSign },
  { key: 'library', label: 'Library', icon: FolderOpen },
];

const STUDIO_INFO = {
  generate: { title: 'Generate', description: 'Queue a render for a chapter, a preview or the full chapter, and follow its progress.' },
  screenplay: { title: 'Screenplay Editor', description: 'Rule-enforced shot list, camera pacing, axis tracking, and performance cues.' },
  assets: { title: 'Asset Studio', description: 'Approve 3-view character turnarounds, expression sheets, and master location plates.' },
  bible: { title: 'Canon review', description: 'Check the lines the reader was least sure of, inspect each character over time, and lock the canon.' },
  qa: { title: 'Keyframe QA Gate', description: '4-Check automated QA gate, face and background matching, and candidate locking.' },
  cost: { title: 'Pre-Render Cost Meter', description: 'RunPod serverless GPU and open-model token itemized budget.' },
  library: { title: 'Output library', description: 'Every video, audio clip and panel rendered for this book.' },
};

export function Studio() {
  const { novelId } = useProject();
  const [params, setParams] = useSearchParams();
  const tab = params.get('tab') || 'generate';
  const info = STUDIO_INFO[tab] || STUDIO_INFO.generate;

  return (
    <div className="mx-auto w-full max-w-6xl px-4 py-10 sm:px-8">
      <PageHeader
        eyebrow="Studio"
        title={info.title}
        description={info.description}
      />
      <div role="group" aria-label="Studio view" className="mb-8 inline-flex flex-wrap gap-1 rounded-2xl border border-border bg-surface p-1">
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
        {tab === 'library' && <OutputLibrary novelId={novelId} hideHeader />}
        {tab === 'generate' && <GenerationWorkspace novelId={novelId} hideHeader />}
        {tab === 'screenplay' && <ScreenplayEditor novelId={novelId} />}
        {tab === 'assets' && <AssetStudio novelId={novelId} />}
        {tab === 'bible' && <BibleReview novelId={novelId} />}
        {tab === 'cost' && <CostMeterWidget novelId={novelId} />}
      </div>
    </div>
  );
}

export function Settings() {
  const { novelId, refreshProjects, projects } = useProject();
  const navigate = useNavigate();
  const project = (projects || []).find((p) => p.id === novelId);
  return (
    <div className="mx-auto w-full max-w-4xl px-4 py-10 sm:px-8">
      <PageHeader eyebrow="Settings" title="Project settings" description="Source, ingestion status and appearance." />
      <div className="space-y-8">
        <section className="rounded-3xl border border-border bg-surface p-6">
          <h2 className="font-display text-lg font-bold tracking-tight">Source &amp; pipeline</h2>
          <ProjectHome novelId={novelId} hideHeader onChanged={refreshProjects} onNewProject={() => navigate('/projects/new')} />
        </section>
        <VisualStyleSetting novelId={novelId} project={project} onChanged={refreshProjects} />
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
