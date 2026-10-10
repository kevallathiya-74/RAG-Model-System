/**
 * Response time and duration formatting utilities for RAG chat.
 *
 * Implements standard human-readable duration presentation:
 * - < 1000 ms: rounded milliseconds ('X ms', e.g. '125 ms', '999 ms')
 * - >= 1000 ms: seconds with two decimal places ('X.XX s', e.g. '1.00 s', '14.04 s')
 * - Handles boundary conditions cleanly (e.g. 999.6ms rounds up to 1.00s rather than 1000ms)
 * - Returns null for null, undefined, invalid, negative, or non-finite inputs
 */

/**
 * Formats a duration in milliseconds into a readable representation.
 *
 * @param {number} ms - Measured duration in milliseconds
 * @returns {string|null} Formatted duration or null if invalid/negative
 */
export function formatDurationMs(ms) {
  if (typeof ms !== 'number' || !Number.isFinite(ms) || ms < 0) {
    return null;
  }
  const roundedMs = Math.round(ms);
  if (roundedMs < 1000) {
    return `${roundedMs} ms`;
  }
  return `${(ms / 1000).toFixed(2)} s`;
}

/**
 * Formats a duration in seconds into a readable representation.
 *
 * @param {number} sec - Measured duration in seconds
 * @returns {string|null} Formatted duration or null if invalid/negative
 */
export function formatDurationSec(sec) {
  if (typeof sec !== 'number' || !Number.isFinite(sec) || sec < 0) {
    return null;
  }
  return formatDurationMs(sec * 1000);
}

/**
 * Formats response latency from RAG API metadata.
 *
 * Supports:
 * - latencies.total_sec (semantic RAG pipeline, seconds)
 * - latencies.total (hybrid & structured query services, seconds)
 * - direct numeric seconds value
 *
 * @param {Object|number} latencies - Latencies dictionary or duration in seconds
 * @returns {string|null} Formatted latency string or null if absent/invalid
 */
export function formatLatency(latencies) {
  if (latencies == null) {
    return null;
  }
  let rawSec;
  if (typeof latencies === 'number') {
    rawSec = latencies;
  } else if (typeof latencies === 'object') {
    rawSec = latencies.total_sec ?? latencies.total;
  } else {
    return null;
  }

  if (typeof rawSec !== 'number' || !Number.isFinite(rawSec) || rawSec < 0) {
    return null;
  }
  return formatDurationMs(rawSec * 1000);
}
