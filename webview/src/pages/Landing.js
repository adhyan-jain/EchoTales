import React, { useEffect, useState } from 'react';
import { Link } from 'react-router-dom';
import {
  ArrowRight,
  AudioLines,
  BookOpen,
  Check,
  Cpu,
  Images,
  Network,
  ShieldCheck,
  Sparkles,
  TrendingUp,
  Users,
} from 'lucide-react';
import { api } from '../api';
import { Logo, ThemeToggle } from '../components/app/Chrome';
import { pickPanels, pickReferenceSheets, thumbUrl } from '../lib/media';

/**
 * Public landing page. Imagery is the first project's own rendered panels
 * and reference sheets, fetched live -- no stock art, and nothing shown that
 * the pipeline did not actually produce. If the server is unreachable or
 * locked, every image slot falls back to a pure-CSS glow, so the page still
 * reads as finished rather than broken.
 *
 * Copy rules: describe what the product does; never claim it is the first
 * or only system of its kind; never quote an accuracy number here (those
 * live in docs/ with their reference-set caveats); and describe only
 * concepts already public on origin/master -- this file ships with the repo.
 */
function useShowcase() {
  const [data, setData] = useState({ novelId: null, label: '', panels: [], sheets: [], stats: null });
  useEffect(() => {
    let alive = true;
    api
      .listProjects()
      .then((projects) => {
        const first = (projects || []).find((p) => p.ingested) || (projects || [])[0];
        if (!first) return undefined;
        return api.listOutput(first.id).then((out) => {
          if (!alive) return;
          setData({
            novelId: first.id,
            label: first.title || first.id,
            panels: pickPanels(out, 18),
            sheets: pickReferenceSheets(out, 4),
            stats: { chapters: first.chapter_count },
          });
        });
      })
      .catch(() => {});
    return () => {
      alive = false;
    };
  }, []);
  return data;
}

function Img({ novelId, path, className = '', alt = '', width = 480 }) {
  const [failed, setFailed] = useState(false);
  if (!novelId || !path || failed) {
    return <div className={`hero-glow bg-surface2 ${className}`} aria-hidden="true" />;
  }
  return (
    <img
      src={thumbUrl(novelId, path, width)}
      alt={alt}
      loading="lazy"
      decoding="async"
      onError={() => setFailed(true)}
      className={`object-cover ${className}`}
    />
  );
}

const NAV = [
  { href: '#how', label: 'How it works' },
  { href: '#features', label: 'Features' },
  { href: '#showcase', label: 'Showcase' },
];

export default function Landing() {
  const { novelId, label, panels, sheets, stats } = useShowcase();
  const heroPanels = panels.slice(0, 6);
  const strip = panels.length ? [...panels, ...panels] : [];

  return (
    <div className="min-h-screen bg-bg text-text">
      <header className="glass fixed inset-x-0 top-0 z-50 border-b border-border/60">
        <nav className="mx-auto flex h-16 max-w-7xl items-center gap-6 px-4 sm:px-6" aria-label="Main">
          <Logo />
          <div className="ml-6 hidden items-center gap-1 md:flex">
            {NAV.map((n) => (
              <a key={n.href} href={n.href} className="rounded-lg px-3 py-1.5 text-sm text-muted transition-colors hover:text-text">
                {n.label}
              </a>
            ))}
          </div>
          <div className="ml-auto flex items-center gap-2">
            <ThemeToggle />
            <Link
              to="/projects"
              className="inline-flex h-9 items-center gap-1.5 rounded-xl bg-text px-4 text-sm font-semibold text-bg transition-opacity hover:opacity-90"
            >
              Open app <ArrowRight className="h-4 w-4" aria-hidden="true" />
            </Link>
          </div>
        </nav>
      </header>

      <main>
        {/* Hero: the project's own panels, dimmed behind the headline. */}
        <section className="relative isolate flex min-h-[100svh] items-end overflow-hidden pb-20 pt-32 sm:items-center sm:pb-0">
          <div className="absolute inset-0 -z-10 grid grid-cols-3 gap-1 opacity-60 sm:grid-cols-6" aria-hidden="true">
            {(heroPanels.length ? heroPanels : Array.from({ length: 6 })).map((p, i) => (
              <div key={i} className="relative overflow-hidden">
                <Img novelId={novelId} path={p} className="h-full w-full animate-ken-burns" />
              </div>
            ))}
          </div>
          <div className="absolute inset-0 -z-10 bg-gradient-to-t from-bg via-bg/85 to-bg/40" aria-hidden="true" />
          <div className="hero-glow absolute inset-0 -z-10" aria-hidden="true" />

          <div className="mx-auto w-full max-w-7xl px-4 sm:px-6">
            <div className="max-w-3xl animate-reveal">
              <div className="inline-flex items-center gap-2 rounded-full border border-border bg-surface/70 px-3 py-1 text-xs font-medium text-muted backdrop-blur">
                <Sparkles className="h-3.5 w-3.5 text-accent" aria-hidden="true" />
                Novel in. Audiobook and manga out.
              </div>
              <h1 className="mt-6 font-display text-5xl font-extrabold tracking-tight sm:text-7xl lg:text-8xl">
                <span className="block">A whole novel.</span>
                <span className="block">A cast you can hear.</span>
                <span className="text-gradient block pb-2">A world you can see.</span>
              </h1>
              <p className="mt-6 max-w-xl text-lg text-muted">
                EchoTales reads a whole novel, tracks its characters across the chapters, and generates a multi-voice
                audiobook and illustrated panels from it.
              </p>
              <div className="mt-8 flex flex-wrap items-center gap-3">
                <Link
                  to="/projects/new"
                  className="inline-flex h-12 items-center gap-2 rounded-xl bg-primary px-6 text-base font-semibold text-white shadow-glow transition-colors hover:bg-primary-2"
                >
                  Start a project <ArrowRight className="h-4 w-4" aria-hidden="true" />
                </Link>
                <Link
                  to="/projects"
                  className="inline-flex h-12 items-center gap-2 rounded-xl border border-border bg-surface/70 px-6 text-base font-semibold text-text backdrop-blur transition-colors hover:border-accent/60"
                >
                  Open your library
                </Link>
              </div>
              {stats && stats.chapters ? (
                <p className="mt-8 text-sm text-muted">
                  Now on this server: <span className="font-semibold text-text">{label}</span> ·{' '}
                  <span className="tabular-nums">{stats.chapters}</span> chapters processed
                </p>
              ) : null}
            </div>
          </div>
        </section>

        {strip.length > 0 && (
          <section aria-label="Recently generated panels" className="relative overflow-hidden border-y border-border py-6">
            <div className="flex w-max animate-marquee gap-4 hover:[animation-play-state:paused]">
              {strip.map((p, i) => (
                <div key={i} className="h-44 w-32 shrink-0 overflow-hidden rounded-xl border border-border sm:h-56 sm:w-40">
                  <Img novelId={novelId} path={p} className="h-full w-full" />
                </div>
              ))}
            </div>
            <div className="pointer-events-none absolute inset-y-0 left-0 w-24 bg-gradient-to-r from-bg" aria-hidden="true" />
            <div className="pointer-events-none absolute inset-y-0 right-0 w-24 bg-gradient-to-l from-bg" aria-hidden="true" />
          </section>
        )}

        <section id="how" className="mx-auto max-w-7xl scroll-mt-20 px-4 py-24 sm:px-6">
          <SectionIntro eyebrow="How it works" title="From EPUB to a living adaptation, in three passes." />
          <div className="mt-14 grid gap-4 md:grid-cols-3">
            {[
              {
                icon: BookOpen,
                step: '01',
                title: 'Read the whole book',
                body: 'Drop in an EPUB. Every chapter is sorted into narration, dialogue and inner monologue, so each kind of line can be voiced and drawn its own way.',
              },
              {
                icon: Network,
                step: '02',
                title: 'Track the cast',
                body: 'Names, titles and nicknames are linked to the characters they refer to across the whole volume, with a separate record for each body a character has.',
              },
              {
                icon: AudioLines,
                step: '03',
                title: 'Hear it. See it.',
                body: 'Each character gets a voice and a recorded look, so the audiobook and the panels are cast from the same character list.',
              },
            ].map(({ icon: Icon, step, title, body }) => (
              <div key={step} className="group relative overflow-hidden rounded-3xl border border-border bg-surface p-8 transition-colors hover:border-accent/50">
                <div className="flex items-center justify-between">
                  <span className="flex h-11 w-11 items-center justify-center rounded-2xl bg-accent/10 text-accent">
                    <Icon className="h-5 w-5" aria-hidden="true" />
                  </span>
                  <span className="font-mono text-sm text-muted">{step}</span>
                </div>
                <h3 className="mt-8 font-display text-2xl font-bold tracking-tight">{title}</h3>
                <p className="mt-3 text-muted">{body}</p>
                <div className="pointer-events-none absolute -bottom-24 -right-24 h-48 w-48 rounded-full bg-primary/20 opacity-0 blur-3xl transition-opacity group-hover:opacity-100" aria-hidden="true" />
              </div>
            ))}
          </div>
        </section>

        <section id="features" className="mx-auto max-w-7xl scroll-mt-20 px-4 pb-24 sm:px-6">
          <SectionIntro eyebrow="Features" title="Built for books too long to hold in your head." />
          <div className="mt-14 grid auto-rows-[minmax(220px,auto)] gap-4 md:grid-cols-6">
            <div className="relative overflow-hidden rounded-3xl border border-border bg-surface md:col-span-4 md:row-span-2">
              <div className="grid h-full grid-cols-2 gap-1 opacity-80 sm:grid-cols-4" aria-hidden="true">
                {(sheets.length ? sheets : Array.from({ length: 4 })).map((p, i) => (
                  <Img key={i} novelId={novelId} path={p} className="h-full min-h-[200px] w-full" />
                ))}
              </div>
              <div className="absolute inset-0 bg-gradient-to-t from-surface via-surface/70 to-transparent" aria-hidden="true" />
              <div className="absolute inset-x-0 bottom-0 p-8">
                <Users className="h-6 w-6 text-accent" aria-hidden="true" />
                <h3 className="mt-4 font-display text-3xl font-bold tracking-tight">A cast with a recorded look</h3>
                <p className="mt-2 max-w-lg text-muted">
                  Each character body gets a reference sheet and a set of recorded appearance traits, and those traits
                  are carried into the panel prompts instead of being reinvented scene by scene.
                </p>
              </div>
            </div>
            <Feature className="md:col-span-2" icon={AudioLines} title="A voice per character" body="Where the speaker can be identified, dialogue is cast to that character’s voice; unidentified speakers get their own distinct voice slots." />
            <Feature className="md:col-span-2" icon={Images} title="Panels per scene" body="Scene direction, cast and setting come from the story itself, not from a single-line prompt." />
            <Feature className="md:col-span-2" icon={ShieldCheck} title="Review, don't redo" body="Fix a wrong name or speaker in place. Corrections queue up, and you apply them to the book when you’re ready." />
            <Feature className="md:col-span-2" icon={Cpu} title="Local by default" body="Built to run on a consumer GPU with local models, so a manuscript stays on your machine unless you choose to connect a cloud model." />
            <Feature className="md:col-span-2" icon={TrendingUp} title="Remembers what it has confirmed" body="Names it has already resolved are reused across the book instead of being decided again chapter by chapter." />
          </div>
        </section>

        {panels.length > 6 && (
          <section id="showcase" className="mx-auto max-w-7xl scroll-mt-20 px-4 pb-24 sm:px-6">
            <SectionIntro eyebrow="Showcase" title={`Straight from ${label}.`} description="Panels from the most recent renders on this server." />
            <div className="mt-14 columns-2 gap-4 sm:columns-3 lg:columns-4">
              {panels.slice(6, 18).map((p) => (
                <div key={p} className="mb-4 break-inside-avoid overflow-hidden rounded-2xl border border-border">
                  <Img novelId={novelId} path={p} className="w-full" alt="Generated panel" />
                </div>
              ))}
            </div>
          </section>
        )}

        <section className="mx-auto max-w-7xl px-4 pb-24 sm:px-6">
          <div className="relative overflow-hidden rounded-[2rem] border border-border bg-surface px-8 py-16 text-center sm:px-16">
            <div className="hero-glow absolute inset-0" aria-hidden="true" />
            <div className="relative">
              <h2 className="font-display text-4xl font-extrabold tracking-tight sm:text-6xl">Bring your book to life.</h2>
              <p className="mx-auto mt-4 max-w-xl text-muted">Start with one EPUB. Meet the cast, hear the voices, read the panels.</p>
              <ul className="mx-auto mt-8 flex max-w-2xl flex-wrap justify-center gap-x-6 gap-y-2 text-sm text-muted">
                {['Local by default', 'Whole-volume processing', 'Every fix is reviewable'].map((t) => (
                  <li key={t} className="inline-flex items-center gap-1.5">
                    <Check className="h-4 w-4 text-success" aria-hidden="true" /> {t}
                  </li>
                ))}
              </ul>
              <Link
                to="/projects/new"
                className="mt-10 inline-flex h-12 items-center gap-2 rounded-xl bg-primary px-7 text-base font-semibold text-white shadow-glow transition-colors hover:bg-primary-2"
              >
                Start a project <ArrowRight className="h-4 w-4" aria-hidden="true" />
              </Link>
            </div>
          </div>
        </section>
      </main>

      <footer className="border-t border-border">
        <div className="mx-auto flex max-w-7xl flex-wrap items-center justify-between gap-4 px-4 py-8 text-sm text-muted sm:px-6">
          <Logo />
          <span>Local-first story adaptation.</span>
        </div>
      </footer>
    </div>
  );
}

function SectionIntro({ eyebrow, title, description }) {
  return (
    <div className="max-w-2xl">
      <div className="text-xs font-semibold uppercase tracking-[0.14em] text-accent">{eyebrow}</div>
      <h2 className="mt-3 font-display text-4xl font-bold tracking-tight sm:text-5xl">{title}</h2>
      {description && <p className="mt-4 text-muted">{description}</p>}
    </div>
  );
}

function Feature({ icon: Icon, title, body, className = '' }) {
  return (
    <div className={`group rounded-3xl border border-border bg-surface p-7 transition-colors hover:border-accent/50 ${className}`}>
      <Icon className="h-6 w-6 text-accent" aria-hidden="true" />
      <h3 className="mt-5 font-display text-xl font-bold tracking-tight">{title}</h3>
      <p className="mt-2 text-sm text-muted">{body}</p>
    </div>
  );
}
