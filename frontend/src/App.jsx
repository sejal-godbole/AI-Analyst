import React, { useState, useEffect, useRef } from 'react';
import axios from 'axios';
import { 
  Send, 
  Database, 
  Terminal, 
  ShieldAlert, 
  CheckCircle, 
  AlertTriangle, 
  Clock, 
  Copy, 
  RefreshCw,
  Search,
  Check,
  X,
  Lock,
  Layers,
  Sun,
  Moon
} from 'lucide-react';

const API_BASE = 'http://localhost:8000';

function App() {
  const [theme, setTheme] = useState(() => {
    return localStorage.getItem('theme') || 'dark';
  });

  useEffect(() => {
    document.body.className = theme === 'light' ? 'light-theme' : '';
    localStorage.setItem('theme', theme);
  }, [theme]);

  const [activeTab, setActiveTab] = useState('chat'); // 'chat' | 'schema'
  const [healthStatus, setHealthStatus] = useState('offline'); // 'ok' | 'offline'
  const [schemaData, setSchemaData] = useState({ tables: {} });
  const [messages, setMessages] = useState([
    {
      id: 'welcome',
      sender: 'agent',
      text: 'Hello! I am your AI Database Analyst. I can answer queries, analyze schemas, and run updates under safety guardrails. What would you like to explore today?',
      timestamp: new Date().toLocaleTimeString(),
      status: 'success'
    }
  ]);
  const [question, setQuestion] = useState('');
  const [loading, setLoading] = useState(false);
  
  // Human-In-The-Loop Confirmation State
  const [pendingConfirmation, setPendingConfirmation] = useState(null); 
  // e.g., { thread_id, confirmation_message, sql }

  // Active query inspector state
  const [selectedMessage, setSelectedMessage] = useState(null);

  // Audit Logs State
  const [auditLogs, setAuditLogs] = useState([]);
  const [auditLoading, setAuditLoading] = useState(false);

  const [threadId, setThreadId] = useState(null);

  const messagesEndRef = useRef(null);

  const handleRefresh = () => {
    setThreadId(null);
    setMessages([
      {
        id: 'welcome',
        sender: 'agent',
        text: 'Hello! I am your AI Database Analyst. I can answer queries, analyze schemas, and run updates under safety guardrails. What would you like to explore today?',
        timestamp: new Date().toLocaleTimeString(),
        status: 'success'
      }
    ]);
    setSelectedMessage(null);
    setPendingConfirmation(null);
    fetchStatusAndSchema();
  };

  // Poll backend health and schema info
  const fetchStatusAndSchema = async () => {
    try {
      const healthRes = await axios.get(`${API_BASE}/health`);
      if (healthRes.data.status === 'ok') {
        setHealthStatus('ok');
      } else {
        setHealthStatus('offline');
      }
    } catch {
      setHealthStatus('offline');
    }

    try {
      const schemaRes = await axios.get(`${API_BASE}/schema`);
      setSchemaData(schemaRes.data);
    } catch (err) {
      console.error('Failed to load schema:', err);
    }
  };

  const fetchAuditLogs = async () => {
    setAuditLoading(true);
    try {
      const res = await axios.get(`${API_BASE}/audit-logs`);
      setAuditLogs(res.data);
    } catch (err) {
      console.error('Failed to load audit logs:', err);
    } finally {
      setAuditLoading(false);
    }
  };

  useEffect(() => {
    fetchStatusAndSchema();
  }, []);

  // Scroll to bottom of chat
  useEffect(() => {
    messagesEndRef.current?.scrollIntoView({ behavior: 'smooth' });
  }, [messages, loading, pendingConfirmation]);

  // Handle natural language question submission
  const handleSubmitQuestion = async (qText) => {
    const textToSend = qText || question;
    if (!textToSend.trim()) return;

    setQuestion('');
    setLoading(true);

    const userMsgId = `user-${Date.now()}`;
    const newMsg = {
      id: userMsgId,
      sender: 'user',
      text: textToSend,
      timestamp: new Date().toLocaleTimeString(),
    };
    
    setMessages(prev => [...prev, newMsg]);

    try {
      const payload = { question: textToSend };
      if (threadId) {
        payload.thread_id = threadId;
      }
      const res = await axios.post(`${API_BASE}/analyze`, payload);
      const data = res.data;

      if (data.thread_id) {
        setThreadId(data.thread_id);
      }

      const agentMsgId = `agent-${Date.now()}`;
      
      if (data.status === 'awaiting_confirmation') {
        setPendingConfirmation({
          thread_id: data.thread_id,
          confirmation_message: data.confirmation_message,
          sql: data.sql,
          userMsgId: userMsgId
        });
        
        const agentMsg = {
          id: agentMsgId,
          sender: 'agent',
          text: data.confirmation_message || 'This query requires human confirmation. Please review and approve/reject below.',
          timestamp: new Date().toLocaleTimeString(),
          status: 'awaiting_confirmation',
          sql: data.sql,
          threadId: data.thread_id,
        };
        setMessages(prev => [...prev, agentMsg]);
        setSelectedMessage(agentMsg);
      } else {
        const agentMsg = {
          id: agentMsgId,
          sender: 'agent',
          text: data.answer || (data.status === 'rejected' ? `Rejected: ${data.error}` : `Error: ${data.error}`),
          timestamp: new Date().toLocaleTimeString(),
          status: data.status, // 'success' | 'rejected' | 'error'
          sql: data.sql,
          error: data.error,
          threadId: data.thread_id,
          rowsAffected: data.rows_affected
        };
        setMessages(prev => [...prev, agentMsg]);
        setSelectedMessage(agentMsg);
        
        // Refresh schema in case of structural updates (table creation, etc.)
        fetchStatusAndSchema();
      }
    } catch (err) {
      console.error(err);
      const errorMsg = {
        id: `err-${Date.now()}`,
        sender: 'agent',
        text: 'The server encountered an error processing your query. Check if the database and LLM service are online.',
        timestamp: new Date().toLocaleTimeString(),
        status: 'error'
      };
      setMessages(prev => [...prev, errorMsg]);
    } finally {
      setLoading(false);
    }
  };

  // Handle Human-In-The-Loop Confirmation Action
  const handleConfirm = async (approved) => {
    if (!pendingConfirmation) return;

    const { thread_id, sql } = pendingConfirmation;
    setPendingConfirmation(null);
    setLoading(true);

    try {
      const res = await axios.post(`${API_BASE}/analyze`, {
        thread_id: thread_id,
        confirm: approved,
        question: approved ? 'confirm' : 'reject'
      });

      const data = res.data;
      const agentMsgId = `agent-${Date.now()}`;
      
      const agentMsg = {
        id: agentMsgId,
        sender: 'agent',
        text: data.answer || (approved ? 'Operation approved and executed successfully.' : 'Operation cancelled by user.'),
        timestamp: new Date().toLocaleTimeString(),
        status: data.status,
        sql: sql,
        error: data.error,
        threadId: thread_id,
        rowsAffected: data.rows_affected
      };

      setMessages(prev => [...prev, agentMsg]);
      setSelectedMessage(agentMsg);
      
      // Refresh schema in case database state changed
      fetchStatusAndSchema();
    } catch (err) {
      console.error(err);
      const errorMsg = {
        id: `err-${Date.now()}`,
        sender: 'agent',
        text: 'An error occurred during workflow resumption.',
        timestamp: new Date().toLocaleTimeString(),
        status: 'error'
      };
      setMessages(prev => [...prev, errorMsg]);
    } finally {
      setLoading(false);
    }
  };

  // Query helpers / presets
  const presets = [
    { label: 'Inspect Database Tables', q: 'Show all the tables present in the database' },
    { label: 'Describe Customers Table', q: 'List the columns, data types, and primary keys for the customers table' },
    { label: 'Query (Customers in Pune)', q: 'How many customers are from Pune?' },
    { label: 'PII Sensitive Guardrail', q: "What is Aditi Sharma's email?" },
    { label: 'Write Query (HITL approval)', q: 'Update the monthly charge of all customers to 999' },
    { label: 'Write Query (Safe immediate)', q: 'Update the monthly charge of Aditi Sharma to 899' },
    { label: 'SQL Injection Guardrail', q: 'Show all customers; drop table orders;' },
    { label: 'Schema Validation Block', q: 'Show the customer address' }
  ];

  return (
    <div className="app-container">
      {/* Premium Brutalist App Header */}
      <header className="app-header">
        <div className="brand-section">
          <div className="brand-logo">A</div>
          <h1 className="brand-title">AI Analyst Agent</h1>
        </div>
        
        <div className="brand-section" style={{ gap: '1rem' }}>
          <button 
            className="neo-button secondary" 
            style={{ padding: '0.4rem', width: '2.25rem', height: '2.25rem' }} 
            onClick={() => setTheme(prev => prev === 'light' ? 'dark' : 'light')}
            title="Toggle theme"
          >
            {theme === 'light' ? <Moon size={14} /> : <Sun size={14} />}
          </button>
          
          <button className="neo-button secondary" style={{ padding: '0.4rem 1rem', height: '2.25rem' }} onClick={handleRefresh}>
            <RefreshCw size={14} /> Refresh
          </button>
          
          <div className="api-status">
            <span className={`status-dot ${healthStatus === 'ok' ? 'active' : ''}`}></span>
            API Status: {healthStatus}
          </div>
        </div>
      </header>

      {/* Main Split Layout */}
      <main className="main-layout">
        {/* Left Interactive Panel */}
        <section className="left-panel">
          <div style={{ padding: '2rem 2rem 0 2rem' }}>
            <div className="tabs-navigation">
              <button 
                className={`tab-button ${activeTab === 'chat' ? 'active' : ''}`}
                onClick={() => setActiveTab('chat')}
              >
                <Terminal size={14} style={{ marginRight: '0.35rem', verticalAlign: 'middle' }} />
                Chat Console
              </button>
              <button 
                className={`tab-button ${activeTab === 'schema' ? 'active' : ''}`}
                onClick={() => setActiveTab('schema')}
              >
                <Database size={14} style={{ marginRight: '0.35rem', verticalAlign: 'middle' }} />
                Database Schema
              </button>
              <button 
                className={`tab-button ${activeTab === 'audit' ? 'active' : ''}`}
                onClick={() => {
                  setActiveTab('audit');
                  fetchAuditLogs();
                }}
              >
                <Clock size={14} style={{ marginRight: '0.35rem', verticalAlign: 'middle' }} />
                Audit Logs
              </button>
            </div>
          </div>

          {activeTab === 'chat' && (
            <>
              {/* Chat Conversation Scroll Area */}
              <div className="chat-container">
                {messages.map((msg) => (
                  <div 
                    key={msg.id} 
                    className={`chat-bubble ${msg.sender} ${selectedMessage?.id === msg.id ? 'active-inspect' : ''}`}
                    onClick={() => {
                      if (msg.sender === 'agent') setSelectedMessage(msg);
                    }}
                    style={{ 
                      cursor: msg.sender === 'agent' ? 'pointer' : 'default',
                      borderWidth: selectedMessage?.id === msg.id ? '3px' : '2px' 
                    }}
                  >
                    <div style={{ fontSize: '0.75rem', fontWeight: 600, color: 'var(--text-secondary)', marginBottom: '0.25rem', display: 'flex', justifyContent: 'space-between' }}>
                      <span>{msg.sender === 'user' ? 'YOU' : 'AI ANALYST'}</span>
                      <span>{msg.timestamp}</span>
                    </div>
                    <div>{msg.text}</div>
                    
                    {msg.status === 'awaiting_confirmation' && (
                      <div style={{ display: 'flex', alignItems: 'center', gap: '0.5rem', color: 'var(--warning-text)', fontWeight: 700, fontSize: '0.75rem', marginTop: '0.5rem' }}>
                        <AlertTriangle size={14} /> Paused: Awaiting confirmation
                      </div>
                    )}
                    {msg.status === 'rejected' && (
                      <div style={{ display: 'flex', alignItems: 'center', gap: '0.5rem', color: 'var(--danger-text)', fontWeight: 700, fontSize: '0.75rem', marginTop: '0.5rem' }}>
                        <ShieldAlert size={14} /> Security Blocked
                      </div>
                    )}
                  </div>
                ))}

                {/* Spinning loader inside console */}
                {loading && (
                  <div className="chat-bubble agent" style={{ display: 'flex', alignItems: 'center', gap: '0.75rem', alignSelf: 'flex-start' }}>
                    <RefreshCw className="spinner" size={16} />
                    <span>Analyzing schema and executing query plan...</span>
                  </div>
                )}

                {/* Human-In-The-Loop Confirmation overlay box */}
                {pendingConfirmation && (
                  <div className="confirm-card">
                    <h3 style={{ display: 'flex', alignItems: 'center', gap: '0.5rem', fontSize: '1rem', color: 'var(--warning-text)' }}>
                      <AlertTriangle size={18} /> Risky Write Action Requires Authorization
                    </h3>
                    <p style={{ marginTop: '0.5rem', fontSize: '0.875rem' }}>
                      {pendingConfirmation.confirmation_message}
                    </p>
                    <div className="code-block" style={{ color: 'var(--text-primary)' }}>
                      {pendingConfirmation.sql}
                    </div>
                    
                    <div className="confirm-card-buttons">
                      <button className="confirm-button" onClick={() => handleConfirm(true)}>
                        <Check size={14} style={{ verticalAlign: 'middle', marginRight: '0.25rem' }} /> Approve & Run
                      </button>
                      <button className="reject-button" onClick={() => handleConfirm(false)}>
                        <X size={14} style={{ verticalAlign: 'middle', marginRight: '0.25rem' }} /> Reject & Abort
                      </button>
                    </div>
                  </div>
                )}
                
                <div ref={messagesEndRef} />
              </div>

              {/* Preset suggestion helpers */}
              <div style={{ padding: '0 2rem' }}>
                <h4 style={{ fontSize: '0.75rem', marginBottom: '0.5rem', color: 'var(--text-secondary)' }}>Pre-configured Test Scenarios</h4>
                <div style={{ display: 'flex', gap: '0.5rem', flexWrap: 'wrap', marginBottom: '1rem' }}>
                  {presets.map((preset, idx) => (
                    <button 
                      key={idx}
                      className="neo-button secondary"
                      style={{ fontSize: '0.7rem', padding: '0.35rem 0.6rem', textTransform: 'none', letterSpacing: 'normal' }}
                      onClick={() => handleSubmitQuestion(preset.q)}
                      disabled={loading || !!pendingConfirmation}
                    >
                      {preset.label}
                    </button>
                  ))}
                </div>
              </div>

              {/* Chat Form Entry */}
              <div className="chat-input-wrapper">
                <input 
                  type="text" 
                  className="neo-input" 
                  placeholder={pendingConfirmation ? "Provide confirmation input above..." : "Ask the AI Database Analyst a question..."}
                  value={question}
                  onChange={(e) => setQuestion(e.target.value)}
                  onKeyDown={(e) => e.key === 'Enter' && handleSubmitQuestion()}
                  disabled={loading || !!pendingConfirmation}
                />
                <button 
                  className="neo-button"
                  onClick={() => handleSubmitQuestion()}
                  disabled={loading || !!pendingConfirmation}
                >
                  <Send size={16} />
                </button>
              </div>
            </>
          )}

          {activeTab === 'schema' && (
            <div style={{ padding: '2rem' }}>
              <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: '1.5rem' }}>
                <h2>Active Database Schema</h2>
                <div style={{ fontSize: '0.75rem', fontWeight: 600, color: 'var(--text-secondary)' }}>
                  {Object.keys(schemaData.tables).length} TABLES INSPECTED
                </div>
              </div>
              
              <div className="schema-grid">
                {Object.entries(schemaData.tables).map(([tableName, table]) => (
                  <div key={tableName} className="schema-card neo-box" style={{ margin: 0 }}>
                    <div className="schema-title" style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center' }}>
                      <span>{tableName}</span>
                      <Layers size={12} />
                    </div>
                    <ul className="schema-columns">
                      {Object.entries(table.columns).map(([colName, colType]) => {
                        const isPK = table.primary_keys.includes(colName);
                        const isFK = table.foreign_keys.some(fk => fk.column === colName);
                        return (
                          <li key={colName} className="schema-column-item">
                            <span style={{ fontWeight: (isPK || isFK) ? 'bold' : 'normal' }}>
                              {colName} {isPK && '🔑'} {isFK && '🔗'}
                            </span>
                            <span className="type">{colType}</span>
                          </li>
                        );
                      })}
                    </ul>
                  </div>
                ))}
              </div>
            </div>
          )}

          {activeTab === 'audit' && (
            <div style={{ padding: '2rem' }}>
              <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: '1.5rem' }}>
                <h2>System Audit Logs</h2>
                <button className="neo-button secondary" onClick={fetchAuditLogs} disabled={auditLoading}>
                  <RefreshCw className={auditLoading ? "spinner" : ""} size={14} /> Refresh Logs
                </button>
              </div>

              {auditLoading ? (
                <div style={{ display: 'flex', alignItems: 'center', gap: '0.75rem', padding: '2rem' }}>
                  <RefreshCw className="spinner" size={16} />
                  <span>Loading audit logs...</span>
                </div>
              ) : auditLogs.length === 0 ? (
                <div style={{ border: '2px dashed var(--border-color)', borderRadius: '8px', padding: '3rem', textAlign: 'center', color: 'var(--text-secondary)' }}>
                  <Clock size={32} style={{ margin: '0 auto 1rem auto', display: 'block' }} />
                  No audit log entries found. Run some queries in the Chat Console to generate logs.
                </div>
              ) : (
                <div className="audit-log-list" style={{ display: 'flex', flexDirection: 'column', gap: '1.5rem', maxHeight: '75vh', overflowY: 'auto', paddingRight: '0.5rem' }}>
                  {auditLogs.map((log) => (
                    <div key={log.audit_id} className="neo-box" style={{ margin: 0, padding: '1.5rem' }}>
                      <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: '1rem', borderBottom: '2px solid var(--border-color)', paddingBottom: '0.5rem' }}>
                        <div style={{ display: 'flex', alignItems: 'center', gap: '0.75rem' }}>
                          <span style={{ fontWeight: 800, fontSize: '0.9rem' }}>LOG #{log.audit_id}</span>
                          <span style={{ fontSize: '0.75rem', color: 'var(--text-secondary)' }}>
                            {new Date(log.created_at).toLocaleString()}
                          </span>
                        </div>
                        <div style={{ display: 'flex', gap: '0.5rem' }}>
                          <span className="status-badge" style={{ 
                            backgroundColor: log.validation_status === 'valid' ? 'var(--success-bg)' : 'var(--danger-bg)',
                            color: log.validation_status === 'valid' ? 'var(--success-text)' : 'var(--danger-text)',
                            border: `2px solid ${log.validation_status === 'valid' ? 'var(--success-border)' : 'var(--danger-border)'}`,
                            padding: '0.15rem 0.4rem', borderRadius: '4px', fontWeight: 700, fontSize: '0.65rem'
                          }}>
                            VAL: {log.validation_status ? log.validation_status.toUpperCase() : 'N/A'}
                          </span>
                          <span className="status-badge" style={{ 
                            backgroundColor: log.execution_status === 'success' ? 'var(--success-bg)' : 'var(--danger-bg)',
                            color: log.execution_status === 'success' ? 'var(--success-text)' : 'var(--danger-text)',
                            border: `2px solid ${log.execution_status === 'success' ? 'var(--success-border)' : 'var(--danger-border)'}`,
                            padding: '0.15rem 0.4rem', borderRadius: '4px', fontWeight: 700, fontSize: '0.65rem'
                          }}>
                            EXEC: {log.execution_status ? log.execution_status.toUpperCase() : 'N/A'}
                          </span>
                        </div>
                      </div>

                      <div style={{ display: 'flex', flexDirection: 'column', gap: '0.75rem' }}>
                        <div>
                          <strong style={{ fontSize: '0.75rem', color: 'var(--text-secondary)' }}>USER QUESTION</strong>
                          <p style={{ fontSize: '0.9rem', marginTop: '0.1rem' }}>{log.user_question}</p>
                        </div>

                        {log.generated_sql && (
                          <div>
                            <strong style={{ fontSize: '0.75rem', color: 'var(--text-secondary)' }}>GENERATED SQL</strong>
                            <div className="code-block" style={{ marginTop: '0.25rem', fontSize: '0.75rem', padding: '0.5rem' }}>
                              {log.generated_sql}
                            </div>
                          </div>
                        )}

                        <div style={{ display: 'grid', gridTemplateColumns: 'repeat(auto-fit, minmax(120px, 1fr))', gap: '1rem', marginTop: '0.25rem' }}>
                          <div>
                            <strong style={{ fontSize: '0.75rem', color: 'var(--text-secondary)' }}>RETRIES</strong>
                            <p style={{ fontSize: '0.9rem', fontWeight: 600 }}>{log.retry_count}</p>
                          </div>
                          <div>
                            <strong style={{ fontSize: '0.75rem', color: 'var(--text-secondary)' }}>ROWS AFFECTED</strong>
                            <p style={{ fontSize: '0.9rem', fontWeight: 600 }}>{log.rows_affected !== null ? log.rows_affected : 'N/A'}</p>
                          </div>
                          {log.confirmation_status && (
                            <div>
                              <strong style={{ fontSize: '0.75rem', color: 'var(--text-secondary)' }}>CONFIRMATION</strong>
                              <p style={{ fontSize: '0.9rem', fontWeight: 600, color: log.confirmation_status === 'approved' ? 'var(--success-text)' : 'var(--warning-text)' }}>
                                {log.confirmation_status.toUpperCase()}
                              </p>
                            </div>
                          )}
                        </div>

                        {log.result_summary && (
                          <div>
                            <strong style={{ fontSize: '0.75rem', color: 'var(--text-secondary)' }}>RESULT SUMMARY</strong>
                            <p style={{ fontSize: '0.8rem', fontFamily: 'monospace', backgroundColor: 'rgba(0,0,0,0.03)', padding: '0.4rem', border: '1px solid var(--border-color)', marginTop: '0.1rem' }}>
                              {log.result_summary}
                            </p>
                          </div>
                        )}

                        {log.error && (
                          <div>
                            <strong style={{ fontSize: '0.75rem', color: 'var(--danger-text)' }}>ERROR</strong>
                            <p className="code-block" style={{ backgroundColor: 'var(--danger-bg)', borderColor: 'var(--danger-border)', color: 'var(--danger-text)', fontSize: '0.75rem', padding: '0.5rem', marginTop: '0.1rem' }}>
                              {log.error}
                            </p>
                          </div>
                        )}
                      </div>
                    </div>
                  ))}
                </div>
              )}
            </div>
          )}
        </section>

        {/* Right Details/Metadata Panel */}
        <section className="right-panel">
          <div style={{ marginBottom: '2rem' }}>
            <h2 style={{ display: 'flex', alignItems: 'center', gap: '0.5rem' }}>
              <Terminal size={20} /> Query Inspector
            </h2>
            <p style={{ fontSize: '0.875rem', color: 'var(--text-secondary)', marginTop: '0.25rem' }}>
              Select an analyst response in the console to inspect the underlying security and execution telemetry.
            </p>
          </div>

          {selectedMessage ? (
            <div className="neo-box" style={{ display: 'flex', flexDirection: 'column', gap: '1.5rem', minHeight: '400px' }}>
              <div>
                <h4 style={{ fontSize: '0.75rem', color: 'var(--text-secondary)' }}>EXECUTION STATUS</h4>
                <div style={{ display: 'flex', alignItems: 'center', gap: '0.5rem', marginTop: '0.25rem' }}>
                  {selectedMessage.status === 'success' && (
                    <span className="status-badge" style={{ backgroundColor: 'var(--success-bg)', color: 'var(--success-text)', border: '2px solid var(--success-border)', padding: '0.25rem 0.5rem', borderRadius: '4px', fontWeight: 700, fontSize: '0.75rem' }}>
                      <CheckCircle size={12} style={{ verticalAlign: 'middle', marginRight: '0.25rem' }} /> SUCCESS
                    </span>
                  )}
                  {selectedMessage.status === 'awaiting_confirmation' && (
                    <span className="status-badge" style={{ backgroundColor: 'var(--warning-bg)', color: 'var(--warning-text)', border: '2px solid var(--warning-border)', padding: '0.25rem 0.5rem', borderRadius: '4px', fontWeight: 700, fontSize: '0.75rem' }}>
                      <Clock size={12} style={{ verticalAlign: 'middle', marginRight: '0.25rem' }} /> AWAITING CONFIRMATION
                    </span>
                  )}
                  {selectedMessage.status === 'rejected' && (
                    <span className="status-badge" style={{ backgroundColor: 'var(--danger-bg)', color: 'var(--danger-text)', border: '2px solid var(--danger-border)', padding: '0.25rem 0.5rem', borderRadius: '4px', fontWeight: 700, fontSize: '0.75rem' }}>
                      <Lock size={12} style={{ verticalAlign: 'middle', marginRight: '0.25rem' }} /> GUARDRAILS BLOCKED
                    </span>
                  )}
                  {selectedMessage.status === 'error' && (
                    <span className="status-badge" style={{ backgroundColor: 'var(--danger-bg)', color: 'var(--danger-text)', border: '2px solid var(--danger-border)', padding: '0.25rem 0.5rem', borderRadius: '4px', fontWeight: 700, fontSize: '0.75rem' }}>
                      <X size={12} style={{ verticalAlign: 'middle', marginRight: '0.25rem' }} /> ERROR
                    </span>
                  )}
                </div>
              </div>

              {selectedMessage.sql && (
                <div>
                  <h4 style={{ fontSize: '0.75rem', color: 'var(--text-secondary)', display: 'flex', justifyContent: 'space-between', alignItems: 'center' }}>
                    <span>GENERATED SQL STATEMENT</span>
                    <button 
                      className="neo-button secondary" 
                      style={{ padding: '0.2rem 0.4rem', fontSize: '0.65rem' }}
                      onClick={() => navigator.clipboard.writeText(selectedMessage.sql)}
                    >
                      <Copy size={10} /> COPY
                    </button>
                  </h4>
                  <div className="code-block" style={{ marginTop: '0.5rem' }}>
                    {selectedMessage.sql}
                  </div>
                </div>
              )}

              {selectedMessage.rowsAffected !== undefined && selectedMessage.rowsAffected !== null && (
                <div>
                  <h4 style={{ fontSize: '0.75rem', color: 'var(--text-secondary)' }}>ROWS AFFECTED / RETURNED</h4>
                  <p style={{ fontSize: '1.25rem', fontWeight: 800, marginTop: '0.25rem' }}>
                    {selectedMessage.rowsAffected} row(s)
                  </p>
                </div>
              )}

              {selectedMessage.error && (
                <div>
                  <h4 style={{ fontSize: '0.75rem', color: 'var(--danger-text)' }}>REJECTION / ERROR EXPLANATION</h4>
                  <p className="code-block" style={{ backgroundColor: 'var(--danger-bg)', borderColor: 'var(--danger-border)', color: 'var(--danger-text)', marginTop: '0.5rem' }}>
                    {selectedMessage.error}
                  </p>
                </div>
              )}

              {selectedMessage.threadId && (
                <div>
                  <h4 style={{ fontSize: '0.75rem', color: 'var(--text-secondary)' }}>THREAD TELEMETRY</h4>
                  <p style={{ fontFamily: 'monospace', fontSize: '0.75rem', marginTop: '0.25rem', color: 'var(--text-secondary)' }}>
                    Thread ID: {selectedMessage.threadId}
                  </p>
                </div>
              )}
            </div>
          ) : (
            <div style={{ border: '2px dashed var(--border-color)', borderRadius: '8px', padding: '3rem', textAlign: 'center', color: 'var(--text-secondary)' }}>
              <Terminal size={32} style={{ margin: '0 auto 1rem auto', display: 'block' }} />
              No active inspection telemetry. Select any agent message inside the chat console to analyze.
            </div>
          )}
        </section>
      </main>
    </div>
  );
}

export default App;
