/**
 * User-facing wording for an API failure.
 *
 * The backend's `{error}` strings are written for developers ("unknown novel
 * '%25ZZ'", and on a 500 the exception text, which can be a Python
 * traceback). What a person sees depends on the kind of failure:
 *
 *   network (status 0)  the server is not reachable -- say how to start it
 *   401                 the session lapsed
 *   404                 the thing does not exist -- never echo the raw id
 *   other 4xx           a validation message the backend wrote on purpose
 *                       ("speaker_id is required"): shown, unless it looks
 *                       like an internal error
 *   5xx / anything odd  generic; the detail belongs in the server log
 */
const LOOKS_INTERNAL = /traceback|\.py\b|sqlite|exception|errno|\bat \w+\.|line \d+|\[object/i;
const NETWORK_TEXT = /failed to fetch|networkerror|load failed/i;

const UNREACHABLE = 'Can’t reach the EchoTales server. Check that it is running, then try again.';

export function describeError(err, fallback = 'Something went wrong.') {
  const status = err && typeof err.status === 'number' ? err.status : undefined;
  const raw = (err && (err.serverMessage ?? err.message)) || '';

  if (status === 0) return UNREACHABLE;
  if (status === 401) return 'Your session has ended. Sign in again to continue.';
  if (status === 404) return 'That wasn’t found on this server.';
  if (status && status >= 500) {
    return 'The server hit a problem handling that. Try again, and check the server log if it keeps happening.';
  }
  if (status && status >= 400 && raw && !LOOKS_INTERNAL.test(raw)) return raw;
  if (!status && NETWORK_TEXT.test(raw)) return UNREACHABLE;
  return fallback;
}

export const isNetworkError = (err) => !!err && err.status === 0;
export const isNotFound = (err) => !!err && err.status === 404;
