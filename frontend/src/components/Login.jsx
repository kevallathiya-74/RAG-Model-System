import React, { useState } from 'react';
import { loginApi } from '../api/client.js';

export function Login({ onLoginSuccess }) {
  const [username, setUsername] = useState('');
  const [password, setPassword] = useState('');
  const [loading, setLoading] = useState(false);
  const [errorMessage, setErrorMessage] = useState('');
  const [fieldErrors, setFieldErrors] = useState({});

  const validate = () => {
    const errors = {};
    if (!username.trim()) {
      errors.username = 'User ID or username is required.';
    }
    if (!password) {
      errors.password = 'Password is required.';
    }
    setFieldErrors(errors);
    return Object.keys(errors).length === 0;
  };

  const handleSubmit = async (e) => {
    e.preventDefault();
    setErrorMessage('');

    if (!validate()) {
      return;
    }

    setLoading(true);
    try {
      const response = await loginApi(username.trim(), password);
      // Clean up sensitive state in memory
      setPassword('');
      if (onLoginSuccess) {
        onLoginSuccess(response.user);
      }
    } catch (err) {
      if (err.status === 401) {
        setErrorMessage('Invalid username or password.');
      } else if (err.status === 403) {
        setErrorMessage('Your account is deactivated. Contact an administrator.');
      } else if (err.status === 429) {
        setErrorMessage('Too many login attempts. Please wait 60 seconds.');
      } else {
        setErrorMessage(err.message || 'Authentication failed. Please verify credentials.');
      }
    } finally {
      setLoading(false);
    }
  };

  return (
    <div className="login-card-container">
      <div className="login-card">
        <div className="login-header">
          <div className="security-icon-circle" aria-hidden="true">
            <svg viewBox="0 0 24 24" width="28" height="28" fill="none" stroke="currentColor" strokeWidth="2">
              <rect x="3" y="11" width="18" height="11" rx="2" ry="2" />
              <path d="M7 11V7a5 5 0 0 1 10 0v4" />
            </svg>
          </div>
          <h1 className="login-title">Secure RAG System</h1>
          <p className="login-subtitle">
            Authoritative Identity & Access-Controlled Multi-Modal Intelligence
          </p>
        </div>

        {errorMessage && (
          <div className="alert-box alert-error" role="alert" aria-live="assertive">
            <svg className="icon-small alert-icon" viewBox="0 0 20 20" fill="currentColor" aria-hidden="true">
              <path
                fillRule="evenodd"
                d="M10 18a8 8 0 100-16 8 8 0 000 16zM8.707 7.293a1 1 0 00-1.414 1.414L8.586 10l-1.293 1.293a1 1 0 101.414 1.414L10 11.414l1.293 1.293a1 1 0 001.414-1.414L11.414 10l1.293-1.293a1 1 0 00-1.414-1.414L10 8.586 8.707 7.293z"
                clipRule="evenodd"
              />
            </svg>
            <span>{errorMessage}</span>
          </div>
        )}

        <form onSubmit={handleSubmit} noValidate className="login-form">
          <div className="form-group">
            <label htmlFor="username" className="form-label">
              User ID or Username
            </label>
            <input
              id="username"
              type="text"
              name="username"
              value={username}
              onChange={(e) => {
                setUsername(e.target.value);
                if (fieldErrors.username) {
                  setFieldErrors((prev) => ({ ...prev, username: null }));
                }
              }}
              placeholder="e.g., U001, U1001, U2001..."
              autoComplete="username"
              autoFocus
              disabled={loading}
              className={`form-input ${fieldErrors.username ? 'input-error' : ''}`}
              aria-required="true"
              aria-invalid={!!fieldErrors.username}
              aria-describedby={fieldErrors.username ? 'username-error' : undefined}
            />
            {fieldErrors.username && (
              <span id="username-error" className="field-error-text" role="alert">
                {fieldErrors.username}
              </span>
            )}
          </div>

          <div className="form-group">
            <label htmlFor="password" className="form-label">
              Password
            </label>
            <input
              id="password"
              type="password"
              name="password"
              value={password}
              onChange={(e) => {
                setPassword(e.target.value);
                if (fieldErrors.password) {
                  setFieldErrors((prev) => ({ ...prev, password: null }));
                }
              }}
              placeholder="Enter Password"
              autoComplete="current-password"
              disabled={loading}
              className={`form-input ${fieldErrors.password ? 'input-error' : ''}`}
              aria-required="true"
              aria-invalid={!!fieldErrors.password}
              aria-describedby={fieldErrors.password ? 'password-error' : undefined}
            />
            {fieldErrors.password && (
              <span id="password-error" className="field-error-text" role="alert">
                {fieldErrors.password}
              </span>
            )}
          </div>

          <button
            type="submit"
            disabled={loading}
            className="btn btn-primary btn-block"
            aria-busy={loading}
          >
            {loading ? (
              <span className="btn-loading-content">
                <span className="spinner" aria-hidden="true" />
                Authenticating...
              </span>
            ) : (
              'Sign In'
            )}
          </button>
        </form>
      </div>
    </div>
  );
}
