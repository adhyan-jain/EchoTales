import { ApiError, api } from '../api';
import { describeError, isNetworkError, isNotFound } from '../lib/errors';

// What a person reads when a request fails. The failure-state QA of
// 2026-09-26 found a 500 whose body was a Python traceback shown verbatim on
// every page, and every non-network error labelled "can't reach the server".

const UNREACHABLE = /can.t reach the echotales server/i;

test('a network failure says the server is unreachable', () => {
  expect(describeError(new ApiError(0, ''))).toMatch(UNREACHABLE);
  expect(describeError(new TypeError('Failed to fetch'))).toMatch(UNREACHABLE);
  expect(isNetworkError(new ApiError(0, ''))).toBe(true);
});

test('a 500 never shows the server text, even when it is a traceback', () => {
  const trace = 'Traceback (most recent call last): File "webview_server.py", line 999, in do_GET sqlite3.OperationalError';
  const text = describeError(new ApiError(500, trace));
  expect(text).not.toMatch(/traceback|\.py|sqlite/i);
  expect(text).toMatch(/server hit a problem/i);
});

test('a 404 does not echo the raw id the server put in its message', () => {
  const text = describeError(new ApiError(404, "unknown novel '%25ZZ'"));
  expect(text).not.toMatch(/%25ZZ|novel/i);
  expect(isNotFound(new ApiError(404, ''))).toBe(true);
});

test('a deliberate 400 validation message is shown as written', () => {
  expect(describeError(new ApiError(400, 'speaker_id is required'))).toBe('speaker_id is required');
});

test('a 4xx that looks like an internal error falls back instead', () => {
  expect(describeError(new ApiError(400, 'KeyError at handlers.py line 12'), 'That change could not be saved.')).toBe(
    'That change could not be saved.'
  );
});

test('a plain (non-API) error never leaks its message', () => {
  expect(describeError(new TypeError("Cannot read properties of undefined (reading 'number')"), 'Try again.')).toBe('Try again.');
});

test('a lapsed session asks the user to sign in again', () => {
  expect(describeError(new ApiError(401, 'unauthorized'))).toMatch(/sign in/i);
});

test('an unknown value falls back to the caller’s wording', () => {
  expect(describeError(undefined, 'Could not load projects.')).toBe('Could not load projects.');
});

describe('request timeout', () => {
  afterEach(() => {
    jest.useRealTimers();
    delete global.fetch;
  });

  test('a server that never answers becomes an unreachable-server error instead of an endless spinner', async () => {
    jest.useFakeTimers();
    // A fetch that honours AbortController, like the real one.
    global.fetch = jest.fn(
      (_url, { signal }) =>
        new Promise((_resolve, reject) => {
          signal.addEventListener('abort', () => reject(new DOMException('aborted', 'AbortError')));
        })
    );
    const pending = api.manifest();
    const caught = pending.catch((e) => e);
    jest.advanceTimersByTime(30001);
    const err = await caught;
    expect(err).toBeInstanceOf(ApiError);
    expect(err.status).toBe(0);
    expect(describeError(err)).toMatch(/can.t reach the echotales server/i);
  });

  test('a body that never arrives is also bounded, not just the headers', async () => {
    jest.useFakeTimers();
    global.fetch = jest.fn((_url, { signal }) =>
      Promise.resolve({
        ok: true,
        status: 200,
        json: () =>
          new Promise((_resolve, reject) => {
            signal.addEventListener('abort', () => reject(new DOMException('aborted', 'AbortError')));
          }),
      })
    );
    const caught = api.manifest().catch((e) => e);
    await Promise.resolve();
    jest.advanceTimersByTime(30001);
    const err = await caught;
    expect(err).toBeInstanceOf(ApiError);
  });

  test('a 200 that is not JSON never shows the parser message', async () => {
    global.fetch = jest.fn(() =>
      Promise.resolve({ ok: true, status: 200, json: () => Promise.reject(new SyntaxError("Unexpected token '<'")) })
    );
    const err = await api.manifest().catch((e) => e);
    expect(err).toBeInstanceOf(ApiError);
    expect(describeError(err, 'fallback')).not.toMatch(/token|json/i);
  });

  test('a fast response is not aborted', async () => {
    global.fetch = jest.fn(() => Promise.resolve({ ok: true, json: () => Promise.resolve([{ id: 'x' }]) }));
    await expect(api.manifest()).resolves.toEqual([{ id: 'x' }]);
  });
});

describe('chapter list against an older backend', () => {
  afterEach(() => {
    delete global.fetch;
  });

  test('falls back to the full payload when /chapters does not exist yet', async () => {
    global.fetch = jest.fn((url) =>
      String(url).endsWith('/chapters')
        ? Promise.resolve({ ok: false, status: 404, json: () => Promise.resolve({ error: 'not found' }) })
        : Promise.resolve({ ok: true, json: () => Promise.resolve({ chapters: [{ number: 1, spans: [1, 2] }, { number: 2.5, title: 'Half', spans: [] }] }) })
    );
    await expect(api.chapters('toy')).resolves.toEqual([{ number: 1, title: '' }, { number: 2.5, title: 'Half' }]);
  });

  test('other failures are not swallowed by the fallback', async () => {
    global.fetch = jest.fn(() => Promise.resolve({ ok: false, status: 500, json: () => Promise.resolve({ error: 'boom' }) }));
    await expect(api.chapters('toy')).rejects.toMatchObject({ status: 500 });
  });
});
