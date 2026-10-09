import React, { useState, useEffect } from 'react';
import {
  getAdminAuditLogsApi,
  getAdminUsersApi,
  updateAdminUserStatusApi,
  updateAdminUserRoleApi,
  getAdminDocumentsApi,
  grantDocumentPermissionApi
} from '../api/client.js';

const CANONICAL_ROLES = ['student', 'faculty', 'finance_manager', 'admin'];

export function Admin({ user }) {
  const [subTab, setSubTab] = useState('audit'); // 'audit', 'users', 'documents'
  const [errorBanner, setErrorBanner] = useState('');
  const [successBanner, setSuccessBanner] = useState('');

  // Audit Logs State
  const [auditLogs, setAuditLogs] = useState([]);
  const [auditPage, setAuditPage] = useState(1);
  const [auditPageSize, setAuditPageSize] = useState(20);
  const [auditTotalPages, setAuditTotalPages] = useState(1);
  const [auditTotalItems, setAuditTotalItems] = useState(0);
  const [auditActionFilter, setAuditActionFilter] = useState('');
  const [auditResultFilter, setAuditResultFilter] = useState('');
  const [loadingAudit, setLoadingAudit] = useState(false);

  // Users Administration State
  const [adminUsers, setAdminUsers] = useState([]);
  const [loadingUsers, setLoadingUsers] = useState(false);
  const [updatingUserId, setUpdatingUserId] = useState(null);

  // Documents Administration State
  const [adminDocuments, setAdminDocuments] = useState([]);
  const [loadingDocs, setLoadingDocs] = useState(false);
  const [permDocId, setPermDocId] = useState('');
  const [permRole, setPermRole] = useState('faculty');
  const [permUserId, setPermUserId] = useState('');
  const [grantingPerm, setGrantingPerm] = useState(false);

  // Fetch Audit Logs
  const fetchAuditLogs = async (page = auditPage) => {
    setLoadingAudit(true);
    setErrorBanner('');
    try {
      const data = await getAdminAuditLogsApi({
        page,
        pageSize: auditPageSize,
        action: auditActionFilter.trim() || null,
        result: auditResultFilter.trim() || null
      });
      setAuditLogs(data.items || []);
      setAuditPage(data.page || 1);
      setAuditTotalPages(data.total_pages || 1);
      setAuditTotalItems(data.total_items || 0);
    } catch (err) {
      setErrorBanner(err.message || 'Failed to load security audit logs.');
    } finally {
      setLoadingAudit(false);
    }
  };

  // Fetch Users
  const fetchUsers = async () => {
    setLoadingUsers(true);
    setErrorBanner('');
    try {
      const data = await getAdminUsersApi();
      setAdminUsers(data || []);
    } catch (err) {
      setErrorBanner(err.message || 'Failed to load tenant users.');
    } finally {
      setLoadingUsers(false);
    }
  };

  // Fetch Documents
  const fetchDocuments = async () => {
    setLoadingDocs(true);
    setErrorBanner('');
    try {
      const data = await getAdminDocumentsApi();
      setAdminDocuments(data || []);
    } catch (err) {
      setErrorBanner(err.message || 'Failed to load document permissions.');
    } finally {
      setLoadingDocs(false);
    }
  };

  useEffect(() => {
    if (subTab === 'audit') {
      fetchAuditLogs(1);
    } else if (subTab === 'users') {
      fetchUsers();
    } else if (subTab === 'documents') {
      fetchDocuments();
    }
  }, [subTab]);

  const handleAuditFilterSubmit = (e) => {
    e.preventDefault();
    setAuditPage(1);
    fetchAuditLogs(1);
  };

  const handleToggleUserStatus = async (targetUser) => {
    if (targetUser.user_id === user.user_id) {
      setErrorBanner('Self-deactivation is prohibited for administrator accounts.');
      return;
    }
    const newStatus = !targetUser.is_active;
    setUpdatingUserId(targetUser.user_id);
    setErrorBanner('');
    setSuccessBanner('');
    try {
      await updateAdminUserStatusApi(targetUser.user_id, newStatus);
      setSuccessBanner(`User "${targetUser.user_id}" status updated to ${newStatus ? 'Active' : 'Deactivated'}.`);
      fetchUsers();
    } catch (err) {
      setErrorBanner(err.message || 'Failed to update user status.');
    } finally {
      setUpdatingUserId(null);
    }
  };

  const handleRoleChange = async (targetUserId, newRole) => {
    if (targetUserId === user.user_id && newRole !== 'admin') {
      setErrorBanner('Demoting your own administrator account is prohibited.');
      return;
    }
    setUpdatingUserId(targetUserId);
    setErrorBanner('');
    setSuccessBanner('');
    try {
      await updateAdminUserRoleApi(targetUserId, newRole);
      setSuccessBanner(`User "${targetUserId}" role updated to "${newRole}".`);
      fetchUsers();
    } catch (err) {
      setErrorBanner(err.message || 'Failed to update user role.');
    } finally {
      setUpdatingUserId(null);
    }
  };

  const handleGrantPermission = async (e) => {
    e.preventDefault();
    if (!permDocId) {
      setErrorBanner('Please select a document ID.');
      return;
    }
    setGrantingPerm(true);
    setErrorBanner('');
    setSuccessBanner('');
    try {
      await grantDocumentPermissionApi(permDocId, {
        targetRole: permRole || null,
        targetUserId: permUserId.trim() || null
      });
      setSuccessBanner(`Permission granted on document "${permDocId}".`);
      setPermUserId('');
      fetchDocuments();
    } catch (err) {
      setErrorBanner(err.message || 'Failed to grant document permission.');
    } finally {
      setGrantingPerm(false);
    }
  };

  return (
    <div className="admin-interface">
      <div className="admin-header-card">
        <div>
          <h2 className="section-title">Administrator Control Center</h2>
          <p className="section-desc">
            Tenant-isolated security auditing, role governance, and resource permission controls.
          </p>
        </div>
        <div className="admin-subtabs-nav" role="tablist" aria-label="Administrator views">
          <button
            type="button"
            className={`btn btn-sm ${subTab === 'audit' ? 'btn-primary' : 'btn-secondary'}`}
            onClick={() => setSubTab('audit')}
            role="tab"
            aria-selected={subTab === 'audit'}
          >
            Audit Logs
          </button>
          <button
            type="button"
            className={`btn btn-sm ${subTab === 'users' ? 'btn-primary' : 'btn-secondary'}`}
            onClick={() => setSubTab('users')}
            role="tab"
            aria-selected={subTab === 'users'}
          >
            User Administration
          </button>
          <button
            type="button"
            className={`btn btn-sm ${subTab === 'documents' ? 'btn-primary' : 'btn-secondary'}`}
            onClick={() => setSubTab('documents')}
            role="tab"
            aria-selected={subTab === 'documents'}
          >
            Document Permissions
          </button>
        </div>
      </div>

      {errorBanner && (
        <div className="alert-box alert-error" role="alert" style={{ marginTop: '16px' }}>
          <span>{errorBanner}</span>
        </div>
      )}

      {successBanner && (
        <div className="alert-box alert-success" role="status" style={{ marginTop: '16px' }}>
          <span>{successBanner}</span>
        </div>
      )}

      {/* Subtab 1: Security Audit Logs */}
      {subTab === 'audit' && (
        <section className="doc-section" style={{ marginTop: '16px' }} aria-labelledby="audit-logs-heading">
          <div className="docs-list-header">
            <div>
              <h3 id="audit-logs-heading" className="section-title">
                Security Audit Inspection ({auditTotalItems} Total Events)
              </h3>
              <p className="section-desc">
                Immutable audit trail with sanitization against secret and PII leakage.
              </p>
            </div>
            <button
              type="button"
              onClick={() => fetchAuditLogs(auditPage)}
              disabled={loadingAudit}
              className="btn btn-secondary btn-sm"
            >
              {loadingAudit ? 'Refreshing...' : 'Refresh Logs'}
            </button>
          </div>

          <form onSubmit={handleAuditFilterSubmit} className="form-row" style={{ marginTop: '12px', alignItems: 'flex-end' }}>
            <div className="form-group flex-1">
              <label htmlFor="audit-action-filter" className="form-label">Action Filter</label>
              <input
                id="audit-action-filter"
                type="text"
                placeholder="e.g. login_success, authorization_denied"
                value={auditActionFilter}
                onChange={(e) => setAuditActionFilter(e.target.value)}
                className="form-input"
              />
            </div>
            <div className="form-group flex-1">
              <label htmlFor="audit-result-filter" className="form-label">Result</label>
              <select
                id="audit-result-filter"
                value={auditResultFilter}
                onChange={(e) => setAuditResultFilter(e.target.value)}
                className="form-select"
              >
                <option value="">All Results</option>
                <option value="authorized">authorized</option>
                <option value="denied">denied</option>
                <option value="failed">failed</option>
              </select>
            </div>
            <div className="form-group">
              <button type="submit" disabled={loadingAudit} className="btn btn-primary">
                Apply Filters
              </button>
            </div>
          </form>

          {loadingAudit ? (
            <div className="loading-state-box">
              <span className="spinner" aria-hidden="true" />
              <p>Querying audit records from PostgreSQL...</p>
            </div>
          ) : auditLogs.length === 0 ? (
            <div className="empty-state-box">
              <p>No audit events match the selected criteria.</p>
            </div>
          ) : (
            <>
              <div className="table-responsive" style={{ marginTop: '16px' }}>
                <table className="doc-table">
                  <thead>
                    <tr>
                      <th scope="col">ID</th>
                      <th scope="col">Timestamp</th>
                      <th scope="col">User</th>
                      <th scope="col">Action</th>
                      <th scope="col">Resource</th>
                      <th scope="col">Result</th>
                      <th scope="col">Latency</th>
                      <th scope="col">Metadata</th>
                    </tr>
                  </thead>
                  <tbody>
                    {auditLogs.map((log) => (
                      <tr key={log.id}>
                        <td className="font-mono text-xs">{log.id}</td>
                        <td className="font-mono text-xs" style={{ whiteSpace: 'nowrap' }}>
                          {log.timestamp ? new Date(log.timestamp).toLocaleString() : '-'}
                        </td>
                        <td className="font-semibold">{log.user_id}</td>
                        <td className="font-mono text-xs">{log.action}</td>
                        <td>
                          <span className="badge-pill pill-neutral">
                            {log.resource_type}{log.resource_id ? `: ${log.resource_id}` : ''}
                          </span>
                        </td>
                        <td>
                          <span className={`badge-pill ${log.result === 'authorized' ? 'pill-success' : 'pill-error'}`}>
                            {log.result}
                          </span>
                        </td>
                        <td className="font-mono text-xs">{log.latency_ms != null ? `${log.latency_ms}ms` : '-'}</td>
                        <td className="font-mono text-xs" style={{ maxWidth: '280px', overflow: 'hidden', textOverflow: 'ellipsis' }}>
                          {JSON.stringify(log.metadata || {})}
                        </td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              </div>

              {/* Pagination Controls */}
              <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginTop: '16px' }}>
                <span className="text-sm text-muted">
                  Page {auditPage} of {auditTotalPages} ({auditTotalItems} items)
                </span>
                <div style={{ display: 'flex', gap: '8px' }}>
                  <button
                    type="button"
                    onClick={() => fetchAuditLogs(auditPage - 1)}
                    disabled={auditPage <= 1 || loadingAudit}
                    className="btn btn-secondary btn-sm"
                  >
                    Previous
                  </button>
                  <button
                    type="button"
                    onClick={() => fetchAuditLogs(auditPage + 1)}
                    disabled={auditPage >= auditTotalPages || loadingAudit}
                    className="btn btn-secondary btn-sm"
                  >
                    Next
                  </button>
                </div>
              </div>
            </>
          )}
        </section>
      )}

      {/* Subtab 2: User Administration */}
      {subTab === 'users' && (
        <section className="doc-section" style={{ marginTop: '16px' }} aria-labelledby="users-heading">
          <div className="docs-list-header">
            <div>
              <h3 id="users-heading" className="section-title">
                Tenant User & Role Governance
              </h3>
              <p className="section-desc">
                Enforce the authoritative four-role model and manage active account lifecycle.
              </p>
            </div>
            <button
              type="button"
              onClick={fetchUsers}
              disabled={loadingUsers}
              className="btn btn-secondary btn-sm"
            >
              {loadingUsers ? 'Refreshing...' : 'Refresh Users'}
            </button>
          </div>

          {loadingUsers ? (
            <div className="loading-state-box">
              <span className="spinner" aria-hidden="true" />
              <p>Loading tenant users...</p>
            </div>
          ) : (
            <div className="table-responsive" style={{ marginTop: '16px' }}>
              <table className="doc-table">
                <thead>
                  <tr>
                    <th scope="col">User ID</th>
                    <th scope="col">Name</th>
                    <th scope="col">Department</th>
                    <th scope="col">Canonical Role</th>
                    <th scope="col">Status</th>
                    <th scope="col">Actions</th>
                  </tr>
                </thead>
                <tbody>
                  {adminUsers.map((u) => (
                    <tr key={u.user_id}>
                      <td className="font-mono text-xs">{u.user_id}</td>
                      <td className="font-semibold">{u.name}</td>
                      <td>{u.department || 'N/A'}</td>
                      <td>
                        <select
                          value={u.role}
                          onChange={(e) => handleRoleChange(u.user_id, e.target.value)}
                          disabled={updatingUserId === u.user_id || u.user_id === user.user_id}
                          className="form-select"
                          style={{ padding: '4px 8px', fontSize: '0.85rem' }}
                        >
                          {CANONICAL_ROLES.map((r) => (
                            <option key={r} value={r}>
                              {r}
                            </option>
                          ))}
                        </select>
                      </td>
                      <td>
                        <span className={`badge-pill ${u.is_active ? 'pill-success' : 'pill-error'}`}>
                          {u.is_active ? 'Active' : 'Deactivated'}
                        </span>
                      </td>
                      <td>
                        <button
                          type="button"
                          onClick={() => handleToggleUserStatus(u)}
                          disabled={updatingUserId === u.user_id || u.user_id === user.user_id}
                          className={`btn btn-sm ${u.is_active ? 'btn-secondary' : 'btn-primary'}`}
                        >
                          {updatingUserId === u.user_id
                            ? 'Updating...'
                            : u.is_active
                            ? 'Deactivate'
                            : 'Activate'}
                        </button>
                      </td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          )}
        </section>
      )}

      {/* Subtab 3: Document Permissions */}
      {subTab === 'documents' && (
        <section className="doc-section" style={{ marginTop: '16px' }} aria-labelledby="documents-acl-heading">
          <div className="docs-list-header">
            <div>
              <h3 id="documents-acl-heading" className="section-title">
                Document ACL Governance & Review
              </h3>
              <p className="section-desc">
                Inspect document-level access grants and add explicit role or user authorizations.
              </p>
            </div>
            <button
              type="button"
              onClick={fetchDocuments}
              disabled={loadingDocs}
              className="btn btn-secondary btn-sm"
            >
              {loadingDocs ? 'Refreshing...' : 'Refresh Documents'}
            </button>
          </div>

          {/* Grant Permission Form */}
          <form onSubmit={handleGrantPermission} className="form-row" style={{ marginTop: '16px', background: 'var(--color-surface)', padding: '16px', borderRadius: 'var(--radius-md)', border: '1px solid var(--color-border)', alignItems: 'flex-end' }}>
            <div className="form-group flex-2">
              <label htmlFor="perm-doc-select" className="form-label">Document ID</label>
              <select
                id="perm-doc-select"
                value={permDocId}
                onChange={(e) => setPermDocId(e.target.value)}
                className="form-select"
              >
                <option value="">-- Select Document --</option>
                {adminDocuments.map((d) => (
                  <option key={d.document_id} value={d.document_id}>
                    {d.document_id} ({d.filename})
                  </option>
                ))}
              </select>
            </div>

            <div className="form-group flex-1">
              <label htmlFor="perm-role-select" className="form-label">Grant Role</label>
              <select
                id="perm-role-select"
                value={permRole}
                onChange={(e) => setPermRole(e.target.value)}
                className="form-select"
              >
                <option value="">(None - Specific User Only)</option>
                {CANONICAL_ROLES.map((r) => (
                  <option key={r} value={r}>{r}</option>
                ))}
              </select>
            </div>

            <div className="form-group flex-1">
              <label htmlFor="perm-user-input" className="form-label">Or Specific User ID</label>
              <input
                id="perm-user-input"
                type="text"
                placeholder="e.g. U1001"
                value={permUserId}
                onChange={(e) => setPermUserId(e.target.value)}
                className="form-input"
              />
            </div>

            <div className="form-group">
              <button type="submit" disabled={grantingPerm || !permDocId} className="btn btn-primary">
                {grantingPerm ? 'Granting...' : 'Grant Access'}
              </button>
            </div>
          </form>

          {loadingDocs ? (
            <div className="loading-state-box">
              <span className="spinner" aria-hidden="true" />
              <p>Loading document ACLs...</p>
            </div>
          ) : (
            <div className="table-responsive" style={{ marginTop: '16px' }}>
              <table className="doc-table">
                <thead>
                  <tr>
                    <th scope="col">Document ID</th>
                    <th scope="col">Filename</th>
                    <th scope="col">Sensitivity</th>
                    <th scope="col">Owner</th>
                    <th scope="col">Allowed Roles</th>
                    <th scope="col">Allowed Users</th>
                    <th scope="col">Chunks</th>
                  </tr>
                </thead>
                <tbody>
                  {adminDocuments.map((d) => (
                    <tr key={d.document_id}>
                      <td className="font-mono text-xs">{d.document_id}</td>
                      <td className="font-medium">{d.filename}</td>
                      <td>
                        <span className="badge-pill pill-neutral">{d.sensitivity}</span>
                      </td>
                      <td>{d.owner_user_id || 'System'}</td>
                      <td>
                        <div style={{ display: 'flex', gap: '4px', flexWrap: 'wrap' }}>
                          {d.allowed_roles && d.allowed_roles.length > 0 ? (
                            d.allowed_roles.map((r) => (
                              <span key={r} className="badge-pill pill-doc text-xs">
                                {r}
                              </span>
                            ))
                          ) : (
                            <span className="text-muted text-xs">None</span>
                          )}
                        </div>
                      </td>
                      <td>
                        <div style={{ display: 'flex', gap: '4px', flexWrap: 'wrap' }}>
                          {d.allowed_users && d.allowed_users.length > 0 ? (
                            d.allowed_users.map((u) => (
                              <span key={u} className="badge-pill pill-db text-xs">
                                {u}
                              </span>
                            ))
                          ) : (
                            <span className="text-muted text-xs">All Role Members</span>
                          )}
                        </div>
                      </td>
                      <td>{d.chunk_count}</td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          )}
        </section>
      )}
    </div>
  );
}
