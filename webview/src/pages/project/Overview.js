import React, { useEffect, useMemo, useState } from 'react';
import { Link } from 'react-router-dom';
import { ArrowRight, BookOpen, CircleCheck, CircleDashed, Clapperboard, Hash } from 'lucide-react';
import { api } from '../../api';
import { ProjectProblem, StatCard } from '../../components/app/Chrome';
import { useNovelData } from '../../lib/ProjectContext';
import { countKind, pickPanels, thumbUrl } from '../../lib/media';

const pct = (x) => (typeof x === 'number' ? `${Math.round(x * 100)}%` : '—');
const num = (x) => (typeof x === 'number' ? new Intl.NumberFormat().format(x) : '—');

/**
 * Project home: where the book stands and where to go next. Numbers are the
 * pipeline's own counts from the novel payload -- how many mentions were
 * linked to a character is a coverage figure, not an accuracy claim, and is
 * labelled that way.
 */
export default function Overview() {
  const { novelId, novel, error, errorStatus, refetch, projects } = useNovelData();
  const [output, setOutput] = useState(null);
  const project = (projects || []).find((p) => p.id === novelId) || null;

  useEffect(() => {
    let alive = true;
    setOutput(null);
    api
      .listOutput(novelId)
      .then((o) => alive && setOutput(o))
      .catch(() => alive && setOutput({ kinds: {} }));
    return () => {
      alive = false;
    };
  }, [novelId]);

  const panels = useMemo(() => pickPanels(output, 7), [output]);
  const cast = useMemo(
    () =>
      ((novel && novel.entities) || [])
        .filter((e) => e.is_person !== false)
        .slice()
        .sort((a, b) => b.count - a.count)
        .slice(0, 8),
    [novel]
  );

  if (error) return <ProjectProblem error={error} status={errorStatus} onRetry={refetch} />;

  const s = (novel && novel.stats) || {};
  const title = (project && project.title) || (novel && novel.label) || novelId;

  const media = [
    [countKind(output, 'panels', /\.(png|jpe?g|webp)$/i), 'panel files'],
    [countKind(output, 'audio', /\.(wav|mp3|ogg|flac)$/i), 'audio clips'],
    [countKind(output, 'video', /\.(mp4|webm|mov)$/i), 'videos'],
  ];

  return (
    <div className="pb-20">
      <header className="mx-auto grid max-w-6xl items-end gap-8 px-4 pb-10 pt-12 sm:px-8 lg:grid-cols-[1fr_auto]">
        <div className="min-w-0">
          <p className="text-sm text-muted">Project</p>
          <h1 className="mt-1 font-display text-5xl font-medium tracking-tight sm:text-6xl">{title}</h1>
          <p className="mt-4 max-w-xl text-muted">
            {novel
              ? `${num(s.chapters || 0)} chapters, ${num(s.entities || 0)} characters and places tracked across the book.`
              : 'Loading the book…'}
          </p>
          <div className="mt-6 flex flex-wrap gap-3">
            <Link to="read" className="inline-flex h-11 items-center gap-2 rounded-lg bg-primary px-5 text-sm font-semibold text-on-primary transition-colors hover:bg-primary-2">
              <BookOpen className="h-4 w-4" aria-hidden="true" /> Start reading
            </Link>
            <Link to="studio" className="inline-flex h-11 items-center gap-2 rounded-lg border border-border px-5 text-sm font-semibold text-text transition-colors hover:border-accent/60">
              <Clapperboard className="h-4 w-4" aria-hidden="true" /> Open studio
            </Link>
          </div>
        </div>
        {panels.length > 0 && (
          <div className="hidden gap-2 lg:flex" aria-hidden="true">
            {panels.slice(0, 3).map((p) => (
              <img key={p} src={thumbUrl(novelId, p, 320)} alt="" className="h-52 w-40 rounded-lg border border-border object-cover" />
            ))}
          </div>
        )}
      </header>

      <div className="mx-auto max-w-6xl space-y-12 px-4 sm:px-8">
        <section aria-label="Book at a glance" className="grid grid-cols-2 divide-border border-y border-border lg:grid-cols-4 lg:divide-x">
          <StatCard label="Chapters" value={num(s.chapters)} hint="in this volume" />
          <StatCard
            label="Characters & entities"
            value={num(s.entities)}
            hint={s.singleton_rate != null ? `${pct(s.singleton_rate)} appear once` : null}
          />
          <StatCard
            label="Mentions linked"
            value={pct(s.resolution_rate)}
            hint={`${num(s.resolved)} of ${num(s.mentions)} linked to a character`}
          />
          <StatCard
            label="Dialogue attributed"
            value={pct(s.attribution_rate)}
            hint={s.dialogue_anonymous ? `${num(s.dialogue_anonymous)} lines in unknown-speaker slots` : null}
            tone={s.attribution_rate != null && s.attribution_rate < 0.6 ? 'warn' : 'default'}
          />
        </section>

        <div className="grid gap-12 lg:grid-cols-5">
          <section className="lg:col-span-2">
            <div className="flex items-baseline justify-between border-b border-border pb-3">
              <h2 className="font-display text-2xl font-medium">Main cast</h2>
              <Link to="characters" className="inline-flex items-center gap-1 text-sm text-accent hover:underline">
                All characters <ArrowRight className="h-3.5 w-3.5" aria-hidden="true" />
              </Link>
            </div>
            <ol className="divide-y divide-border/60">
              {cast.map((e, i) => (
                <li key={e.id}>
                  <Link to={`read?focus=${encodeURIComponent(e.id)}`} className="group flex items-center gap-3 py-2.5">
                    <span className="w-5 text-right font-mono text-xs tabular-nums text-muted">{i + 1}</span>
                    <span className="h-2.5 w-2.5 shrink-0 rounded-full" style={{ background: e.colour }} aria-hidden="true" />
                    <span className="min-w-0 flex-1 truncate text-sm font-medium group-hover:text-accent">{e.label}</span>
                    <span className="font-mono text-xs tabular-nums text-muted">{num(e.count)}</span>
                  </Link>
                </li>
              ))}
              {!cast.length && <li className="py-3 text-sm text-muted">{novel ? 'No characters yet.' : 'Loading cast…'}</li>}
            </ol>
          </section>

          <section className="lg:col-span-3">
            <div className="flex items-baseline justify-between border-b border-border pb-3">
              <h2 className="font-display text-2xl font-medium">Latest renders</h2>
              <Link to="studio?tab=library" className="inline-flex items-center gap-1 text-sm text-accent hover:underline">
                Output library <ArrowRight className="h-3.5 w-3.5" aria-hidden="true" />
              </Link>
            </div>
            {panels.length > 1 ? (
              <div className="mt-4 grid grid-cols-3 gap-2">
                {panels.slice(1, 7).map((p) => (
                  <img key={p} src={thumbUrl(novelId, p, 320)} alt="Generated panel" loading="lazy" className="aspect-[3/4] w-full rounded-lg border border-border bg-surface2 object-cover" />
                ))}
              </div>
            ) : (
              <p className="mt-4 text-sm text-muted">No panels rendered yet. Generate some in the Studio.</p>
            )}
            <p className="mt-4 font-mono text-xs tabular-nums text-muted">
              {media.map(([n, label]) => `${new Intl.NumberFormat().format(n || 0)} ${label}`).join('  ·  ')}
            </p>
          </section>
        </div>

        <section>
          <h2 className="border-b border-border pb-3 font-display text-2xl font-medium">Pipeline</h2>
          <ol className="grid gap-x-8 sm:grid-cols-2 lg:grid-cols-4">
            <Step done={project ? project.source_uploaded : !!novel} label="Source uploaded" />
            <Step
              done={project ? project.ingested : !!novel}
              label="Chapters ingested"
              detail={project && project.ingested ? `${project.chapter_count} chapters` : null}
            />
            <Step done={(s.entities || 0) > 0} label="Cast resolved" detail={s.entities ? `${num(s.entities)} entities` : null} />
            <Step done={panels.length > 0} label="Media generated" detail={panels.length ? 'panels on disk' : 'not yet'} />
          </ol>
          {project && project.last_job && (
            <p className="mt-2 flex items-center gap-2 text-sm text-muted">
              <Hash className="h-4 w-4" aria-hidden="true" /> Last job: <span className="font-mono text-text">{project.last_job.kind}</span> ·{' '}
              {project.last_job.status}
            </p>
          )}
        </section>
      </div>
    </div>
  );
}

function Step({ done, label, detail }) {
  const Icon = done ? CircleCheck : CircleDashed;
  return (
    <li className="flex items-start gap-3 border-b border-border/60 py-3">
      <Icon className={`mt-0.5 h-4 w-4 shrink-0 ${done ? 'text-success' : 'text-muted'}`} aria-hidden="true" />
      <div>
        <div className="text-sm font-medium">{label}</div>
        {detail && <div className="text-xs text-muted">{detail}</div>}
      </div>
    </li>
  );
}
