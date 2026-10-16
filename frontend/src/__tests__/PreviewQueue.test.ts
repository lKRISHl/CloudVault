import { afterEach, beforeEach, expect, it, vi } from 'vitest';
import { api, setAccessToken } from '../services/api';

const waiting = { id: 'job', state: 'queued', preview: null, expires_at: '2030-01-01' };
const preview = { kind: 'text', text: 'inert content' };
beforeEach(() => { vi.useFakeTimers(); setAccessToken('test-token'); });
afterEach(() => { vi.useRealTimers(); vi.unstubAllGlobals(); setAccessToken(null); });
function response(body: unknown, status = 200) { return new Response(JSON.stringify(body), { status, headers: { 'Content-Type': 'application/json' } }); }

it('queues a request and polls its private result with the selected version and page', async () => {
  const fetch = vi.fn().mockResolvedValueOnce(response(waiting, 202)).mockResolvedValueOnce(response({ ...waiting, state: 'ready', preview }));
  vi.stubGlobal('fetch', fetch);
  const promise = api.preview('file', 'old-version', 2);
  await vi.advanceTimersByTimeAsync(1500);
  expect(await promise).toEqual(preview);
  expect(fetch.mock.calls[0][0]).toBe('/api/v1/files/file/preview-jobs');
  const body = JSON.parse(fetch.mock.calls[0][1].body);
  expect(body).toMatchObject({ version_id: 'old-version', page: 2 });
  expect(body.request_id).toMatch(/^[0-9a-f-]{36}$/);
  expect(fetch.mock.calls[1][0]).toBe('/api/v1/files/file/preview-jobs/job');
});

it('aborting the wait sends explicit cancellation for the known job', async () => {
  const fetch = vi.fn().mockResolvedValueOnce(response(waiting, 202)).mockResolvedValue(response({ ...waiting, state: 'cancelled' }));
  vi.stubGlobal('fetch', fetch);
  const controller = new AbortController();
  const promise = api.preview('file', null, 0, controller.signal);
  const outcome = expect(promise).rejects.toMatchObject({ name: 'AbortError' });
  await vi.advanceTimersByTimeAsync(0);
  controller.abort(); await outcome;
  expect(fetch).toHaveBeenLastCalledWith('/api/v1/files/file/preview-jobs/job', expect.objectContaining({ method: 'DELETE' }));
});
