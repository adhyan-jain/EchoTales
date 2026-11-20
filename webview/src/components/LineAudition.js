import React, { useEffect, useRef, useState } from 'react';
import { api } from '../api';
import Button from './ui/Button';
import JobFailure from './ui/JobFailure';
import { describeError } from '../lib/errors';
import { DELIVERY_EMOTIONS } from '../lib/delivery';
import { fileUrl } from '../lib/media';
import { voiceLineSample } from '../lib/voiceSample';

const DEFAULT_LINE = 'You should not have come here.';
const MAX_LINE = 400;
const FIELD =
  'w-full rounded-xl border border-border bg-surface px-3 py-2 font-sans text-sm text-text outline-none transition-colors ' +
  'focus:border-accent focus-visible:ring-1 focus-visible:ring-accent';
const LABEL = 'mb-1 block text-xs font-semibold uppercase tracking-[0.14em] text-muted';

/* Hear one line in a character's voice before the whole book is voiced: pick the line, the delivery emotion and the
   voice (the assigned one, another from the audition shortlist, or one the person uploaded), voice it, and keep the
   voice if it is right. A sample is a job because synthesis uses the GPU. */
export default function LineAudition({ novelId, assignedVoiceId, onUseVoice, busy: parentBusy = false }) {
  const [options, setOptions] = useState(null);
  const [loadError, setLoadError] = useState('');
  const [voiceId, setVoiceId] = useState(assignedVoiceId || '');
  const [emotion, setEmotion] = useState('neutral');
  const [text, setText] = useState(DEFAULT_LINE);
  const [running, setRunning] = useState(false);
  const [sample, setSample] = useState(null);
  const [error, setError] = useState('');
  const [failure, setFailure] = useState(null);
  const gone = useRef(false);

  useEffect(() => () => { gone.current = true; }, []);

  useEffect(() => {
    let live = true;
    Promise.all([api.voiceAudition(novelId), api.listProjectVoices(novelId)])
      .then(([aud, mine]) => {
        if (!live) return;
        const seen = new Set();
        const list = [];
        const add = (id, label) => {
          if (id && !seen.has(id)) {
            seen.add(id);
            list.push({ id, label });
          }
        };
        add(assignedVoiceId, `${assignedVoiceId} (assigned)`);
        ((mine && mine.voices) || []).forEach((v) => add(v.voice_id, `${v.name} (your own voice)`));
        ((aud && aud.candidates) || []).forEach((c) => add(c.voice_id, `${c.name} (${c.gender}, ${c.bank})`));
        setOptions(list);
        setVoiceId((v) => v || (list[0] && list[0].id) || '');
      })
      .catch((err) => live && setLoadError(describeError(err, 'Could not load the voices to choose from.')));
    return () => { live = false; };
  }, [novelId, assignedVoiceId]);

  // A sample belongs to the voice, emotion and words it was made from; any change makes it stale.
  const change = (setter) => (e) => {
    setter(e.target.value);
    setSample(null);
  };

  const line = text.trim();
  const ready = !!voiceId && !!line && line.length <= MAX_LINE && !running;

  const hear = async () => {
    setRunning(true);
    setError('');
    setFailure(null);
    setSample(null);
    try {
      const path = await voiceLineSample(novelId, { voiceId, emotion, text: line }, { cancelled: () => gone.current });
      if (!gone.current && path) setSample(path);
    } catch (err) {
      if (gone.current) return;
      if (err && typeof err.summary === 'string') setFailure({ summary: err.summary });
      else setError(describeError(err, 'Could not make the sample.'));
    } finally {
      if (!gone.current) setRunning(false);
    }
  };

  return (
    <div className="space-y-3">
      {loadError && (
        <div role="alert" className="rounded-xl border border-danger/40 bg-danger/10 px-3 py-2 text-sm text-danger">
          {loadError}
        </div>
      )}
      <div>
        <label className={LABEL} htmlFor="la-voice">Voice</label>
        <select id="la-voice" className={FIELD} value={voiceId} onChange={change(setVoiceId)} disabled={running || !options}>
          {(options || []).map((o) => (
            <option key={o.id} value={o.id}>{o.label}</option>
          ))}
        </select>
        {options && options.length <= 1 && (
          <p className="mt-1 text-xs text-muted">
            To choose among more voices, find narrator candidates in Settings or add one of your own.
          </p>
        )}
      </div>
      <div>
        <label className={LABEL} htmlFor="la-emotion">Delivery</label>
        <select id="la-emotion" className={FIELD} value={emotion} onChange={change(setEmotion)} disabled={running}>
          {DELIVERY_EMOTIONS.map((e) => (
            <option key={e.value} value={e.value}>{e.label}</option>
          ))}
        </select>
      </div>
      <div>
        <label className={LABEL} htmlFor="la-text">Line to hear</label>
        <textarea id="la-text" className={FIELD} rows={2} maxLength={MAX_LINE} value={text} onChange={change(setText)} disabled={running} />
      </div>
      <div className="flex flex-wrap items-center gap-3">
        <Button size="sm" disabled={!ready} onClick={hear}>
          {running ? 'Voicing…' : 'Hear this line'}
        </Button>
        {running && <span role="status" className="text-sm text-muted">Voicing on the GPU, usually under a minute.</span>}
        {sample && voiceId && voiceId !== assignedVoiceId && onUseVoice && (
          <Button variant="secondary" size="sm" disabled={parentBusy} onClick={() => onUseVoice(voiceId)}>
            Use this voice for the character
          </Button>
        )}
      </div>
      {error && (
        <div role="alert" className="rounded-xl border border-danger/40 bg-danger/10 px-3 py-2 text-sm text-danger">{error}</div>
      )}
      {failure && <JobFailure kind="sample" summary={failure.summary} />}
      {sample && (
        <audio controls autoPlay aria-label="Sample of the line" src={fileUrl(novelId, sample)} className="h-10 w-full" />
      )}
    </div>
  );
}
