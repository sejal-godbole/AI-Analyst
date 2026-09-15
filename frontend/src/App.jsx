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
  Moon,
  Activity,
  Zap,
  Cpu,
  Server,
  Code2,
  ExternalLink,
  ChevronDown,
  ChevronRight,
  ShieldCheck,
  DollarSign
} from 'lucide-react';
import ObservabilityDashboard from './components/ObservabilityDashboard';

const API_BASE = import.meta.env.VITE_API_BASE_URL || 'http://localhost:8000';

function App() {
  const [theme, setTheme] = useState(() => {
    return localStorage.getItem('theme') || 'dark';
  });

  useEffect(() => {
    document.body.className = theme === 'light' ? 'light-theme' : '';
    localStorage.setItem('theme', theme);
  }, [theme]);

  const [activeTab, setActiveTab] = useState('chat'); // 'chat' | 'schema' | 'audit'
  const [healthStatus, setHealthStatus] = useState('offline'); // 'ok' | 'offline'
  const [schemaData, setSchemaData] = useState({ tables: {} });
  const [messages, setMessages] = useState([
    {
      id: 'welcome',
      sender: 'agent',
      text: 'Hello! I am your AI Database Analyst. I can answer queries, analyze schemas, and run updates under safety guardrails with live LangSmith observability. What would you like to explore today?',
      timestamp: new Date().toLocaleTimeString(),
      status: 'success'
    }
  ]);
  const [question, setQuestion] = useState('');
  const [loading, setLoading] = useState(false);
  
  // Human-In-The-Loop Confirmation State
  const [pendingConfirmation, setPendingConfirmation] = useState(null); 

  // Active query inspector state
  const [selectedMessage, setSelectedMessage] = useState(null);
  const [activeTraceDetail, setActiveTraceDetail] = useState(null);
  const [showPromptDetails, setShowPromptDetails] = useState(false);

  // Big Observability Dialog Modal State
  const [showObservabilityModal, setShowObservabilityModal] = useState(false);

  // Audit Logs State
  const [auditLogs, setAuditLogs] = useState([]);
  const [auditLoading, setAuditLoading] = useState(false);

  const [threadId, setThreadId] = useState(null);
  const [activeTraceId, setActiveTraceId] = useState(null);

  const messagesEndRef = useRef(null);

  // Close modal on escape key
  useEffect(() => {
    const handleKeyDown = (e) => {
      if (e.key === 'Escape') {
        setShowObservabilityModal(false);
      }
    };
    window.addEventListener('keydown', handleKeyDown);
    return () => window.removeEventListener('keydown', handleKeyDown);
  }, []);

  const handleRefresh = () => {
    setThreadId(null);
    setActiveTraceId(null);
    setSelectedMessage(null);
    setActiveTraceDetail(null);
    setMessages([
      {
        id: 'welcome',
        sender: 'agent',
        text: 'Hello! I am your AI Database Analyst. I can answer queries, analyze schemas, and run updates under safety guardrails with live LangSmith observability. What would you like to explore today?',
        timestamp: new Date().toLocaleTimeString(),
        status: 'success'
      }
    ]);
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

  const fetchTraceDetail = async (traceId) => {
    if (!traceId) return;
    try {
      const res = await axios.get(`${API_BASE}/api/observability/traces/${traceId}`);
      setActiveTraceDetail(res.data);
    } catch (err) {
      console.error('Failed to fetch trace detail for inspector:', err);
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
      if (data.trace_id) {
        setActiveTraceId(data.trace_id);
        fetchTraceDetail(data.trace_id);
      }

      const agentMsgId = `agent-${Date.now()}`;
      
      if (data.status === 'awaiting_confirmation') {
        setPendingConfirmation({
          thread_id: data.thread_id,
          trace_id: data.trace_id,
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
          traceId: data.trace_id,
        };
        setMessages(prev => [...prev, agentMsg]);
        setSelectedMessage(agentMsg);
      } else {
        const agentMsg = {
          id: agentMsgId,
          sender: 'agent',
          text: data.answer || (data.status === 'rejected' ? `Rejected: ${data.error}` : `Error: ${data.error}`),
          timestamp: new Date().toLocaleTimeString(),
          status: data.status,
          sql: data.sql,
          error: data.error,
          threadId: data.thread_id,
          traceId: data.trace_id,
          rowsAffected: data.rows_affected
        };
        setMessages(prev => [...prev, agentMsg]);
        setSelectedMessage(agentMsg);
        
        // Refresh schema in case of structural updates
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

    const { thread_id, trace_id, sql } = pendingConfirmation;
    setPendingConfirmation(null);
    setLoading(true);

    try {
      const res = await axios.post(`${API_BASE}/analyze`, {
        thread_id: thread_id,
        trace_id: trace_id,
        confirm: approved,
        question: approved ? 'confirm' : 'reject'
      });

      const data = res.data;
      if (data.trace_id) {
        setActiveTraceId(data.trace_id);
        fetchTraceDetail(data.trace_id);
      }

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
        traceId: data.trace_id || trace_id,
        rowsAffected: data.rows_affected
      };

      setMessages(prev => [...prev, agentMsg]);
      setSelectedMessage(agentMsg);
      
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

  // Select message and sync trace details
  const handleSelectMessage = (msg) => {
    if (msg.sender !== 'agent') return;
    setSelectedMessage(msg);
    if (msg.traceId) {
      setActiveTraceId(msg.traceId);
      fetchTraceDetail(msg.traceId);
    } else {
      setActiveTraceDetail(null);
    }
  };

  // Query presets
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
        
        <div className="brand-section" style={{ gap: '0.75rem' }}>
          <button 
            className="neo-button secondary" 
            style={{ padding: '0.4rem 0.85rem', height: '2.25rem', gap: '0.4rem' }} 
            onClick={() => setShowObservabilityModal(true)}
            title="Open Observability & LangSmith Traces Dialog"
          >
            <Activity size={14} style={{ color: 'var(--accent-color)' }} />
            <span>Observability & Traces</span>
          </button>

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
              <button 
                className="tab-button"
                onClick={() => setShowObservabilityModal(true)}
                style={{ color: 'var(--accent-color)', borderColor: 'rgba(139, 92, 246, 0.25)' }}
                title="Open Big Observability Traces Dialog"
              >
                <Activity size={14} style={{ marginRight: '0.35rem', verticalAlign: 'middle' }} />
                Live Observability ↗
              </button>
            </div>
          </div>

          {/* Tab 1: Chat Console */}
          {activeTab === 'chat' && (
            <>
              {/* Chat Conversation Scroll Area */}
              <div className="chat-container">
                {messages.map((msg) => (
                  <div 
                    key={msg.id} 
                    className={`chat-bubble ${msg.sender} ${selectedMessage?.id === msg.id ? 'active-inspect' : ''}`}
                    onClick={() => handleSelectMessage(msg)}
                    style={{ 
                      cursor: msg.sender === 'agent' ? 'pointer' : 'default',
                      borderWidth: selectedMessage?.id === msg.id ? '3px' : '2px' 
                    }}
                  >
                    <div style={{ fontSize: '0.75rem', fontWeight: 600, color: 'var(--text-secondary)', marginBottom: '0.25rem', display: 'flex', justifyContent: 'space-between' }}>
                      <span>{msg.sender === 'user' ? 'YOU' : 'AI ANALYST'}</span>
                      <span>{msg.timestamp}</span>
                    </div>
                    
                    <div style={{ whiteSpace: 'pre-wrap', lineHeight: '1.5' }}>
                      {msg.text}
                    </div>
                  </div>
                ))}

                {loading && (
                  <div className="chat-bubble agent" style={{ borderStyle: 'dashed' }}>
                    <div style={{ display: 'flex', alignItems: 'center', gap: '0.5rem' }}>
                      <div className="status-dot active"></div>
                      <span>Tracing LangGraph nodes & evaluating guardrails...</span>
                    </div>
                  </div>
                )}

                {/* Human-In-The-Loop Confirmation Box */}
                {pendingConfirmation && (
                  <div className="neo-box" style={{ borderColor: 'var(--warning-border)', backgroundColor: 'var(--warning-bg)', margin: '1rem 0' }}>
                    <div style={{ display: 'flex', alignItems: 'center', gap: '0.5rem', color: 'var(--warning-text)', fontWeight: 700 }}>
                      <AlertTriangle size={18} />
                      <span>HUMAN AUTHORIZATION REQUIRED</span>
                    </div>

                    <p style={{ marginTop: '0.5rem', fontSize: '0.875rem' }}>
                      {pendingConfirmation.confirmation_message}
                    </p>

                    <div className="code-block" style={{ marginTop: '0.5rem', marginBottom: '1rem' }}>
                      {pendingConfirmation.sql}
                    </div>

                    <div style={{ display: 'flex', gap: '0.75rem' }}>
                      <button 
                        className="neo-button" 
                        style={{ backgroundColor: 'var(--success-bg)', color: 'var(--success-text)', borderColor: 'var(--success-border)' }}
                        onClick={() => handleConfirm(true)}
                      >
                        <Check size={14} /> APPROVE & EXECUTE
                      </button>
                      <button 
                        className="neo-button" 
                        style={{ backgroundColor: 'var(--danger-bg)', color: 'var(--danger-text)', borderColor: 'var(--danger-border)' }}
                        onClick={() => handleConfirm(false)}
                      >
                        <X size={14} /> REJECT
                      </button>
                    </div>
                  </div>
                )}

                <div ref={messagesEndRef} />
              </div>

              {/* Natural Language Prompt Input */}
              <div className="chat-input-area">
                {/* Fast Presets */}
                <div style={{ display: 'flex', gap: '0.5rem', overflowX: 'auto', paddingBottom: '0.5rem' }}>
                  {presets.map((p, idx) => (
                    <button
                      key={idx}
                      className="neo-button secondary"
                      style={{ fontSize: '0.7rem', padding: '0.25rem 0.5rem', whiteSpace: 'nowrap' }}
                      onClick={() => handleSubmitQuestion(p.q)}
                      disabled={loading}
                    >
                      {p.label}
                    </button>
                  ))}
                </div>

                <form 
                  onSubmit={(e) => {
                    e.preventDefault();
                    handleSubmitQuestion();
                  }}
                  style={{ display: 'flex', gap: '0.5rem', marginTop: '0.5rem' }}
                >
                  <input
                    type="text"
                    className="neo-input"
                    placeholder="Ask a question about customers, orders, or request database updates..."
                    value={question}
                    onChange={(e) => setQuestion(e.target.value)}
                    disabled={loading}
                    style={{ flex: 1 }}
                  />
                  <button type="submit" className="neo-button primary" disabled={loading || !question.trim()}>
                    <Send size={16} />
                  </button>
                </form>
              </div>
            </>
          )}

          {/* Tab 2: Database Schema */}
          {activeTab === 'schema' && (
            <div style={{ flex: 1, overflowY: 'auto', padding: '0 2rem 2rem 2rem' }}>
              <div style={{ marginBottom: '1.5rem', display: 'flex', justifyContent: 'space-between', alignItems: 'center' }}>
                <div>
                  <h3 style={{ fontSize: '1.1rem', fontWeight: 700 }}>Database Schema Metadata</h3>
                  <p style={{ color: 'var(--text-secondary)', fontSize: '0.8rem' }}>
                    Live discovered schema using the raw MCP <code>inspect_schema</code> tool.
                  </p>
                </div>
                <button className="neo-button secondary" style={{ fontSize: '0.75rem', padding: '0.3rem 0.6rem' }} onClick={fetchStatusAndSchema}>
                  <RefreshCw size={12} /> Sync Schema
                </button>
              </div>

              <div style={{ display: 'grid', gridTemplateColumns: 'repeat(auto-fill, minmax(280px, 1fr))', gap: '1rem' }}>
                {Object.entries(schemaData.tables || {}).map(([tableName, tableInfo]) => (
                  <div key={tableName} className="neo-box" style={{ padding: '1rem' }}>
                    <div style={{ display: 'flex', alignItems: 'center', gap: '0.5rem', borderBottom: '1px solid var(--border-color)', paddingBottom: '0.5rem', marginBottom: '0.5rem' }}>
                      <Database size={16} style={{ color: 'var(--accent-color)' }} />
                      <strong style={{ fontSize: '0.9rem' }}>{tableName}</strong>
                    </div>

                    <div style={{ fontSize: '0.75rem' }}>
                      <p style={{ fontWeight: 600, color: 'var(--text-secondary)', marginBottom: '0.25rem' }}>Columns:</p>
                      <div style={{ display: 'flex', flexDirection: 'column', gap: '0.25rem' }}>
                        {Object.entries(tableInfo.columns || {}).map(([colName, colType]) => {
                          const isPk = tableInfo.primary_keys?.includes(colName);
                          return (
                            <div key={colName} style={{ display: 'flex', justifyContent: 'space-between', fontFamily: 'monospace', color: isPk ? 'var(--accent-color)' : 'inherit' }}>
                              <span>{colName} {isPk && '(PK)'}</span>
                              <span style={{ color: 'var(--text-secondary)' }}>{colType}</span>
                            </div>
                          );
                        })}
                      </div>

                      {tableInfo.foreign_keys && tableInfo.foreign_keys.length > 0 && (
                        <div style={{ marginTop: '0.75rem', borderTop: '1px dashed var(--border-color)', paddingTop: '0.5rem' }}>
                          <p style={{ fontWeight: 600, color: 'var(--text-secondary)', marginBottom: '0.25rem' }}>Foreign Keys:</p>
                          {tableInfo.foreign_keys.map((fk, idx) => (
                            <div key={idx} style={{ fontFamily: 'monospace', fontSize: '0.7rem', color: 'var(--text-secondary)' }}>
                              {fk.column} → {fk.references_table}.{fk.references_column}
                            </div>
                          ))}
                        </div>
                      )}
                    </div>
                  </div>
                ))}
              </div>
            </div>
          )}

          {/* Tab 3: Audit Logs */}
          {activeTab === 'audit' && (
            <div style={{ flex: 1, overflowY: 'auto', padding: '0 2rem 2rem 2rem' }}>
              <div style={{ marginBottom: '1.5rem', display: 'flex', justifyContent: 'space-between', alignItems: 'center' }}>
                <div>
                  <h3 style={{ fontSize: '1.1rem', fontWeight: 700 }}>Agent Audit Logs</h3>
                  <p style={{ color: 'var(--text-secondary)', fontSize: '0.8rem' }}>
                    Immutable log of all user questions, generated SQL, guardrail validations, and execution results.
                  </p>
                </div>
                <button className="neo-button secondary" style={{ fontSize: '0.75rem', padding: '0.3rem 0.6rem' }} onClick={fetchAuditLogs}>
                  <RefreshCw size={12} className={auditLoading ? 'spinning' : ''} /> Refresh Logs
                </button>
              </div>

              {auditLogs.length === 0 ? (
                <div style={{ border: '2px dashed var(--border-color)', borderRadius: '8px', padding: '3rem', textAlign: 'center', color: 'var(--text-secondary)' }}>
                  No audit logs found yet. Execute queries to see their trace.
                </div>
              ) : (
                <div style={{ display: 'flex', flexDirection: 'column', gap: '0.75rem' }}>
                  {auditLogs.map((log) => (
                    <div key={log.audit_id} className="neo-box" style={{ padding: '1rem' }}>
                      <div style={{ display: 'flex', justifyContent: 'space-between', borderBottom: '1px solid var(--border-color)', paddingBottom: '0.5rem', marginBottom: '0.5rem', fontSize: '0.75rem' }}>
                        <div>
                          <strong style={{ color: 'var(--accent-color)' }}>#{log.audit_id}</strong>
                          <span style={{ marginLeft: '0.5rem', color: 'var(--text-secondary)' }}>
                            {log.created_at ? new Date(log.created_at).toLocaleTimeString() : ''}
                          </span>
                        </div>
                        <div style={{ display: 'flex', gap: '0.5rem' }}>
                          <span className="status-badge" style={{ 
                            backgroundColor: log.validation_status === 'valid' ? 'var(--success-bg)' : 'var(--danger-bg)',
                            color: log.validation_status === 'valid' ? 'var(--success-text)' : 'var(--danger-text)',
                            border: `1px solid ${log.validation_status === 'valid' ? 'var(--success-border)' : 'var(--danger-border)'}`,
                            padding: '0.1rem 0.4rem',
                            fontSize: '0.65rem'
                          }}>
                            {log.validation_status ? log.validation_status.toUpperCase() : 'N/A'}
                          </span>
                          <span className="status-badge" style={{ 
                            backgroundColor: log.execution_status === 'success' ? 'var(--success-bg)' : 'var(--danger-bg)',
                            color: log.execution_status === 'success' ? 'var(--success-text)' : 'var(--danger-text)',
                            border: `1px solid ${log.execution_status === 'success' ? 'var(--success-border)' : 'var(--danger-border)'}`,
                            padding: '0.1rem 0.4rem',
                            fontSize: '0.65rem'
                          }}>
                            {log.execution_status ? log.execution_status.toUpperCase() : 'N/A'}
                          </span>
                        </div>
                      </div>

                      <div style={{ display: 'flex', flexDirection: 'column', gap: '0.5rem' }}>
                        <div>
                          <strong style={{ fontSize: '0.75rem', color: 'var(--text-secondary)' }}>QUESTION: </strong>
                          <span style={{ fontSize: '0.85rem' }}>{log.user_question}</span>
                        </div>

                        {log.generated_sql && (
                          <div>
                            <strong style={{ fontSize: '0.75rem', color: 'var(--text-secondary)' }}>SQL:</strong>
                            <div className="code-block" style={{ fontSize: '0.75rem', padding: '0.5rem', marginTop: '0.25rem' }}>
                              {log.generated_sql}
                            </div>
                          </div>
                        )}

                        <div style={{ display: 'grid', gridTemplateColumns: 'repeat(auto-fit, minmax(120px, 1fr))', gap: '0.5rem', backgroundColor: 'rgba(0,0,0,0.02)', padding: '0.5rem', borderRadius: '4px', border: '1px solid var(--border-color)', marginTop: '0.25rem' }}>
                          <div>
                            <strong style={{ fontSize: '0.75rem', color: 'var(--text-secondary)' }}>INTENT</strong>
                            <p style={{ fontSize: '0.8rem', fontWeight: 600 }}>{log.intent || 'N/A'}</p>
                          </div>
                          <div>
                            <strong style={{ fontSize: '0.75rem', color: 'var(--text-secondary)' }}>ROWS</strong>
                            <p style={{ fontSize: '0.8rem', fontWeight: 600 }}>{log.rows_affected !== null ? log.rows_affected : '0'}</p>
                          </div>
                          <div>
                            <strong style={{ fontSize: '0.75rem', color: 'var(--text-secondary)' }}>RETRIES</strong>
                            <p style={{ fontSize: '0.8rem', fontWeight: 600 }}>{log.retry_count || 0}</p>
                          </div>
                          {log.confirmation_status && (
                            <div>
                              <strong style={{ fontSize: '0.75rem', color: 'var(--text-secondary)' }}>CONFIRMATION</strong>
                              <p style={{ fontSize: '0.8rem', fontWeight: 600, color: log.confirmation_status === 'approved' ? 'var(--success-text)' : 'var(--warning-text)' }}>
                                {log.confirmation_status.toUpperCase()}
                              </p>
                            </div>
                          )}
                        </div>

                        {log.result_summary && (
                          <div>
                            <strong style={{ fontSize: '0.75rem', color: 'var(--text-secondary)' }}>RESULT SUMMARY:</strong>
                            <p style={{ fontSize: '0.75rem', fontFamily: 'monospace', color: 'var(--text-secondary)', backgroundColor: 'var(--bg-code)', padding: '0.4rem', borderRadius: '4px', border: '1px solid var(--border-color)', marginTop: '0.1rem' }}>
                              {log.result_summary}
                            </p>
                          </div>
                        )}

                        {log.error && (
                          <div>
                            <strong style={{ fontSize: '0.75rem', color: 'var(--danger-text)' }}>ERROR:</strong>
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
              {/* Button to Trace Observability in Big Dialog Box */}
              <button 
                className="neo-button primary" 
                style={{ width: '100%', padding: '0.65rem', gap: '0.5rem', fontWeight: 700, fontSize: '0.82rem' }}
                onClick={() => setShowObservabilityModal(true)}
              >
                <Activity size={16} /> Trace Observability
              </button>

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
            <div style={{ border: '2px dashed var(--border-color)', borderRadius: '8px', padding: '3rem 1.5rem', textAlign: 'center', color: 'var(--text-secondary)' }}>
              <Terminal size={32} style={{ margin: '0 auto 1rem auto', display: 'block', color: 'var(--accent-color)' }} />
              <p style={{ fontSize: '0.85rem' }}>
                No active inspection telemetry. Select any agent message inside the chat console to analyze.
              </p>
            </div>
          )}
        </section>
      </main>

      {/* Big Observability Modal Dialog Box */}
      {showObservabilityModal && (
        <div className="obs-dialog-backdrop" onClick={() => setShowObservabilityModal(false)}>
          <div className="obs-dialog-container" onClick={(e) => e.stopPropagation()}>
            <ObservabilityDashboard 
              currentTraceId={activeTraceId || selectedMessage?.traceId} 
              onClose={() => setShowObservabilityModal(false)} 
            />
          </div>
        </div>
      )}
    </div>
  );
}

export default App;
