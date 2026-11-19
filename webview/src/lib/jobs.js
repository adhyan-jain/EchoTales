import { api } from '../api';

const ENDED = ['SUCCEEDED', 'FAILED', 'PARTIAL', 'CANCELLED', 'INTERRUPTED'];

/**
 * Follow one queued job to its end and resolve with its last state. Checks at once, then every `everyMs`, and gives up
 * after `maxChecks` (a job left RUNNING by a server restart must not be polled for ever); `cancelled()` lets an
 * unmounted panel stop it. A failed read is retried like any other tick: one dropped request is not the job failing.
 */
export async function waitForJob(novelId, jobId, { everyMs = 2000, maxChecks = 450, cancelled = () => false } = {}) {
  let last = null;
  for (let i = 0; i < maxChecks && !cancelled(); i += 1) {
    try {
      last = await api.getJob(novelId, jobId);
      if (last && ENDED.includes(last.status)) return last;
    } catch {
      /* try again on the next tick */
    }
    await new Promise((resolve) => setTimeout(resolve, everyMs));
  }
  return last;
}
