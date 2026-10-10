import React, { useState, useRef, useEffect } from 'react';
import { chatApi } from '../api/client.js';
import { Citations } from './Citations.jsx';
import { formatLatency } from '../utils/format.js';

function renderInlineFormatting(text) {
  if (!text) return null;
  const parts = [];
  const regex = /(\*\*.*?\*\*|`.*?`|\[(?:SRC-\d+|SRC-DB-\d+)\])/g;
  let lastIndex = 0;
  let match;

  while ((match = regex.exec(text)) !== null) {
    if (match.index > lastIndex) {
      parts.push(text.substring(lastIndex, match.index));
    }
    const token = match[0];
    if (token.startsWith('**') && token.endsWith('**')) {
      parts.push(<strong key={match.index}>{token.slice(2, -2)}</strong>);
    } else if (token.startsWith('`') && token.endsWith('`')) {
      parts.push(<code key={match.index}>{token.slice(1, -1)}</code>);
    } else if (token.startsWith('[SRC-')) {
      parts.push(<span key={match.index} className="inline-source-tag">{token}</span>);
    } else {
      parts.push(token);
    }
    lastIndex = regex.lastIndex;
  }
  if (lastIndex < text.length) {
    parts.push(text.substring(lastIndex));
  }
  return parts.length > 0 ? parts : text;
}

function renderMessageBody(text) {
  if (!text) return null;
  const lines = text.split('\n');
  const elements = [];
  let currentList = [];

  const flushList = () => {
    if (currentList.length > 0) {
      elements.push(
        <ul key={`ul-${elements.length}`} className="chat-markdown-list">
          {currentList.map((item, idx) => (
            <li key={idx}>{renderInlineFormatting(item)}</li>
          ))}
        </ul>
      );
      currentList = [];
    }
  };

  lines.forEach((line, idx) => {
    const trimmed = line.trim();
    if (trimmed.startsWith('* ') || trimmed.startsWith('- ')) {
      currentList.push(trimmed.slice(2));
    } else {
      flushList();
      if (trimmed.length > 0) {
        elements.push(
          <p key={`p-${idx}`} className="chat-markdown-para">
            {renderInlineFormatting(line)}
          </p>
        );
      }
    }
  });
  flushList();

  return elements.length > 0 ? elements : text;
}

export function Chat({ user }) {
  const [question, setQuestion] = useState('');
  const [messages, setMessages] = useState([]);
  const [loading, setLoading] = useState(false);
  const [errorBanner, setErrorBanner] = useState('');
  const messagesEndRef = useRef(null);

  const scrollToBottom = () => {
    messagesEndRef.current?.scrollIntoView({ behavior: 'smooth' });
  };

  useEffect(() => {
    scrollToBottom();
  }, [messages, loading]);

  const handleSend = async (e) => {
    e.preventDefault();
    const query = question.trim();
    if (!query || loading) {
      return;
    }

    setErrorBanner('');
    const userMessage = {
      id: Date.now(),
      sender: 'user',
      text: query,
      timestamp: new Date().toLocaleTimeString([], { hour: '2-digit', minute: '2-digit' })
    };

    setMessages((prev) => [...prev, userMessage]);
    setQuestion('');
    setLoading(true);

    try {
      const response = await chatApi(query);

      const assistantMessage = {
        id: Date.now() + 1,
        sender: 'assistant',
        text: response.answer,
        citations: response.citations || [],
        grounded: response.grounded,
        retrievalCount: response.retrieval_count,
        latencies: response.latencies || {},
        timestamp: new Date().toLocaleTimeString([], { hour: '2-digit', minute: '2-digit' })
      };

      setMessages((prev) => [...prev, assistantMessage]);
    } catch (err) {
      if (err.status === 401) {
        setErrorBanner('Your session has expired. Please sign in again.');
      } else if (err.status === 403) {
        setErrorBanner('Access forbidden. You do not have authorization for this query.');
      } else if (err.status === 429) {
        setErrorBanner('Rate limit reached (30 queries/min). Please pause before sending another query.');
      } else {
        setErrorBanner(err.message || 'Error processing RAG query.');
      }
    } finally {
      setLoading(false);
    }
  };

  const handleClearChat = () => {
    setMessages([]);
    setErrorBanner('');
  };

  return (
    <div className="chat-interface">
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
          <button
            type="button"
            className="alert-dismiss"
            onClick={() => setErrorBanner('')}
            aria-label="Dismiss error"
          >
            ×
          </button>
        </div>
      )}

      <div className="chat-messages-area" role="log" aria-live="polite" aria-label="Conversation history">
        {messages.length === 0 ? (
          <div className="chat-empty-state">
            <div className="empty-icon" aria-hidden="true">
              <svg viewBox="0 0 24 24" width="40" height="40" fill="none" stroke="currentColor" strokeWidth="1.5">
                <path d="M21 11.5a8.38 8.38 0 0 1-.9 3.8 8.5 8.5 0 0 1-7.6 4.7 8.38 8.38 0 0 1-3.8-.9L3 21l1.9-5.7a8.38 8.38 0 0 1-.9-3.8 8.5 8.5 0 0 1 4.7-7.6 8.38 8.38 0 0 1 3.8-.9h.5a8.48 8.48 0 0 1 8 8v.5z" />
              </svg>
            </div>
            <h2>Secure Enterprise Assistant</h2>
            <p>
              Ask questions grounded in your authorized documents and database records.
              Retrieval is filtered at the database and vector layers according to your role (
              <strong>{user?.role || 'authorized user'}</strong>) and tenant.
            </p>
            <div className="sample-queries-list">
              <span className="sample-label">
                Suggested Queries for <strong>{user?.role || 'User'}</strong>:
              </span>
              {(user?.role === 'student' ? [
                'What are my student directory details for STU-1001?',
                'What is my attendance record for Computer Science?',
                'What is the schedule for engineering classes?',
                'What is the student access control policy?'
              ] : user?.role === 'faculty' ? [
                'List faculty directory and course assignments for teaching staff.',
                'Show the class schedule and room allocations for Engineering.',
                'What are the access control policies for faculty and staff?',
                'What student directories am I authorized to access?'
              ] : user?.role === 'finance_manager' ? [
                'Show my assigned fee receipts and collection ledger.',
                'What are the payment details for fee receipt REC-3001?',
                'Summarize fee collection totals for my department.',
                'What is the financial access control policy?'
              ] : [
                'What is the access control policy for sensitive documents (EDU-POL-001)?',
                'What is the summary of the fee ledger and student payments?',
                'Show teacher directory and class schedule overview.',
                'Which employees belong to the Operations department?'
              ]).map((queryText) => (
                <button
                  key={queryText}
                  type="button"
                  className="sample-query-chip"
                  onClick={() => setQuestion(queryText)}
                  title="Click to insert query"
                >
                  "{queryText}"
                </button>
              ))}
            </div>
          </div>
        ) : (
          messages.map((msg) => {
            const formattedLatency = msg.sender === 'assistant' ? formatLatency(msg.latencies) : null;
            return (
              <div
                key={msg.id}
                className={`message-row ${msg.sender === 'user' ? 'row-user' : 'row-assistant'}`}
              >
                <div className={`message-bubble ${msg.sender === 'user' ? 'bubble-user' : 'bubble-assistant'}`}>
                  <div className="message-meta-header">
                    <span className="message-sender-name">
                      {msg.sender === 'user' ? (user?.name || 'You') : 'Secure RAG Agent'}
                    </span>
                    <span className="message-time">{msg.timestamp}</span>
                  </div>

                  <div className="message-body-text">{renderMessageBody(msg.text)}</div>

                  {msg.sender === 'assistant' && (
                    <div className="assistant-footer">
                      <div className="grounding-status-bar">
                        {msg.grounded ? (
                          <span className="badge badge-success">
                            <span className="status-dot dot-success" aria-hidden="true" />
                            Grounded in Authorized Sources
                          </span>
                        ) : (
                          <span className="badge badge-warning">
                            <span className="status-dot dot-warning" aria-hidden="true" />
                            Restricted / Safe Refusal
                          </span>
                        )}

                        {msg.retrievalCount !== undefined && msg.retrievalCount > 0 && (
                          <span className="badge badge-neutral">
                            Retrieved Chunks: {msg.retrievalCount}
                          </span>
                        )}

                        {formattedLatency && (
                          <span className="latency-text">
                            {formattedLatency}
                          </span>
                        )}
                      </div>

                      <Citations citations={msg.citations} />
                    </div>
                  )}
                </div>
              </div>
            );
          })
        )}

        {loading && (
          <div className="message-row row-assistant">
            <div className="message-bubble bubble-assistant bubble-loading">
              <div className="typing-indicator" aria-label="Searching authorized sources and generating response">
                <span></span>
                <span></span>
                <span></span>
              </div>
              <span className="loading-label">Retrieving authorized context & synthesizing answer...</span>
            </div>
          </div>
        )}

        <div ref={messagesEndRef} />
      </div>

      <div className="chat-input-container">
        <form onSubmit={handleSend} className="chat-form">
          <label htmlFor="chat-query-input" className="sr-only">
            Ask a question
          </label>
          <input
            id="chat-query-input"
            type="text"
            value={question}
            onChange={(e) => setQuestion(e.target.value)}
            placeholder="Ask a question grounded in authorized documents & data..."
            disabled={loading}
            autoComplete="off"
            className="chat-input"
          />
          <button
            type="submit"
            disabled={!question.trim() || loading}
            className="btn btn-primary btn-send"
            aria-label="Send question"
          >
            {loading ? (
              <span className="spinner small-spinner" aria-hidden="true" />
            ) : (
              <svg viewBox="0 0 20 20" fill="currentColor" width="18" height="18" aria-hidden="true">
                <path d="M10.894 2.553a1 1 0 00-1.788 0l-7 14a1 1 0 001.169 1.409l5-1.429A1 1 0 009 15.571V11a1 1 0 112 0v4.571a1 1 0 00.725.962l5 1.428a1 1 0 001.17-1.408l-7-14z" />
              </svg>
            )}
          </button>
          {messages.length > 0 && (
            <button
              type="button"
              onClick={handleClearChat}
              disabled={loading}
              className="btn btn-secondary btn-icon-only"
              title="Clear chat history"
              aria-label="Clear chat history"
            >
              <svg viewBox="0 0 20 20" fill="currentColor" width="16" height="16" aria-hidden="true">
                <path
                  fillRule="evenodd"
                  d="M9 2a1 1 0 00-.894.553L7.382 4H4a1 1 0 000 2v10a2 2 0 002 2h8a2 2 0 002-2V6a1 1 0 100-2h-3.382l-.724-1.447A1 1 0 0011 2H9zM7 8a1 1 0 012 0v6a1 1 0 11-2 0V8zm5-1a1 1 0 00-1 1v6a1 1 0 102 0V8a1 1 0 00-1-1z"
                  clipRule="evenodd"
                />
              </svg>
            </button>
          )}
        </form>
      </div>
    </div>
  );
}
