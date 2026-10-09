import React, { useState, useEffect } from 'react';
import { getDocumentsApi, uploadDocumentApi } from '../api/client.js';

export function Documents({ user }) {
  const [documents, setDocuments] = useState([]);
  const [totalCount, setTotalCount] = useState(0);
  const [loading, setLoading] = useState(true);
  const [uploading, setUploading] = useState(false);
  const [errorBanner, setErrorBanner] = useState('');
  const [successBanner, setSuccessBanner] = useState('');

  // Upload state
  const [selectedFile, setSelectedFile] = useState(null);
  const [sensitivity, setSensitivity] = useState('internal');
  const [allowedRoles, setAllowedRoles] = useState('');

  const fetchDocuments = async () => {
    setLoading(true);
    setErrorBanner('');
    try {
      const data = await getDocumentsApi();
      setDocuments(data.documents || []);
      setTotalCount(data.total || 0);
    } catch (err) {
      if (err.status === 401) {
        setErrorBanner('Your session has expired. Please sign in again.');
      } else if (err.status === 403) {
        setErrorBanner('Access forbidden. You do not have permission to view documents.');
      } else {
        setErrorBanner(err.message || 'Failed to load documents.');
      }
    } finally {
      setLoading(false);
    }
  };

  useEffect(() => {
    fetchDocuments();
  }, []);

  const handleFileChange = (e) => {
    const file = e.target.files[0];
    if (file) {
      setSelectedFile(file);
      setSuccessBanner('');
      setErrorBanner('');
    }
  };

  const handleUpload = async (e) => {
    e.preventDefault();
    if (!selectedFile || uploading) {
      return;
    }

    setUploading(true);
    setErrorBanner('');
    setSuccessBanner('');

    const formData = new FormData();
    formData.append('file', selectedFile);
    formData.append('sensitivity', sensitivity);
    if (allowedRoles.trim()) {
      formData.append('allowed_roles', allowedRoles.trim());
    }

    try {
      const result = await uploadDocumentApi(formData);
      setSuccessBanner(
        `Successfully ingested "${result.filename}" (${result.source_type}). Created ${result.chunk_count} vector chunks.`
      );
      setSelectedFile(null);
      // Reset input element
      const fileInput = document.getElementById('doc-file-upload');
      if (fileInput) fileInput.value = '';
      // Refresh list from backend
      fetchDocuments();
    } catch (err) {
      if (err.status === 403) {
        setErrorBanner('Permission denied: You do not have authorization to upload documents.');
      } else if (err.status === 413) {
        setErrorBanner('File too large: Maximum allowed size is 20MB.');
      } else if (err.status === 429) {
        setErrorBanner('Rate limit reached for file ingestion. Please wait before retrying.');
      } else {
        setErrorBanner(err.message || 'Document upload and indexing failed.');
      }
    } finally {
      setUploading(false);
    }
  };

  return (
    <div className="documents-interface">
      {errorBanner && (
        <div className="alert-box alert-error" role="alert" aria-live="assertive">
          <svg className="icon-small alert-icon" viewBox="0 0 20 20" fill="currentColor" aria-hidden="true">
            <path
              fillRule="evenodd"
              d="M10 18a8 8 0 100-16 8 8 0 000 16zM8.707 7.293a1 1 0 00-1.414 1.414L8.586 10l-1.293 1.293a1 1 0 101.414 1.414L10 11.414l1.293 1.293a1 1 0 001.414-1.414L11.414 10l1.293-1.293a1 1 0 00-1.414-1.414L10 8.586 8.707 7.293z"
              clipRule="evenodd"
            />
          </svg>
          <span>{errorBanner}</span>
        </div>
      )}

      {successBanner && (
        <div className="alert-box alert-success" role="status" aria-live="polite">
          <svg className="icon-small alert-icon" viewBox="0 0 20 20" fill="currentColor" aria-hidden="true">
            <path
              fillRule="evenodd"
              d="M10 18a8 8 0 100-16 8 8 0 000 16zM13.707 7.707a1 1 0 00-1.414-1.414L9 9.586 7.707 8.293a1 1 0 00-1.414 1.414l2 2a1 1 0 001.414 0l4-4z"
              clipRule="evenodd"
            />
          </svg>
          <span>{successBanner}</span>
        </div>
      )}

      {/* Upload Section */}
      <section className="doc-section upload-section" aria-labelledby="upload-heading">
        <h2 id="upload-heading" className="section-title">
          Live Multi-Modal Document Ingestion
        </h2>
        <p className="section-desc">
          Upload PDF or image files to extract text/OCR, chunk content, generate embeddings via Ollama, and index with retrieval-layer ACL into Qdrant.
        </p>

        <form onSubmit={handleUpload} className="upload-form">
          <div className="form-row">
            <div className="form-group flex-2">
              <label htmlFor="doc-file-upload" className="form-label">
                Select Document or Image <span aria-hidden="true">*</span>
              </label>
              <input
                id="doc-file-upload"
                type="file"
                accept=".pdf,.png,.jpg,.jpeg"
                onChange={handleFileChange}
                disabled={uploading}
                className="form-input-file"
                aria-required="true"
              />
              <span className="field-hint">Accepted: PDF, PNG, JPG, JPEG (Max 20MB)</span>
            </div>

            <div className="form-group flex-1">
              <label htmlFor="sensitivity-select" className="form-label">
                Sensitivity Classification
              </label>
              <select
                id="sensitivity-select"
                value={sensitivity}
                onChange={(e) => setSensitivity(e.target.value)}
                disabled={uploading}
                className="form-select"
              >
                <option value="internal">Internal</option>
                <option value="confidential">Confidential</option>
                <option value="restricted">Restricted</option>
              </select>
            </div>
          </div>

          <div className="form-row">
            <div className="form-group flex-2">
              <label htmlFor="allowed-roles-input" className="form-label">
                Access Restriction (Optional Roles)
              </label>
              <input
                id="allowed-roles-input"
                type="text"
                value={allowedRoles}
                onChange={(e) => setAllowedRoles(e.target.value)}
                placeholder="e.g. admin, hr_manager (leave blank for default)"
                disabled={uploading}
                className="form-input"
              />
              <span className="field-hint">Comma-separated roles allowed to access document</span>
            </div>

            <div className="form-group flex-1 form-action-align">
              <button
                type="submit"
                disabled={!selectedFile || uploading}
                className="btn btn-primary btn-block"
                aria-busy={uploading}
              >
                {uploading ? (
                  <span className="btn-loading-content">
                    <span className="spinner" aria-hidden="true" />
                    Extracting & Indexing...
                  </span>
                ) : (
                  'Upload & Index'
                )}
              </button>
            </div>
          </div>
        </form>
      </section>

      {/* Document List Section */}
      <section className="doc-section" aria-labelledby="docs-list-heading">
        <div className="docs-list-header">
          <div>
            <h2 id="docs-list-heading" className="section-title">
              Authorized Tenant Documents
            </h2>
            <p className="section-desc">
              List of documents and multi-modal assets authorized for your identity and role.
            </p>
          </div>
          <button
            type="button"
            onClick={fetchDocuments}
            disabled={loading}
            className="btn btn-secondary btn-refresh"
            aria-label="Refresh document list"
          >
            {loading ? <span className="spinner small-spinner" aria-hidden="true" /> : 'Refresh'}
          </button>
        </div>

        {loading ? (
          <div className="loading-state-box">
            <span className="spinner" aria-hidden="true" />
            <p>Loading authorized documents...</p>
          </div>
        ) : documents.length === 0 ? (
          <div className="empty-state-box">
            <svg viewBox="0 0 24 24" width="36" height="36" fill="none" stroke="currentColor" strokeWidth="1.5" aria-hidden="true">
              <path d="M14 2H6a2 2 0 0 0-2 2v16a2 2 0 0 0 2 2h12a2 2 0 0 0 2-2V8z" />
              <polyline points="14 2 14 8 20 8" />
              <line x1="16" y1="13" x2="8" y2="13" />
              <line x1="16" y1="17" x2="8" y2="17" />
              <polyline points="10 9 9 9 8 9" />
            </svg>
            <p>No authorized documents found for your role in this tenant.</p>
          </div>
        ) : (
          <div className="table-responsive">
            <table className="doc-table">
              <thead>
                <tr>
                  <th scope="col">Document ID</th>
                  <th scope="col">Filename</th>
                  <th scope="col">Format</th>
                  <th scope="col">Status</th>
                  <th scope="col">Chunks Indexed</th>
                  <th scope="col">Tenant</th>
                </tr>
              </thead>
              <tbody>
                {documents.map((doc) => (
                  <tr key={doc.document_id}>
                    <td className="font-mono text-xs">{doc.document_id}</td>
                    <td className="font-medium">{doc.filename}</td>
                    <td>
                      <span className={`badge-pill ${doc.source_type === 'pdf' ? 'pill-pdf' : 'pill-img'}`}>
                        {doc.source_type}
                      </span>
                    </td>
                    <td>
                      <span className="badge-pill pill-success">{doc.status || 'indexed'}</span>
                    </td>
                    <td>{doc.chunk_count}</td>
                    <td><span className="badge-pill pill-neutral">{doc.tenant_id}</span></td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        )}
      </section>
    </div>
  );
}
