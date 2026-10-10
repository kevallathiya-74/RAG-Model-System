import { describe, it, expect, beforeEach, vi, afterEach } from 'vitest';
import {
  setAuth,
  getAuthToken,
  getStoredUser,
  clearAuth,
  onUnauthorized,
  apiRequest,
  loginApi,
  chatApi,
  getDocumentsApi
} from '../src/api/client.js';
import {
  formatDurationMs,
  formatDurationSec,
  formatLatency
} from '../src/utils/format.js';

describe('Secure API Client - Auth & State Management', () => {
  let mockStorage = {};

  beforeEach(() => {
    mockStorage = {};
    vi.stubGlobal('localStorage', {
      getItem: (key) => mockStorage[key] || null,
      setItem: (key, val) => { mockStorage[key] = String(val); },
      removeItem: (key) => { delete mockStorage[key]; },
      clear: () => { mockStorage = {}; }
    });
  });

  afterEach(() => {
    vi.restoreAllMocks();
  });

  it('stores and retrieves JWT token and user summary securely', () => {
    clearAuth();
    expect(getAuthToken()).toBeNull();
    expect(getStoredUser()).toBeNull();

    const sampleUser = {
      user_id: 'U001',
      name: 'System Admin',
      role: 'finance_manager',
      tenant_id: 'TENANT-001'
    };
    const sampleToken = 'eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9.dummy';

    setAuth(sampleToken, sampleUser);
    expect(getAuthToken()).toBe(sampleToken);
    expect(getStoredUser()).toEqual(sampleUser);

    clearAuth();
    expect(getAuthToken()).toBeNull();
    expect(getStoredUser()).toBeNull();
  });

  it('attaches Authorization Bearer header when token exists', async () => {
    const sampleToken = 'test-bearer-token-123';
    setAuth(sampleToken, { user_id: 'U001' });

    let capturedHeaders = null;
    vi.stubGlobal('fetch', vi.fn().mockImplementation((url, options) => {
      capturedHeaders = options.headers;
      return Promise.resolve({
        ok: true,
        status: 200,
        headers: new Headers({ 'content-type': 'application/json' }),
        json: () => Promise.resolve({ status: 'ok' })
      });
    }));

    await apiRequest('/api/test');
    expect(capturedHeaders.get('Authorization')).toBe(`Bearer ${sampleToken}`);
  });

  it('triggers onUnauthorized and clears storage on HTTP 401 response', async () => {
    setAuth('expired-token', { user_id: 'U002' });

    const unauthorizedSpy = vi.fn();
    const unsubscribe = onUnauthorized(unauthorizedSpy);

    vi.stubGlobal('fetch', vi.fn().mockResolvedValue({
      ok: false,
      status: 401,
      headers: new Headers({ 'content-type': 'application/json' }),
      json: () => Promise.resolve({ detail: 'Token signature invalid.' })
    }));

    await expect(apiRequest('/api/chat')).rejects.toThrow('Token signature invalid.');
    expect(unauthorizedSpy).toHaveBeenCalledTimes(1);
    expect(getAuthToken()).toBeNull();

    unsubscribe();
  });

  it('normalizes 403 Forbidden with proper status code and message', async () => {
    setAuth('valid-token', { user_id: 'U006' });

    vi.stubGlobal('fetch', vi.fn().mockResolvedValue({
      ok: false,
      status: 403,
      headers: new Headers({ 'content-type': 'application/json' }),
      json: () => Promise.resolve({ detail: 'Access denied to department record.' })
    }));

    try {
      await apiRequest('/api/chat', { method: 'POST', body: JSON.stringify({ question: 'payroll' }) });
      expect.fail('Should have thrown an error');
    } catch (err) {
      expect(err.status).toBe(403);
      expect(err.message).toBe('Access denied to department record.');
    }
  });

  it('loginApi sends credentials and persists token & user on success', async () => {
    const mockLoginResponse = {
      access_token: 'auth-jwt-token-xyz',
      token_type: 'bearer',
      expires_in: 28800,
      user: {
        user_id: 'U001',
        name: 'System Admin',
        role: 'finance_manager',
        tenant_id: 'TENANT-001'
      }
    };

    vi.stubGlobal('fetch', vi.fn().mockResolvedValue({
      ok: true,
      status: 200,
      headers: new Headers({ 'content-type': 'application/json' }),
      json: () => Promise.resolve(mockLoginResponse)
    }));

    const result = await loginApi('U001', 'Password123!');
    expect(result.access_token).toBe('auth-jwt-token-xyz');
    expect(getAuthToken()).toBe('auth-jwt-token-xyz');
    expect(getStoredUser().user_id).toBe('U001');
  });

  it('chatApi calls /api/chat with valid question payload and returns citations', async () => {
    setAuth('chat-token', { user_id: 'U001' });

    const mockChatResponse = {
      answer: 'Remote work is permitted 2 days per week [SRC-1].',
      citations: [
        {
          source_id: 'SRC-1',
          source_type: 'pdf',
          filename: 'remote_policy.pdf',
          page_number: 3,
          chunk_id: 'chunk-123'
        }
      ],
      retrieval_count: 1,
      grounded: true,
      latencies: { total_sec: 0.45 }
    };

    vi.stubGlobal('fetch', vi.fn().mockImplementation((url, opts) => {
      expect(url).toContain('/api/chat');
      expect(opts.method).toBe('POST');
      const body = JSON.parse(opts.body);
      expect(body.question).toBe('What is remote work policy?');

      return Promise.resolve({
        ok: true,
        status: 200,
        headers: new Headers({ 'content-type': 'application/json' }),
        json: () => Promise.resolve(mockChatResponse)
      });
    }));

    const res = await chatApi('What is remote work policy?');
    expect(res.grounded).toBe(true);
    expect(res.citations).toHaveLength(1);
    expect(res.citations[0].source_id).toBe('SRC-1');
    expect(formatLatency(res.latencies)).toBe('450 ms');
  });
});

describe('Response Latency & Duration Formatting Utilities', () => {
  it('formats normal millisecond durations under 1000ms correctly', () => {
    expect(formatDurationMs(125)).toBe('125 ms');
    expect(formatDurationMs(999)).toBe('999 ms');
  });

  it('formats durations of at least one second as seconds with 2 decimals', () => {
    expect(formatDurationMs(1000)).toBe('1.00 s');
    expect(formatDurationMs(8568)).toBe('8.57 s');
    expect(formatDurationMs(8662)).toBe('8.66 s');
    expect(formatDurationMs(14042)).toBe('14.04 s');
    expect(formatDurationMs(60000)).toBe('60.00 s');
  });

  it('handles unit boundaries consistently without 1000ms artifact', () => {
    expect(formatDurationMs(999.4)).toBe('999 ms');
    expect(formatDurationMs(999.5)).toBe('1.00 s');
    expect(formatDurationMs(1000.0)).toBe('1.00 s');
  });

  it('handles zero correctly as 0 ms', () => {
    expect(formatDurationMs(0)).toBe('0 ms');
    expect(formatDurationSec(0)).toBe('0 ms');
  });

  it('returns null for missing, null, undefined, negative, or non-finite values', () => {
    expect(formatDurationMs(null)).toBeNull();
    expect(formatDurationMs(undefined)).toBeNull();
    expect(formatDurationMs(-500)).toBeNull();
    expect(formatDurationMs(NaN)).toBeNull();
    expect(formatDurationMs(Infinity)).toBeNull();
  });

  it('formats latencies metadata object from real API responses', () => {
    // Semantic RAG pipeline (total_sec)
    expect(formatLatency({ total_sec: 14.042 })).toBe('14.04 s');
    expect(formatLatency({ total_sec: 8.568 })).toBe('8.57 s');
    expect(formatLatency({ total_sec: 8.662 })).toBe('8.66 s');
    expect(formatLatency({ total_sec: 0.45 })).toBe('450 ms');

    // Structured / Hybrid query routes (total fallback)
    expect(formatLatency({ total: 0.125, database: 0.05 })).toBe('125 ms');
    expect(formatLatency({ total: 1.25, database: 0.1 })).toBe('1.25 s');

    // Missing or invalid metadata
    expect(formatLatency(null)).toBeNull();
    expect(formatLatency({})).toBeNull();
    expect(formatLatency({ total_sec: -1 })).toBeNull();
    expect(formatLatency({ total_sec: NaN })).toBeNull();
  });

  it('ensures each chat response displays its own measured value independently', () => {
    const responses = [
      { sender: 'assistant', latencies: { total_sec: 14.042 } },
      { sender: 'assistant', latencies: { total_sec: 8.568 } },
      { sender: 'assistant', latencies: { total_sec: 0.125 } },
      { sender: 'assistant', latencies: {} }
    ];

    const formatted = responses.map((r) => formatLatency(r.latencies));
    expect(formatted).toEqual(['14.04 s', '8.57 s', '125 ms', null]);
  });
});

