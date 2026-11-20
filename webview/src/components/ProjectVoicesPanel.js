import React, { useCallback, useEffect, useRef, useState } from 'react';
import { api } from '../api';
import Button from './ui/Button';
import Input from './ui/Input';
import { useToast } from './ui/Toast';
import JobFailure from './ui/JobFailure';
import { describeError } from '../lib/errors';
import { fileUrl } from '../lib/media';
import { voiceLineSample } from '../lib/voiceSample';

// Shown until the server answers; the server's own statement replaces it, so the recorded wording and the label agree.
const DEFAULT_STATEMENT = "This is my voice or I have the speaker's permission.";
// A fixed sentence for the preview: the person is judging the voice, not the words.
const PREVIEW_LINE = 'The lantern light did not reach the stairs, and he counted them anyway.';

/* Add a voice of your own (or one you have permission to use) for this book. It is stored in this project only, with a
   record of the consent next to it, and then joins the voices characters are cast from the next time the book is
   voiced. The checkbox is required: a recording of a real person can be cloned to say anything. */
export default function ProjectVoicesPanel({ novelId }) {
  const push = useToast();
  const [info, setInfo] = useState(null);
  const [loadError, setLoadError] = useState('');
  const [name, setName] = useState('');
  const [gender, setGender] = useState('female');
  const [age, setAge] = useState('30');
  const [file, setFile] = useState(null);
  const [fileKey, setFileKey] = useState(0);
  const [consent, setConsent] = useState(false);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState('');
  const [previewing, setPreviewing] = useState('');
  const [previews, setPreviews] = useState({});
  const [previewError, setPreviewError] = useState(null);
  const gone = useRef(false);

  useEffect(() => () => { gone.current = true; }, []);

  const preview = async (voiceId) => {
    setPreviewing(voiceId);
    setPreviewError(null);
    try {
      const path = await voiceLineSample(novelId, { voiceId, emotion: 'neutral', text: PREVIEW_LINE }, { cancelled: () => gone.current });
      if (!gone.current && path) setPreviews((p) => ({ ...p, [voiceId]: path }));
    } catch (err) {
      if (gone.current) return;
      setPreviewError(
        typeof err.summary === 'string'
          ? { voiceId, summary: err.summary }
          : { voiceId, message: describeError(err, 'Could not make the sample.') }
      );
    } finally {
      if (!gone.current) setPreviewing('');
    }
  };

  const load = useCallback(() => {
    return api
      .listProjectVoices(novelId)
      .then((r) => {
        if (gone.current) return;
        setInfo(r);
        setLoadError('');
      })
      .catch((err) => {
        if (!gone.current) setLoadError(describeError(err, 'Could not load your voices.'));
      });
  }, [novelId]);

  useEffect(() => {
    load();
  }, [load]);

  const statement = (info && info.statement) || DEFAULT_STATEMENT;
  const limits = (info && info.limits) || { min_seconds: 3, max_seconds: 60 };
  const ageN = Number(age);
  const ready = name.trim() !== '' && !!file && consent && Number.isInteger(ageN) && ageN > 0 && !busy;

  const submit = async () => {
    setBusy(true);
    setError('');
    try {
      await api.uploadProjectVoice(novelId, file, { name: name.trim(), gender, age: ageN, consent: true });
      push('Voice added.', 'success');
      setName('');
      setFile(null);
      setFileKey((k) => k + 1);
      setConsent(false);
      await load();
    } catch (err) {
      setError(describeError(err, 'Could not add that voice.'));
    } finally {
      setBusy(false);
    }
  };

  return (
    <section aria-label="Your own voices" className="rounded-3xl border border-border bg-surface p-6">
      <h2 className="font-display text-lg font-bold tracking-tight">Your own voices</h2>
      <p className="mt-1 text-sm text-muted">
        Add a clean recording of one speaker, WAV or FLAC, between {limits.min_seconds} and {limits.max_seconds} seconds.
        The voice is kept in this project only and can be cast as a character the next time the book is voiced.
      </p>

      <div className="mt-4 grid gap-3 sm:grid-cols-[2fr_1fr_1fr]">
        <div>
          <label className="mb-1 block text-xs font-semibold uppercase tracking-[0.14em] text-muted" htmlFor="pv-name">
            Voice name
          </label>
          <Input id="pv-name" value={name} onChange={(e) => setName(e.target.value)} placeholder="e.g. My voice" />
        </div>
        <div>
          <label className="mb-1 block text-xs font-semibold uppercase tracking-[0.14em] text-muted" htmlFor="pv-gender">
            Gender
          </label>
          <select
            id="pv-gender"
            value={gender}
            onChange={(e) => setGender(e.target.value)}
            className="h-10 w-full rounded-xl border border-border bg-transparent px-3 font-sans text-sm text-text"
          >
            <option value="female">Female</option>
            <option value="male">Male</option>
          </select>
        </div>
        <div>
          <label className="mb-1 block text-xs font-semibold uppercase tracking-[0.14em] text-muted" htmlFor="pv-age">
            Age
          </label>
          <Input id="pv-age" type="number" min="5" max="100" value={age} onChange={(e) => setAge(e.target.value)} />
        </div>
      </div>

      <div className="mt-3">
        <label className="mb-1 block text-xs font-semibold uppercase tracking-[0.14em] text-muted" htmlFor="pv-file">
          Recording
        </label>
        <input
          key={fileKey}
          id="pv-file"
          type="file"
          accept=".wav,.flac,audio/wav,audio/flac"
          onChange={(e) => setFile(e.target.files && e.target.files[0] ? e.target.files[0] : null)}
          className="block cursor-pointer text-sm text-muted file:mr-3 file:cursor-pointer file:rounded-lg file:border file:border-border file:bg-transparent file:px-3 file:py-1.5 file:font-sans file:text-sm file:text-text"
        />
      </div>

      <label className="mt-4 flex cursor-pointer items-start gap-2 text-sm text-text">
        <input type="checkbox" className="mt-1" checked={consent} onChange={(e) => setConsent(e.target.checked)} />
        <span>{statement}</span>
      </label>

      {error && (
        <div role="alert" className="mt-3 rounded-xl border border-danger/40 bg-danger/10 px-3 py-2 text-sm text-danger">
          {error}
        </div>
      )}
      <div className="mt-4">
        <Button variant="secondary" disabled={!ready} onClick={submit}>
          {busy ? 'Adding…' : 'Add this voice'}
        </Button>
      </div>

      {loadError && (
        <div role="alert" className="mt-4 rounded-xl border border-danger/40 bg-danger/10 px-3 py-2 text-sm text-danger">
          {loadError}
        </div>
      )}
      <ul className="mt-5 space-y-2">
        {info && info.voices.length === 0 && !loadError && <li className="text-sm text-muted">No voices of your own yet.</li>}
        {((info && info.voices) || []).map((v) => (
          <li key={v.voice_id} className="rounded-2xl border border-border px-4 py-3 text-sm">
            <span className="text-text">{v.name}</span>
            <span className="ml-2 text-xs text-muted">
              {v.gender}, age {v.age}. Consent recorded {String(v.consent_at).slice(0, 10)}.
            </span>
            <div className="mt-2 grid gap-2 sm:grid-cols-2">
              <div>
                <span className="mb-1 block text-xs text-muted">Your recording</span>
                {v.clip ? (
                  <audio controls preload="none" aria-label={`Your recording of ${v.name}`} src={fileUrl(novelId, v.clip)} className="h-10 w-full" />
                ) : (
                  <span className="text-xs text-muted">The recording is not available.</span>
                )}
              </div>
              <div>
                <span className="mb-1 block text-xs text-muted">How it sounds reading a line</span>
                {previews[v.voice_id] ? (
                  <audio controls aria-label={`Synthesized sample of ${v.name}`} src={fileUrl(novelId, previews[v.voice_id])} className="h-10 w-full" />
                ) : (
                  <Button variant="secondary" size="sm" disabled={!!previewing} onClick={() => preview(v.voice_id)}>
                    {previewing === v.voice_id ? 'Voicing…' : 'Hear a synthesized sample'}
                  </Button>
                )}
              </div>
            </div>
            {previewError && previewError.voiceId === v.voice_id && (
              previewError.message
                ? <div role="alert" className="mt-2 text-sm text-danger">{previewError.message}</div>
                : <JobFailure kind="sample" summary={previewError.summary} />
            )}
          </li>
        ))}
      </ul>
    </section>
  );
}
