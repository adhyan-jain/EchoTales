import React, { useEffect, useMemo, useState } from 'react';
import { Link } from 'react-router-dom';
import {
  ArrowRight,
  AudioLines,
  BookOpen,
  CircleCheck,
  CircleDashed,
  Clapperboard,
  Film,
  Hash,
  Images,
  Link2,
  MessageSquareQuote,
  Users,
} from 'lucide-react';
import { api } from '../../api';
import { CenterMessage, StatCard } from '../../components/app/Chrome';
import { useProject } from '../../lib/ProjectContext';
import { countKind, fileUrl, pickPanels } from '../../lib/media';

const pct = (x) => (typeof x === 'number' ? `${Math.round(x * 100)}%` : '—');
const num = (x) => (typeof x === 'number' ? new Intl.NumberFormat().format(x) : '—');

/**
 * Project home: where the book stands and where to go next. Numbers are the
 * pipeline's own counts from the novel payload -- how many mentions were
 * linked to a character is a coverage figure, not an accuracy claim, and is
 * labelled that way.
 */
export default function Overview() {
  const { novelId, novel, error } = useProject();
  const [output, setOutput] = useState(null);
  const [project, setProject] = useState(null);

  useEffect(() => {
    let alive = true;
    setOutput(null);
    setProject(null);
    api
      .listOutput(novelId)
      .then((o) => alive && setOutput(o))
      .catch(() => alive && setOutput({ kinds: {} }));
    api
      .listProjects()
      .then((l) => alive && setProject((l || []).find((p) => p.id === novelId) || null))
      .catch(() => {});
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

  if (error) return <CenterMessage title="Couldn’t load this project">{error}</CenterMessage>;

  const s = (novel && novel.stats) || {};
  const title = (project && project.title) || (novel && novel.label) || novelId;
  const maxCount = cast.length ? cast[0].count : 1;

  return (
    <div className="pb-16">
      <section className="relative isolate overflow-hidden border-b border-border">
        {panels[0] ? (
          <img src={fileUrl(novelId, panels[0])} alt="" className="absolute inset-0 -z-10 h-full w-full object-cover opacity-40 blur-[2px]" />
        ) : null}
        <div className="absolute inset-0 -z-10 bg-gradient-to-r from-bg via-bg/90 to-bg/40" aria-hidden="true" />
        <div className="hero-glow absolute inset-0 -z-10" aria-hidden="true" />
        <div className="mx-auto max-w-6xl px-4 py-14 sm:px-8">
          <div className="text-xs font-semibold uppercase tracking-[0.14em] text-accent">Project overview</div>
          <h1 className="mt-2 font-display text-4xl font-extrabold tracking-tight sm:text-6xl">{title}</h1>
          <p className="mt-3 max-w-xl text-muted">
            {s.chapters
              ? `${num(s.chapters)} chapters, ${num(s.entities)} characters and places tracked across the book.`
              : 'Loading the book…'}
          </p>
          <div className="mt-7 flex flex-wrap gap-3">
            <Link to="read" className="inline-flex h-11 items-center gap-2 rounded-xl bg-primary px-5 text-sm font-semibold text-white shadow-glow transition-colors hover:bg-primary-2">
              <BookOpen className="h-4 w-4" aria-hidden="true" /> Start reading
            </Link>
            <Link to="studio" className="inline-flex h-11 items-center gap-2 rounded-xl border border-border bg-surface/70 px-5 text-sm font-semibold text-text backdrop-blur transition-colors hover:border-accent/60">
              <Clapperboard className="h-4 w-4" aria-hidden="true" /> Open studio
            </Link>
          </div>
        </div>
      </section>

      <div className="mx-auto max-w-6xl space-y-10 px-4 pt-10 sm:px-8">
        <section aria-label="Book at a glance" className="grid grid-cols-2 gap-4 lg:grid-cols-4">
          <StatCard icon={BookOpen} label="Chapters" value={num(s.chapters)} hint="in this volume" />
          <StatCard
            icon={Users}
            label="Characters & entities"
            value={num(s.entities)}
            hint={s.singleton_rate != null ? `${pct(s.singleton_rate)} appear once` : null}
          />
          <StatCard
            icon={Link2}
            label="Mentions linked"
            value={pct(s.resolution_rate)}
            hint={`${num(s.resolved)} of ${num(s.mentions)} linked to a character`}
            tone="good"
          />
          <StatCard
            icon={MessageSquareQuote}
            label="Dialogue attributed"
            value={pct(s.attribution_rate)}
            hint={s.dialogue_anonymous ? `${num(s.dialogue_anonymous)} lines in unknown-speaker slots` : null}
            tone={s.attribution_rate != null && s.attribution_rate < 0.6 ? 'warn' : 'default'}
          />
        </section>

        <div className="grid gap-6 lg:grid-cols-5">
          <section className="rounded-3xl border border-border bg-surface p-6 lg:col-span-2">
            <div className="flex items-center justify-between">
              <h2 className="font-display text-lg font-bold tracking-tight">Main cast</h2>
              <Link to="cast" className="inline-flex items-center gap-1 text-sm text-accent hover:underline">
                All characters <ArrowRight className="h-3.5 w-3.5" aria-hidden="true" />
              </Link>
            </div>
            <ul className="mt-5 space-y-3">
              {cast.map((e) => (
                <li key={e.id}>
                  <Link to={`read?focus=${encodeURIComponent(e.id)}`} className="group -m-2 block rounded-xl p-2 transition-colors hover:bg-surface2">
                    <div className="flex items-center gap-3">
                      <span
                        className="flex h-8 w-8 shrink-0 items-center justify-center rounded-full text-xs font-bold text-black"
                        style={{ background: e.colour }}
                        aria-hidden="true"
                      >
                        {e.label.slice(0, 1)}
                      </span>
                      <span className="min-w-0 flex-1 truncate text-sm font-medium group-hover:text-accent">{e.label}</span>
                      <span className="text-xs tabular-nums text-muted">{num(e.count)}</span>
                    </div>
                    <div className="ml-11 mt-1.5 h-1 overflow-hidden rounded-full bg-surface2">
                      <div className="h-full rounded-full" style={{ width: `${Math.max(4, (e.count / maxCount) * 100)}%`, background: e.colour }} />
                    </div>
                  </Link>
                </li>
              ))}
              {!cast.length && <li className="text-sm text-muted">Loading cast…</li>}
            </ul>
          </section>

          <section className="rounded-3xl border border-border bg-surface p-6 lg:col-span-3">
            <div className="flex items-center justify-between">
              <h2 className="font-display text-lg font-bold tracking-tight">Latest renders</h2>
              <Link to="studio?tab=library" className="inline-flex items-center gap-1 text-sm text-accent hover:underline">
                Output library <ArrowRight className="h-3.5 w-3.5" aria-hidden="true" />
              </Link>
            </div>
            {panels.length > 1 ? (
              <div className="mt-5 grid grid-cols-3 gap-2">
                {panels.slice(1, 7).map((p) => (
                  <div key={p} className="aspect-[3/4] overflow-hidden rounded-xl border border-border bg-surface2">
                    <img src={fileUrl(novelId, p)} alt="Generated panel" loading="lazy" className="h-full w-full object-cover transition-transform duration-500 hover:scale-105" />
                  </div>
                ))}
              </div>
            ) : (
              <p className="mt-5 text-sm text-muted">No panels rendered yet. Generate some in the Studio.</p>
            )}
            <div className="mt-5 grid grid-cols-3 gap-3 text-sm">
              <MediaCount icon={Images} label="Panel files" value={countKind(output, 'panels', /\.(png|jpe?g|webp)$/i)} />
              <MediaCount icon={AudioLines} label="Audio clips" value={countKind(output, 'audio', /\.(wav|mp3|ogg|flac)$/i)} />
              <MediaCount icon={Film} label="Videos" value={countKind(output, 'video', /\.(mp4|webm|mov)$/i)} />
            </div>
          </section>
        </div>

        <section className="rounded-3xl border border-border bg-surface p-6">
          <h2 className="font-display text-lg font-bold tracking-tight">Pipeline</h2>
          <ol className="mt-5 grid gap-3 sm:grid-cols-4">
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
            <p className="mt-4 flex items-center gap-2 text-sm text-muted">
              <Hash className="h-4 w-4" aria-hidden="true" /> Last job: <span className="font-mono text-text">{project.last_job.kind}</span> ·{' '}
              {project.last_job.status}
            </p>
          )}
        </section>
      </div>
    </div>
  );
}

function MediaCount({ icon: Icon, label, value }) {
  return (
    <div className="rounded-xl bg-surface2 px-3 py-2.5">
      <div className="flex items-center gap-1.5 text-xs text-muted">
        <Icon className="h-3.5 w-3.5" aria-hidden="true" /> {label}
      </div>
      <div className="mt-0.5 font-display text-lg font-bold tabular-nums">{new Intl.NumberFormat().format(value || 0)}</div>
    </div>
  );
}

function Step({ done, label, detail }) {
  const Icon = done ? CircleCheck : CircleDashed;
  return (
    <li className={`flex items-start gap-3 rounded-2xl border px-4 py-3 ${done ? 'border-success/30 bg-success/5' : 'border-border'}`}>
      <Icon className={`mt-0.5 h-5 w-5 shrink-0 ${done ? 'text-success' : 'text-muted'}`} aria-hidden="true" />
      <div>
        <div className="text-sm font-medium">{label}</div>
        {detail && <div className="text-xs text-muted">{detail}</div>}
      </div>
    </li>
  );
}
