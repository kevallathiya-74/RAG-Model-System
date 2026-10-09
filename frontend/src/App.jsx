import React, { useState, useEffect } from 'react';
import { getStoredUser, clearAuth, onUnauthorized, getAuthToken } from './api/client.js';
import { Login } from './components/Login.jsx';
import { Chat } from './components/Chat.jsx';
import { Documents } from './components/Documents.jsx';

const formatRoleName = (role) => {
  if (role === 'student') return 'Student';
  if (role === 'faculty') return 'Faculty';
  if (role === 'finance_manager') return 'Finance Manager (Fee Collector)';
  return role;
};

export default function App() {
  const [user, setUser] = useState(() => getStoredUser());
  const [activeTab, setActiveTab] = useState('chat');

  useEffect(() => {
    // Check if token exists
    const token = getAuthToken();
    if (!token) {
      setUser(null);
    }

    // Subscribe to 401 unauthorized events from API client
    const unsubscribe = onUnauthorized(() => {
      setUser(null);
    });

    return () => {
      unsubscribe();
    };
  }, []);

  const handleLoginSuccess = (userData) => {
    setUser(userData);
    setActiveTab('chat');
  };

  const handleLogout = () => {
    clearAuth();
    setUser(null);
    setActiveTab('chat');
  };

  return (
    <div className="app-container">
      <header className="app-header">
        <div className="header-branding">
          <div className="brand-logo" aria-hidden="true">
            <svg viewBox="0 0 24 24" width="22" height="22" fill="none" stroke="currentColor" strokeWidth="2.2">
              <path d="M12 2L2 7l10 5 10-5-10-5z" />
              <path d="M2 17l10 5 10-5" />
              <path d="M2 12l10 5 10-5" />
            </svg>
          </div>
          <div>
            <h1 className="brand-title">Secure Multi-Modal RAG</h1>
            <p className="brand-subtitle">Retrieval-Layer JWT Authorization & Grounded Citations</p>
          </div>
        </div>

        {user && (
          <div className="header-user-controls">
            <div className="user-profile-summary" aria-label="Current authenticated session">
              <span className="user-name">{user.name}</span>
              <span className="user-role-badge">{formatRoleName(user.role)}</span>
              {user.department && (
                <span className="user-dept-badge">{user.department}</span>
              )}
              <span className="user-tenant-badge">{user.tenant_id}</span>
            </div>

            <button
              type="button"
              onClick={handleLogout}
              className="btn btn-secondary btn-sm btn-logout"
              aria-label="Sign out of current session"
            >
              Sign Out
            </button>
          </div>
        )}
      </header>

      {user && (
        <nav className="app-tabs-nav" aria-label="Main application sections">
          <button
            type="button"
            className={`tab-btn ${activeTab === 'chat' ? 'tab-btn-active' : ''}`}
            onClick={() => setActiveTab('chat')}
            aria-selected={activeTab === 'chat'}
            role="tab"
          >
            <svg viewBox="0 0 20 20" fill="currentColor" width="16" height="16" aria-hidden="true">
              <path
                fillRule="evenodd"
                d="M18 10c0 3.866-3.582 7-8 7a8.841 8.841 0 01-4.083-.98L2 17l1.338-3.123C2.493 12.767 2 11.434 2 10c0-3.866 3.582-7 8-7s8 3.134 8 7zM7 9H5v2h2V9zm8 0h-2v2h2V9zm-5 0h-2v2h2V9z"
                clipRule="evenodd"
              />
            </svg>
            Secure RAG Chat
          </button>
          <button
            type="button"
            className={`tab-btn ${activeTab === 'documents' ? 'tab-btn-active' : ''}`}
            onClick={() => setActiveTab('documents')}
            aria-selected={activeTab === 'documents'}
            role="tab"
          >
            <svg viewBox="0 0 20 20" fill="currentColor" width="16" height="16" aria-hidden="true">
              <path
                fillRule="evenodd"
                d="M4 4a2 2 0 012-2h4.586A2 2 0 0112 2.586L15.414 6A2 2 0 0116 7.414V16a2 2 0 01-2 2H6a2 2 0 01-2-2V4z"
                clipRule="evenodd"
              />
            </svg>
            Authorized Documents
          </button>
        </nav>
      )}

      <main className="app-main">
        {!user ? (
          <Login onLoginSuccess={handleLoginSuccess} />
        ) : activeTab === 'chat' ? (
          <Chat user={user} />
        ) : (
          <Documents user={user} />
        )}
      </main>

      <footer className="app-footer">
        <span>Authoritative Identity: PostgreSQL</span>
        <span className="footer-separator">•</span>
        <span>Vector ACL: Qdrant Cloud</span>
        <span className="footer-separator">•</span>
        <span>LLM: Local Gemma 3 1B</span>
      </footer>
    </div>
  );
}
