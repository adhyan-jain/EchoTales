import { api } from '../api';
import { waitForJob } from './jobs';

/** A failed sample job: carries the job's own error text for `JobFailure`'s disclosure. */
export class SampleJobError extends Error {
  constructor(summary) {
    super('The sample was not made.');
    this.summary = summary || '';
  }
}

/**
 * The output-folder path of one line spoken in one voice with one delivery emotion. A finished sample is reused (the
 * server names it from the voice, emotion and words), so asking again for the same line costs nothing; otherwise one
 * `voice_audition` job is queued, because synthesis uses the GPU, and followed to its end.
 */
export async function voiceLineSample(novelId, { voiceId, emotion, text }, { cancelled = () => false } = {}) {
  const ask = { voiceId, emotion, text };
  try {
    return (await api.voiceSample(novelId, ask)).path;
  } catch (err) {
    if (!err || err.status !== 404) throw err;
  }
  const queued = await api.triggerStage(novelId, 'voice_audition', {
    target: 'line', voice_id: voiceId, emotion, text,
  });
  const done = await waitForJob(novelId, queued.job_id, { everyMs: 1500, cancelled });
  if (cancelled()) return null;
  if (!done || done.status !== 'SUCCEEDED') throw new SampleJobError(done && done.error_summary);
  return (await api.voiceSample(novelId, ask)).path;
}
