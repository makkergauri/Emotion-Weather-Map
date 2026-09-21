/**
 * The two behaviours a first-time visitor to the deployed site depends on:
 * surviving a backend that is still waking up, and filling the map in while the
 * backend's cache warms. Both are timing-driven, so they run on a fake clock.
 */

import { act, renderHook, waitFor } from '@testing-library/react';
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';
import { useCountries } from './useRegionData';
import type { CountrySummary } from '../types';

function country(code: string, condition: CountrySummary['condition']): CountrySummary {
  return {
    code,
    name: code.toUpperCase(),
    lat: 0,
    lng: 0,
    score: condition === 'no_data' ? 0 : 0.2,
    condition,
    headline_count: condition === 'no_data' ? 0 : 20,
    confidence: condition === 'no_data' ? 'none' : 'high',
    source: condition === 'no_data' ? null : 'rss',
    updated_at: null,
  };
}

/**
 * Advance the fake clock in one-second steps, each inside its own act().
 *
 * One big advance doesn't work: React holds every state update made inside an
 * act() until the act exits, so the first retry would fire, queue its update,
 * and never get to issue the next request. Stepping lets React render between
 * timers, the way a real browser does.
 */
async function elapse(ms: number) {
  for (let t = 0; t < ms; t += 1000) {
    await act(async () => {
      await vi.advanceTimersByTimeAsync(1000);
    });
  }
}

function ok(body: unknown) {
  return Promise.resolve(new Response(JSON.stringify(body), { status: 200 }));
}

describe('useCountries', () => {
  beforeEach(() => {
    vi.useFakeTimers({ shouldAdvanceTime: true });
  });

  afterEach(() => {
    vi.useRealTimers();
    vi.unstubAllGlobals();
  });

  it('keeps retrying while a sleeping server wakes up', async () => {
    // Two failed connections, then the server answers — the free-tier cold start.
    const fetchMock = vi
      .fn()
      .mockRejectedValueOnce(new TypeError('Failed to fetch'))
      .mockRejectedValueOnce(new TypeError('Failed to fetch'))
      .mockImplementation(() => ok([country('in', 'rainy')]));
    vi.stubGlobal('fetch', fetchMock);

    const { result } = renderHook(() => useCountries());

    await waitFor(() => expect(result.current.retrying).toBe(true));
    expect(result.current.error).toBeNull();

    await elapse(11_000);

    await waitFor(() => expect(result.current.data).toHaveLength(1));
    expect(result.current.retrying).toBe(false);
    expect(result.current.error).toBeNull();
  });

  it('gives up with a visible error once the retries run out', async () => {
    vi.stubGlobal('fetch', vi.fn().mockRejectedValue(new TypeError('Failed to fetch')));

    const { result } = renderHook(() => useCountries());

    await elapse(5_000 * 13);

    await waitFor(() => expect(result.current.error).toBe('Failed to fetch'));
    expect(result.current.retrying).toBe(false);
  });

  it('polls while the cache warms, then stops once every country is in', async () => {
    const fetchMock = vi
      .fn()
      .mockImplementationOnce(() => ok([country('in', 'no_data'), country('jp', 'no_data')]))
      .mockImplementationOnce(() => ok([country('in', 'rainy'), country('jp', 'no_data')]))
      .mockImplementation(() => ok([country('in', 'rainy'), country('jp', 'sunny')]));
    vi.stubGlobal('fetch', fetchMock);

    const { result } = renderHook(() => useCountries());

    await waitFor(() => expect(result.current.warming).toBe(true));

    await elapse(11_000);

    await waitFor(() => expect(result.current.warming).toBe(false));
    expect(result.current.data?.every((c) => c.condition !== 'no_data')).toBe(true);

    // With nothing left grey, the page goes quiet instead of polling forever.
    const callsWhenDone = fetchMock.mock.calls.length;
    await elapse(30_000);
    expect(fetchMock.mock.calls.length).toBe(callsWhenDone);
  });

  it('does not poll a fully warm map at all', async () => {
    const fetchMock = vi.fn().mockImplementation(() => ok([country('in', 'rainy')]));
    vi.stubGlobal('fetch', fetchMock);

    const { result } = renderHook(() => useCountries());
    await waitFor(() => expect(result.current.data).toHaveLength(1));

    await elapse(30_000);
    expect(fetchMock).toHaveBeenCalledTimes(1);
    expect(result.current.warming).toBe(false);
  });
});