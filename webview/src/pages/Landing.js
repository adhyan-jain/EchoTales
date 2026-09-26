import React, { useEffect, useState } from 'react';
import { Link } from 'react-router-dom';
import { ArrowRight } from 'lucide-react';
import { api } from '../api';
import { Logo, ThemeToggle } from '../components/app/Chrome';
import { pickPanels, pickReferenceSheets, thumbUrl } from '../lib/media';

/**
 * Public landing page. Imagery is the first project's own rendered panels
 * and reference sheets, fetched live -- no stock art, and nothing shown that
 * the pipeline did not actually produce. If the server is unreachable or
 * locked, every image slot falls back to a flat block, so the page still
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
    return <div className={`bg-surface2 ${className}`} aria-hidden="true" />;
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
  { href: '#page', label: 'On the page' },
  { href: '#details', label: 'Details' },
];

const STEPS = [
  {
    title: 'Read the whole book',
    body: 'Drop in an EPUB. Every chapter is sorted into narration, dialogue and inner monologue, so each kind of line can be voiced and drawn its own way.',
  },
  {
    title: 'Track who is who',
    body: 'Names, titles and nicknames are linked to the characters they refer to across the whole volume, with a separate record for each body a character has.',
  },
  {
    title: 'Cast the voices, draw the scenes',
    body: 'Each character gets a voice and a recorded look, so the audiobook and the panels are cast from the same character list.',
  },
];

const DETAILS = [
  ['A recorded look for each character', 'Each character body gets a reference sheet and recorded appearance traits, and those traits are carried into the panel prompts instead of being reinvented scene by scene.'],
  ['A voice per character', 'Where the speaker can be identified, dialogue is cast to that character’s voice. Unidentified speakers get their own distinct voice slots.'],
  ['Panels planned from the story', 'Scene direction, cast and setting come from the text itself, not from a one-line prompt.'],
  ['Review, don’t redo', 'Fix a wrong name or speaker in place. Corrections queue up, and you apply them to the book when you’re ready.'],
  ['Local by default', 'Built to run on a consumer GPU with local models, so a manuscript stays on your machine unless you choose to connect a cloud model.'],
  ['Names stay decided', 'Names it has already resolved are reused across the book instead of being decided again chapter by chapter.'],
];

export default function Landing() {
  const { novelId, label, panels, stats } = useShowcase();
  const [lead, ...rest] = panels;

  return (
    <div className="min-h-screen bg-bg text-text">
      <header className="fixed inset-x-0 top-0 z-50 border-b border-border bg-bg/95">
        <nav className="mx-auto flex h-16 max-w-6xl items-center gap-6 px-4 sm:px-6" aria-label="Main">
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
              className="inline-flex h-9 items-center gap-1.5 rounded-lg border border-border px-4 text-sm font-medium transition-colors hover:border-accent/60"
            >
              Open app <ArrowRight className="h-4 w-4" aria-hidden="true" />
            </Link>
          </div>
        </nav>
      </header>

      <main>
        <section className="mx-auto grid max-w-6xl items-center gap-12 px-4 pb-20 pt-32 sm:px-6 lg:grid-cols-[1.1fr_1fr] lg:pt-40">
          <div className="animate-reveal">
            <h1 className="font-display text-5xl font-medium sm:text-6xl lg:text-7xl">
              A web novel, read aloud by a cast and drawn as panels.
            </h1>
            <p className="mt-6 max-w-xl text-lg text-muted">
              EchoTales works out who is who across a whole volume, then uses that to give each character a voice and a
              look, and to plan the scenes.
            </p>
            <div className="mt-8 flex flex-wrap items-center gap-3">
              <Link
                to="/projects/new"
                className="inline-flex h-12 items-center gap-2 rounded-lg bg-primary px-6 text-base font-semibold text-on-primary transition-colors hover:bg-primary-2"
              >
                Start a project <ArrowRight className="h-4 w-4" aria-hidden="true" />
              </Link>
              <Link
                to="/projects"
                className="inline-flex h-12 items-center rounded-lg border border-border px-6 text-base font-medium transition-colors hover:border-accent/60"
              >
                Open your library
              </Link>
            </div>
            {stats && stats.chapters ? (
              <p className="mt-8 text-sm text-muted">
                On this server: <span className="font-medium text-text">{label}</span> ·{' '}
                <span className="tabular-nums">{stats.chapters}</span> chapters processed
              </p>
            ) : null}
          </div>

          <div className="grid grid-cols-5 grid-rows-2 gap-2" aria-hidden="true">
            <Img novelId={novelId} path={lead} width={960} className="col-span-3 row-span-2 h-full min-h-[22rem] w-full rounded-lg border border-border" />
            <Img novelId={novelId} path={rest[0]} className="col-span-2 h-full min-h-[10rem] w-full rounded-lg border border-border" />
            <Img novelId={novelId} path={rest[1]} className="col-span-2 h-full min-h-[10rem] w-full rounded-lg border border-border" />
          </div>
        </section>

        <section id="how" className="mx-auto max-w-6xl scroll-mt-20 px-4 py-20 sm:px-6">
          <h2 className="font-display text-4xl font-medium sm:text-5xl">How it works</h2>
          <ol className="mt-10 border-t border-border">
            {STEPS.map((step, i) => (
              <li key={step.title} className="grid gap-2 border-b border-border py-8 md:grid-cols-[4rem_1fr_1.4fr] md:gap-8">
                <span className="font-mono text-sm text-muted">{String(i + 1).padStart(2, '0')}</span>
                <h3 className="font-display text-2xl font-medium">{step.title}</h3>
                <p className="text-muted">{step.body}</p>
              </li>
            ))}
          </ol>
        </section>

        <section id="page" className="mx-auto max-w-6xl scroll-mt-20 px-4 pb-20 sm:px-6">
          <div className="grid gap-10 lg:grid-cols-[1fr_1.3fr] lg:items-start">
            <div>
              <h2 className="font-display text-4xl font-medium sm:text-5xl">Every line says who is speaking.</h2>
              <p className="mt-5 max-w-md text-muted">
                Names in the text are underlined in their character’s colour. Each line of dialogue shows its speaker in
                the margin, and a speaker the text never names keeps a numbered slot of its own, so it can be voiced
                consistently and fixed later.
              </p>
            </div>
            <figure>
              <div className="rounded-lg border border-border bg-surface px-5 py-2 sm:px-8">
                <SpecimenLine who="Narration">
                  <Mark colour="#e8aa50">Mara</Mark> set the lantern on the sill and waited for the ferry.
                </SpecimenLine>
                <SpecimenLine who="Mara" dialogue>
                  “It’s late,” she said. “He won’t come.”
                </SpecimenLine>
                <SpecimenLine who="Unknown speaker 1" note="own voice slot" dialogue>
                  “The <Mark colour="#7acaa0">captain</Mark> is never late,” the old man said.
                </SpecimenLine>
              </div>
              <figcaption className="mt-3 text-sm text-muted">Illustration with invented text, not taken from a book.</figcaption>
            </figure>
          </div>
        </section>

        <section id="details" className="mx-auto max-w-6xl scroll-mt-20 px-4 pb-20 sm:px-6">
          <h2 className="font-display text-4xl font-medium sm:text-5xl">Built for books too long to hold in your head.</h2>
          <dl className="mt-10 grid border-t border-border md:grid-cols-2 md:gap-x-16">
            {DETAILS.map(([term, def]) => (
              <div key={term} className="border-b border-border py-6">
                <dt className="font-display text-xl font-medium">{term}</dt>
                <dd className="mt-2 text-muted">{def}</dd>
              </div>
            ))}
          </dl>
        </section>

        {panels.length > 6 && (
          <section className="mx-auto max-w-6xl px-4 pb-20 sm:px-6" aria-label="Rendered panels">
            <h2 className="font-display text-4xl font-medium sm:text-5xl">Straight from {label}</h2>
            <p className="mt-3 text-muted">Panels from the most recent renders on this server.</p>
            <div className="mt-8 grid grid-cols-2 gap-2 sm:grid-cols-3 lg:grid-cols-6">
              {panels.slice(3, 15).map((p) => (
                <Img key={p} novelId={novelId} path={p} alt="Generated panel" className="aspect-[3/4] w-full rounded-lg border border-border" />
              ))}
            </div>
          </section>
        )}

        <section className="border-t border-border">
          <div className="mx-auto flex max-w-6xl flex-wrap items-center justify-between gap-6 px-4 py-16 sm:px-6">
            <h2 className="font-display text-3xl font-medium sm:text-4xl">Start with one EPUB.</h2>
            <Link
              to="/projects/new"
              className="inline-flex h-12 items-center gap-2 rounded-lg bg-primary px-6 text-base font-semibold text-on-primary transition-colors hover:bg-primary-2"
            >
              Start a project <ArrowRight className="h-4 w-4" aria-hidden="true" />
            </Link>
          </div>
        </section>
      </main>

      <footer className="border-t border-border">
        <div className="mx-auto flex max-w-6xl flex-wrap items-center justify-between gap-4 px-4 py-8 text-sm text-muted sm:px-6">
          <Logo />
          <span>Local-first story adaptation.</span>
        </div>
      </footer>
    </div>
  );
}

function Mark({ colour, children }) {
  return (
    <span className="font-medium" style={{ borderBottom: `2px solid ${colour}` }}>
      {children}
    </span>
  );
}

function SpecimenLine({ who, note, dialogue = false, children }) {
  return (
    <div className="grid gap-1 border-b border-border/60 py-4 last:border-b-0 sm:grid-cols-[8rem_1fr] sm:gap-5">
      <div className="text-sm sm:text-right">
        <div className="font-medium text-text">{who}</div>
        {note && <div className="text-xs text-muted">{note}</div>}
      </div>
      <p
        className={`font-display text-xl leading-relaxed ${dialogue ? 'border-l-2 border-accent/60 pl-4' : ''}`}
      >
        {children}
      </p>
    </div>
  );
}
