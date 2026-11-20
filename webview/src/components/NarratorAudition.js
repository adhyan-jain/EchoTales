import React, { useCallback, useEffect, useRef, useState } from 'react';
import { api } from '../api';
import Button from './ui/Button';
import JobFailure from './ui/JobFailure';
import { useToast } from './ui/Toast';
import { describeError } from '../lib/errors';
import { waitForJob } from '../lib/jobs';
import { fileUrl } from '../lib/media';

/* Choose the narrator by ear. The narrator reads every line that is not a character's, so it is the one voice worth
   listening to before a whole book is voiced. The shortlist comes from measuring the voice banks (clean, steady
   pace, spread over pitch); finding it and voicing a sample for each is one job, because it uses the GPU. Choosing
   writes the single config.json key `voice.narrator` and nothing else. */
export default function NarratorAudition({ novelId }) {
  const push = useToast();
  const [info, setInfo] = useState(null);
  const [loadError, setLoadError] = useState('');
  const [picked, setPicked] = useState('');
  const [busy, setBusy] = useState('');
  const [failure, setFailure] = useState(null);
  const gone = useRef(false);

  useEffect(() => () => { gone.current = true; }, []);

  const load = useCallback(() => {
    return api
      .voiceAudition(novelId)
      .then((r) => {
        if (gone.current) return;
        setInfo(r);
        setLoadError('');
        setPicked((p) => p || r.narrator || '');
      })
      .catch((err) => {
        if (!gone.current) setLoadError(describeError(err, 'Could not load the narrator candidates.'));
      });
  }, [novelId]);

  useEffect(() => {
    load();
  }, [load]);

  const find = async () => {
    setBusy('find');
    setFailure(null);
    try {
      const queued = await api.triggerStage(novelId, 'voice_audition', { target: 'narrator' });
      const done = await waitForJob(novelId, queued.job_id, { everyMs: 3000, cancelled: () => gone.current });
      if (gone.current) return;
      if (done && done.status === 'SUCCEEDED') push('Narrator samples ready.', 'success');
      else setFailure({ summary: done && done.error_summary });
      await load();
    } catch (err) {
      push(describeError(err, 'Could not queue the narrator audition.'), 'danger');
    } finally {
      if (!gone.current) setBusy('');
    }
  };

  const choose = async () => {
    setBusy('choose');
    try {
      await api.setNarrator(novelId, picked);
      push('Narrator saved. The next time the book is voiced it reads the narration.', 'success');
      await load();
    } catch (err) {
      push(describeError(err, 'Could not save the narrator.'), 'danger');
    } finally {
      if (!gone.current) setBusy('');
    }
  };

  const candidates = (info && info.candidates) || [];
  const current = (info && info.narrator) || '';
  const hasSamples = candidates.some((c) => c.sample);

  return (
    <section aria-label="Narrator audition" className="rounded-3xl border border-border bg-surface p-6">
      <h2 className="font-display text-lg font-bold tracking-tight">Choose the narrator</h2>
      <p className="mt-1 text-sm text-muted">
        The narrator reads everything that is not a character&rsquo;s line. Listen to each candidate read the same
        passage, then pick one.
        {current ? <> The narrator now is <span className="font-mono text-text">{current}</span>.</> : ' No narrator is chosen yet; the voice stage picks one by default.'}
      </p>

      {loadError && (
        <div role="alert" className="mt-3 rounded-xl border border-danger/40 bg-danger/10 px-3 py-2 text-sm text-danger">
          {loadError}
        </div>
      )}

      <div className="mt-4 flex flex-wrap items-center gap-3">
        <Button variant="secondary" disabled={!!busy} onClick={find}>
          {busy === 'find' ? 'Finding and voicing candidates…' : candidates.length ? 'Find new candidates' : 'Find narrator candidates'}
        </Button>
        {busy === 'find' && (
          <span role="status" className="text-sm text-muted">
            This measures the voice banks and voices a sample each on the GPU, which can take several minutes.
          </span>
        )}
      </div>
      {failure && <JobFailure kind="narrator audition" summary={failure.summary} />}

      {info && candidates.length === 0 && !loadError && busy !== 'find' && (
        <p className="mt-4 text-sm text-muted">No candidates yet. Find them to start listening.</p>
      )}

      {candidates.length > 0 && (
        <fieldset className="mt-5">
          <legend className="mb-2 text-xs font-semibold uppercase tracking-[0.14em] text-muted">Candidates</legend>
          <p className="mb-3 text-sm text-muted">
            Passage: <span className="italic">{info.passage}</span>
          </p>
          <ul className="space-y-2">
            {candidates.map((c) => {
              const id = `narrator-${c.voice_id}`;
              return (
                <li
                  key={c.voice_id}
                  className="grid items-center gap-3 rounded-2xl border border-border px-4 py-3 sm:grid-cols-[minmax(0,1fr)_minmax(0,1.4fr)]"
                >
                  <label htmlFor={id} className="flex cursor-pointer items-start gap-3 text-sm">
                    <input
                      id={id}
                      type="radio"
                      name="narrator"
                      value={c.voice_id}
                      checked={picked === c.voice_id}
                      onChange={() => setPicked(c.voice_id)}
                      className="mt-1 focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-accent focus-visible:ring-offset-2 focus-visible:ring-offset-bg"
                    />
                    <span>
                      <span className="block text-text">
                        {c.name}
                        {current === c.voice_id && <span className="ml-2 text-xs text-accent">current narrator</span>}
                      </span>
                      <span className="block text-xs text-muted">
                        {c.gender}
                        {c.f0_hz ? `, about ${Math.round(c.f0_hz)} Hz` : ''}. {c.bank} ({c.licence}).
                      </span>
                    </span>
                  </label>
                  {c.sample ? (
                    <audio
                      controls
                      preload="none"
                      aria-label={`Sample of ${c.name}`}
                      src={fileUrl(novelId, c.sample)}
                      className="h-10 w-full"
                    />
                  ) : (
                    <span className="text-sm text-muted">No sample voiced yet.</span>
                  )}
                </li>
              );
            })}
          </ul>
          <div className="mt-4 flex flex-wrap items-center gap-3">
            <Button disabled={!picked || picked === current || !!busy} onClick={choose}>
              {busy === 'choose' ? 'Saving…' : 'Use as narrator'}
            </Button>
            {!hasSamples && <span className="text-sm text-muted">Samples are voiced when you find candidates.</span>}
          </div>
        </fieldset>
      )}
    </section>
  );
}
