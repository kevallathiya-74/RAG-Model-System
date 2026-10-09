import React from 'react';

/**
 * Citation Display Component
 * Renders verified citation metadata returned strictly by backend.
 * Never fabricates source data or bypasses authorization.
 */
export function Citations({ citations }) {
  if (!citations || citations.length === 0) {
    return null;
  }

  return (
    <div className="citations-container" aria-label="Cited sources">
      <div className="citations-header">
        <span className="citations-title">
          <svg
            className="icon-small"
            viewBox="0 0 20 20"
            fill="currentColor" 
            aria-hidden="true"
          >
            <path
              fillRule="evenodd"
              d="M4 4a2 2 0 012-2h4.586A2 2 0 0112 2.586L15.414 6A2 2 0 0116 7.414V16a2 2 0 01-2 2H6a2 2 0 01-2-2V4zm2 6a1 1 0 011-1h6a1 1 0 110 2H7a1 1 0 01-1-1zm1 3a1 1 0 100 2h6a1 1 0 100-2H7z"
              clipRule="evenodd"
            />
          </svg>
          Grounded Sources ({citations.length})
        </span>
      </div>

      <div className="citations-list" role="list">
        {citations.map((c, index) => {
          const sourceId = c.source_id || `SRC-${index + 1}`;
          const isStructured = c.source_type === 'structured' || c.source_type === 'database' || !!c.table;
          const isImage = c.source_type === 'image' || !!c.image_id;

          return (
            <div key={`${sourceId}-${index}`} className="citation-card" role="listitem">
              <div className="citation-badge-row">
                <span className="citation-tag">{sourceId}</span>
                <span className={`type-badge ${isStructured ? 'type-db' : isImage ? 'type-img' : 'type-doc'}`}>
                  {c.source_type || (isStructured ? 'Database' : 'Document')}
                </span>
                {c.authorized !== undefined && (
                  <span className={`auth-badge ${c.authorized ? 'auth-ok' : 'auth-denied'}`}>
                    {c.authorized ? 'Authorized' : 'Restricted'}
                  </span>
                )}
              </div>

              <div className="citation-meta">
                {c.filename && (
                  <div className="meta-item">
                    <span className="meta-label">File:</span>
                    <span className="meta-value">{c.filename}</span>
                  </div>
                )}

                {c.page_number !== undefined && c.page_number !== null && (
                  <div className="meta-item">
                    <span className="meta-label">Page:</span>
                    <span className="meta-value">{c.page_number}</span>
                  </div>
                )}

                {c.image_id && (
                  <div className="meta-item">
                    <span className="meta-label">Image ID:</span>
                    <span className="meta-value">{c.image_id}</span>
                  </div>
                )}

                {c.table && (
                  <div className="meta-item">
                    <span className="meta-label">Table:</span>
                    <span className="meta-value">{c.table}</span>
                  </div>
                )}

                {c.query_type && (
                  <div className="meta-item">
                    <span className="meta-label">Query Type:</span>
                    <span className="meta-value">{c.query_type}</span>
                  </div>
                )}

                {c.record_ids && c.record_ids.length > 0 && (
                  <div className="meta-item">
                    <span className="meta-label">Record IDs:</span>
                    <span className="meta-value">{c.record_ids.join(', ')}</span>
                  </div>
                )}

                {c.fields && c.fields.length > 0 && (
                  <div className="meta-item">
                    <span className="meta-label">Fields:</span>
                    <span className="meta-value">{c.fields.join(', ')}</span>
                  </div>
                )}

                {c.chunk_id && (
                  <div className="meta-item">
                    <span className="meta-label">Chunk:</span>
                    <span className="meta-value chunk-code">{c.chunk_id.slice(0, 16)}...</span>
                  </div>
                )}
              </div>
            </div>
          );
        })}
      </div>
    </div>
  );
}
