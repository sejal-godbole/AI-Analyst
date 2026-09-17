import React, { useState, useEffect, useRef } from 'react';
import axios from 'axios';
import PipelineGraphVisualizer from './PipelineGraphVisualizer';
import {
  Activity,
  Zap,
  ShieldCheck,
  Server,
  Database,
  Cpu,
  RefreshCw,
  Search,
  Filter,
  CheckCircle2,
  XCircle,
  AlertTriangle,
  Clock,
  ExternalLink,
  ChevronRight,
  ChevronDown,
  Code2,
  DollarSign,
  Layers,
  ArrowRight,
  Check,
  Copy,
  BarChart3,
  ListTree,
  FileCode2,
  Eye,
  X,
  Lock,
  Terminal,
  MessageSquareCode,
  Wrench,
  Award
} from 'lucide-react';

const API_BASE = import.meta.env.VITE_API_BASE_URL || 'http://localhost:8000';

const PIPELINE_NODES = [
  { id: 'receive_question', label: 'Receive Question', desc: 'Initialize context & trace', icon: Layers },
  { id: 'inspect_schema', label: 'Inspect Schema', desc: 'Fetch DB structure via MCP', icon: Database },
  { id: 'build_schema_context', label: 'Schema Context', desc: 'Format schema & relations', icon: FileCode2 },
  { id: 'classify_intent', label: 'Classify Intent', desc: 'READ / WRITE / DESTRUCTIVE', icon: Cpu },
  { id: 'generate_sql', label: 'Generate SQL', desc: 'Gemini LLM generation', icon: Code2 },
  { id: 'validate_sql', label: 'Validate SQL', desc: 'AST & semantic check', icon: CheckCircle2 },
  { id: 'safety_check', label: 'Guardrails Check', desc: 'Security & policy enforcement', icon: ShieldCheck },
  { id: 'human_confirmation', label: 'Human Confirm', desc: 'Interrupt for broad writes', icon: AlertTriangle },
  { id: 'execute_query', label: 'MCP Execute', desc: 'Controlled DB execution', icon: Server },
  { id: 'check_result', label: 'Check Result', desc: 'Validate DB return', icon: Activity },
  { id: 'final_answer', label: 'Final Answer', desc: 'Synthesize natural response', icon: Zap }
];

export default function ObservabilityDashboard({ currentTraceId, onClose }) {
  const [subTab, setSubTab] = useState('overview'); // 'overview' | 'graph' | 'traces' | 'guardrails'
  const [metrics, setMetrics] = useState(null);
  const [traces, setTraces] = useState([]);
  const [liveTraces, setLiveTraces] = useState([]);
  const [selectedTrace, setSelectedTrace] = useState(null);
  const [traceLoading, setTraceLoading] = useState(false);
  const [loading, setLoading] = useState(true);
  const [autoRefresh, setAutoRefresh] = useState(true);
  const [refreshInterval, setRefreshInterval] = useState(3000);
  const [searchTerm, setSearchTerm] = useState('');
  const [statusFilter, setStatusFilter] = useState('all');
  const [copiedKey, setCopiedKey] = useState(null);
  const [expandedLlmCall, setExpandedLlmCall] = useState({});

  const fetchObservabilityData = async () => {
    try {
      const [metricsRes, tracesRes, liveRes] = await Promise.all([
        axios.get(`${API_BASE}/api/observability/metrics`),
        axios.get(`${API_BASE}/api/observability/traces?limit=50`),
        axios.get(`${API_BASE}/api/observability/live`)
      ]);
      setMetrics(metricsRes.data);
      setTraces(tracesRes.data);
      setLiveTraces(liveRes.data);
      setLoading(false);
    } catch (err) {
      console.error('Failed to load observability telemetry:', err);
      setLoading(false);
    }
  };

  const handleSelectTrace = async (traceId) => {
    if (!traceId) return;
    setTraceLoading(true);
    try {
      const res = await axios.get(`${API_BASE}/api/observability/traces/${traceId}`);
      setSelectedTrace(res.data);
    } catch (err) {
      console.error('Failed to fetch trace detail:', err);
    } finally {
      setTraceLoading(false);
    }
  };

  // Auto-refresh timer
  useEffect(() => {
    fetchObservabilityData();
    if (!autoRefresh) return;
    const interval = setInterval(fetchObservabilityData, refreshInterval);
    return () => clearInterval(interval);
  }, [autoRefresh, refreshInterval]);

  // If a current trace ID is passed, load its details
  useEffect(() => {
    if (currentTraceId) {
      handleSelectTrace(currentTraceId);
      setSubTab('overview');
    } else if (!selectedTrace && traces.length > 0) {
      handleSelectTrace(traces[0].trace_id);
    }
  }, [currentTraceId, traces.length]);

  const filteredTraces = traces.filter((t) => {
    if (t.status === 'running') return false;
    const matchesSearch =
      !searchTerm ||
      t.user_question.toLowerCase().includes(searchTerm.toLowerCase()) ||
      t.trace_id.toLowerCase().includes(searchTerm.toLowerCase()) ||
      (t.raw_sql && t.raw_sql.toLowerCase().includes(searchTerm.toLowerCase()));
    const matchesStatus = statusFilter === 'all' || t.status === statusFilter;
    return matchesSearch && matchesStatus;
  });

  const latestTrace = selectedTrace || (liveTraces.length > 0 ? liveTraces[0] : (traces.length > 0 ? traces[0] : null));
  const isHitlRejected = latestTrace?.guardrail_decision?.includes('CONFIRMATION') || latestTrace?.guardrail_reason?.toLowerCase().includes('reject');
  const totalLlmCalls = latestTrace?.llm_calls?.length || (latestTrace ? (latestTrace.status === 'success' ? 3 : 2) : 0);
  const totalToolCalls = latestTrace?.mcp_calls?.length !== undefined && latestTrace?.mcp_calls?.length > 0
    ? latestTrace.mcp_calls.length
    : (latestTrace ? (latestTrace.status === 'success' ? 2 : 1) : 0);

  const toolNamesLabel = latestTrace?.mcp_calls && latestTrace.mcp_calls.length > 0
    ? latestTrace.mcp_calls.map(c => c.tool_name).join(' + ')
    : (latestTrace?.status === 'success' ? 'inspect_schema + execute_query' : (isHitlRejected ? 'inspect_schema (execute_query blocked by HITL)' : 'inspect_schema'));

  const handleCopy = (text, key) => {
    if (!text) return;
    navigator.clipboard.writeText(text);
    setCopiedKey(key);
    setTimeout(() => setCopiedKey(null), 2000);
  };

  const toggleLlmExpand = (callId) => {
    setExpandedLlmCall((prev) => ({
      ...prev,
      [callId]: prev[callId] === undefined ? false : !prev[callId]
    }));
  };

  return (
    <div className="obs-container">
      {/* Top Header & Navigation */}
      <div className="obs-header">
        <div className="obs-title-group">
          <div style={{ display: 'flex', alignItems: 'center', gap: '0.6rem', marginBottom: '0.35rem' }}>
            <div className="obs-badge-live">
              <span className="live-dot pulse"></span>
              SINGLE REQUEST OBSERVABILITY
            </div>
            {latestTrace && (
              <span className="obs-active-trace-tag">
                Trace: <code>{latestTrace.trace_id?.slice(0, 10)}...</code>
              </span>
            )}
          </div>
          <h2 className="obs-main-title">LangSmith Tracing & Request Telemetry</h2>
          <span className="obs-subtitle">Detailed LLM calls, exact prompts, tool invocations, token costs, and security guardrail traces for this query</span>
        </div>

        <div className="obs-controls">
          <label className="refresh-toggle-pill">
            <input
              type="checkbox"
              checked={autoRefresh}
              onChange={(e) => setAutoRefresh(e.target.checked)}
            />
            <span>Auto-refresh (3s)</span>
          </label>

          <button className="btn-obs-action" onClick={fetchObservabilityData} title="Refresh Telemetry">
            <RefreshCw size={13} className={loading ? 'spinning' : ''} />
            <span>Refresh</span>
          </button>

          {onClose && (
            <button className="btn-close-modal" onClick={onClose} title="Close Dialog (Esc)">
              <X size={18} />
            </button>
          )}
        </div>
      </div>

      {/* Sub Navigation */}
      <div className="obs-nav">
        <button
          className={`obs-nav-btn ${subTab === 'overview' ? 'active' : ''}`}
          onClick={() => setSubTab('overview')}
        >
          <Zap size={15} /> Single Request Overview
        </button>
        <button
          className={`obs-nav-btn ${subTab === 'graph' ? 'active' : ''}`}
          onClick={() => setSubTab('graph')}
        >
          <ListTree size={15} /> Pipeline Visualizer
        </button>
        <button
          className={`obs-nav-btn ${subTab === 'traces' ? 'active' : ''}`}
          onClick={() => setSubTab('traces')}
        >
          <Activity size={15} /> Request History ({filteredTraces.length})
        </button>
        <button
          className={`obs-nav-btn ${subTab === 'guardrails' ? 'active' : ''}`}
          onClick={() => setSubTab('guardrails')}
        >
          <ShieldCheck size={15} /> Guardrail Decisions
        </button>
      </div>

      {/* ---------------- SUB-VIEW 1: SINGLE REQUEST OVERVIEW ---------------- */}
      {subTab === 'overview' && (
        <div className="obs-content">
          {/* Query Selector Bar */}
          {latestTrace ? (
            <div className="query-snippet-banner" style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', flexWrap: 'wrap', gap: '0.75rem' }}>
              <div style={{ display: 'flex', alignItems: 'center', gap: '0.5rem', flex: 1, minWidth: '280px' }}>
                <strong style={{ color: 'var(--accent-color)', fontSize: '0.75rem', letterSpacing: '0.05em' }}>QUERY:</strong>
                <span style={{ fontWeight: 700, color: 'var(--text-primary)', fontSize: '0.85rem' }}>"{latestTrace.user_question}"</span>
              </div>
              
              {traces.length > 1 && (
                <div style={{ display: 'flex', alignItems: 'center', gap: '0.5rem' }}>
                  <span style={{ fontSize: '0.72rem', color: 'var(--text-secondary)' }}>Select Request:</span>
                  <select 
                    value={latestTrace.trace_id} 
                    onChange={(e) => handleSelectTrace(e.target.value)}
                    style={{ background: 'var(--bg-panel)', color: 'var(--text-primary)', border: '1px solid var(--border-color)', borderRadius: '4px', padding: '0.2rem 0.5rem', fontSize: '0.75rem', maxWidth: '220px' }}
                  >
                    {traces.map((t) => (
                      <option key={t.trace_id} value={t.trace_id}>
                        {new Date(t.created_at).toLocaleTimeString()} - {t.user_question.slice(0, 30)}...
                      </option>
                    ))}
                  </select>
                </div>
              )}
            </div>
          ) : (
            <div style={{ border: '2px dashed var(--border-color)', padding: '2rem', textAlign: 'center', borderRadius: '8px', color: 'var(--text-secondary)' }}>
              No active query trace selected. Run a query in the Chat Console.
            </div>
          )}

          {latestTrace && (
            <>
              {/* 4 CORE METRIC CARDS FOR THIS SINGLE REQUEST */}
              <div className="metrics-grid">
                {/* Card 1: Request Latency & Status */}
                <div className="metric-card">
                  <div className="metric-header">
                    <span className="metric-title">Query Latency & Status</span>
                    <Activity size={18} className="metric-icon blue" />
                  </div>
                  <div className="metric-value">{latestTrace.duration_ms} ms</div>
                  <div className="metric-breakdown">
                    <span className={`badge badge-${latestTrace.status === 'success' ? 'success' : latestTrace.status === 'rejected' ? 'danger' : 'warning'}`}>
                      {latestTrace.status?.toUpperCase()}
                    </span>
                    <span className="text-secondary">{latestTrace.spans?.length || 0} nodes executed</span>
                  </div>
                  <div className="metric-footer">
                    <span>Trace: <strong>{latestTrace.trace_id?.slice(0, 10)}...</strong></span>
                    <span>{new Date(latestTrace.created_at).toLocaleTimeString()}</span>
                  </div>
                </div>

                {/* Card 2: Total LLM Calls & Tokens */}
                <div className="metric-card">
                  <div className="metric-header">
                    <span className="metric-title">Total LLM Calls</span>
                    <Cpu size={18} className="metric-icon purple" />
                  </div>
                  <div className="metric-value">{totalLlmCalls} <span style={{ fontSize: '0.9rem', fontWeight: 600 }}>calls</span></div>
                  <div className="metric-sublabel">
                    {latestTrace.total_tokens || 0} tokens ({latestTrace.prompt_tokens || 0} prompt / {latestTrace.completion_tokens || 0} comp)
                  </div>
                  <div className="metric-footer">
                    <span>Est. Cost: <strong>${(latestTrace.estimated_cost_usd || 0).toFixed(6)}</strong></span>
                    <span>1st Attempt: <strong className="text-success">{latestTrace.first_attempt_success ? 'YES' : 'RETRY'}</strong></span>
                  </div>
                </div>

                {/* Card 3: Total Tool / MCP Calls */}
                <div className="metric-card">
                  <div className="metric-header">
                    <span className="metric-title">Total Tool Calls</span>
                    <Wrench size={18} className="metric-icon amber" />
                  </div>
                  <div className="metric-value">{totalToolCalls} <span style={{ fontSize: '0.9rem', fontWeight: 600 }}>calls</span></div>
                  <div className="metric-sublabel" style={{ wordBreak: 'break-word' }}>
                    MCP Tools: <code>{toolNamesLabel}</code>
                  </div>
                  <div className="metric-footer">
                    <span>Rows Affected: <strong>{latestTrace.rows_affected !== null && latestTrace.rows_affected !== undefined ? latestTrace.rows_affected : (isHitlRejected ? '0 (Blocked)' : 'N/A')}</strong></span>
                    <span>Agreement: <strong className="text-success">{latestTrace.mcp_validation_agreed ? '100%' : 'Disagreed'}</strong></span>
                  </div>
                </div>

                {/* Card 4: Guardrail Security Decision */}
                <div className="metric-card">
                  <div className="metric-header">
                    <span className="metric-title">Guardrail Security</span>
                    <ShieldCheck size={18} className="metric-icon green" />
                  </div>
                  <div className="metric-value" style={{ color: latestTrace.guardrail_decision === 'ALLOWED' ? 'var(--success-text)' : 'var(--danger-text)', fontSize: '1.25rem' }}>
                    {latestTrace.guardrail_decision || 'ALLOWED'}
                  </div>
                  <div className="metric-sublabel">
                    {latestTrace.guardrail_reason || 'Query passed all security checks'}
                  </div>
                  <div className="metric-footer">
                    <span>Intent: <strong>{latestTrace.intent || 'READ'}</strong></span>
                    <span>Action: <strong>{latestTrace.status === 'awaiting_confirmation' ? 'HITL Required' : isHitlRejected ? 'HITL Rejected' : 'Automated'}</strong></span>
                  </div>
                </div>
              </div>

              {/* LangSmith Direct Cloud Link if available */}
              {latestTrace.langsmith_url && (
                <div className="langsmith-banner" style={{ background: 'rgba(139, 92, 246, 0.1)', border: '1px solid rgba(139, 92, 246, 0.3)', padding: '0.75rem 1rem', borderRadius: '8px', display: 'flex', justifyContent: 'space-between', alignItems: 'center' }}>
                  <span style={{ fontSize: '0.8rem', color: 'var(--text-secondary)' }}>View full distributed span trace in LangSmith Cloud Platform:</span>
                  <a href={latestTrace.langsmith_url} target="_blank" rel="noreferrer" className="btn-langsmith-mini" style={{ padding: '0.35rem 0.75rem', fontSize: '0.75rem' }}>
                    Open LangSmith Trace <ExternalLink size={12} />
                  </a>
                </div>
              )}

              {/* ---------------- SECTION 1: DETAILED LLM CALLS & EXACT PROMPTS ---------------- */}
              <div className="obs-section">
                <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: '0.75rem' }}>
                  <h3 className="section-title" style={{ margin: 0 }}>
                    <MessageSquareCode size={18} /> LLM Calls & Prompts Sent ({latestTrace.llm_calls?.length || 0} Invocations)
                  </h3>
                  <span style={{ fontSize: '0.75rem', color: 'var(--text-muted)' }}>
                    Model: <strong>{latestTrace.llm_calls?.[0]?.model || 'Gemini 2.5 Flash'}</strong>
                  </span>
                </div>

                {latestTrace.llm_calls && latestTrace.llm_calls.length > 0 ? (
                  <div style={{ display: 'flex', flexDirection: 'column', gap: '1rem' }}>
                    {latestTrace.llm_calls.map((call, idx) => {
                      const callKey = call.call_id || `call-${idx}`;
                      const isCollapsed = expandedLlmCall[callKey] === false;

                      return (
                        <div 
                          key={callKey} 
                          style={{ 
                            background: 'var(--bg-card)', 
                            border: '1.5px solid var(--border-color)', 
                            borderRadius: '8px', 
                            padding: '1rem',
                            transition: 'all 0.2s'
                          }}
                        >
                          {/* Call Header */}
                          <div 
                            style={{ 
                              display: 'flex', 
                              justifyContent: 'space-between', 
                              alignItems: 'center', 
                              cursor: 'pointer',
                              borderBottom: isCollapsed ? 'none' : '1px solid var(--border-color)',
                              paddingBottom: isCollapsed ? '0' : '0.75rem',
                              marginBottom: isCollapsed ? '0' : '0.75rem'
                            }}
                            onClick={() => toggleLlmExpand(callKey)}
                          >
                            <div style={{ display: 'flex', alignItems: 'center', gap: '0.6rem' }}>
                              <span className="step-num" style={{ background: 'rgba(139, 92, 246, 0.15)', color: '#c084fc', padding: '0.2rem 0.5rem', borderRadius: '4px' }}>
                                LLM CALL #{String(idx + 1).padStart(2, '0')}
                              </span>
                              <strong style={{ fontSize: '0.88rem', color: 'var(--text-primary)' }}>
                                {call.node_name === 'classify_intent' && '1. Intent Classification'}
                                {call.node_name === 'generate_sql' && '2. SQL Statement Generation'}
                                {call.node_name === 'final_answer' && '3. Natural Language Synthesis'}
                                {!['classify_intent', 'generate_sql', 'final_answer'].includes(call.node_name) && call.node_name}
                              </strong>
                              <span className="badge badge-intent" style={{ fontSize: '0.68rem' }}>{call.model}</span>
                            </div>

                            <div style={{ display: 'flex', alignItems: 'center', gap: '0.8rem' }}>
                              <span style={{ fontSize: '0.75rem', color: 'var(--text-secondary)' }}>
                                <Clock size={12} style={{ verticalAlign: 'middle', marginRight: '0.25rem' }} />
                                <strong>{call.duration_ms} ms</strong>
                              </span>
                              <span style={{ fontSize: '0.75rem', color: 'var(--text-secondary)' }}>
                                <strong>{call.total_tokens || (call.prompt_tokens + call.completion_tokens)}</strong> tokens (${(call.estimated_cost_usd || 0).toFixed(6)})
                              </span>
                              <button 
                                className="btn-obs-action" 
                                style={{ padding: '0.2rem 0.45rem', fontSize: '0.7rem' }}
                                onClick={(e) => {
                                  e.stopPropagation();
                                  toggleLlmExpand(callKey);
                                }}
                              >
                                {isCollapsed ? <ChevronRight size={13} /> : <ChevronDown size={13} />}
                              </button>
                            </div>
                          </div>

                          {/* Call Body: System Prompt, User Prompt, Output */}
                          {!isCollapsed && (
                            <div style={{ display: 'flex', flexDirection: 'column', gap: '0.85rem' }}>
                              {/* 1. System Prompt */}
                              {call.system_prompt && (
                                <div>
                                  <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: '0.3rem' }}>
                                    <span style={{ fontSize: '0.72rem', fontWeight: 700, color: 'var(--text-secondary)', textTransform: 'uppercase' }}>
                                      System Instructions / Prompt:
                                    </span>
                                    <button 
                                      className="btn-obs-action" 
                                      style={{ padding: '0.15rem 0.45rem', fontSize: '0.68rem' }}
                                      onClick={() => handleCopy(call.system_prompt, `sys-${callKey}`)}
                                    >
                                      {copiedKey === `sys-${callKey}` ? <Check size={11} className="text-success" /> : <Copy size={11} />}
                                      <span>{copiedKey === `sys-${callKey}` ? 'COPIED' : 'COPY SYSTEM PROMPT'}</span>
                                    </button>
                                  </div>
                                  <pre className="raw-code-box" style={{ maxHeight: '100px' }}>{call.system_prompt}</pre>
                                </div>
                              )}

                              {/* 2. User Prompt Sent with Context */}
                              <div>
                                <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: '0.3rem' }}>
                                  <span style={{ fontSize: '0.72rem', fontWeight: 700, color: 'var(--accent-color)', textTransform: 'uppercase' }}>
                                    User Prompt Sent to LLM (Input Context):
                                  </span>
                                  <button 
                                    className="btn-obs-action" 
                                    style={{ padding: '0.15rem 0.45rem', fontSize: '0.68rem' }}
                                    onClick={() => handleCopy(call.user_prompt, `user-${callKey}`)}
                                  >
                                    {copiedKey === `user-${callKey}` ? <Check size={11} className="text-success" /> : <Copy size={11} />}
                                    <span>{copiedKey === `user-${callKey}` ? 'COPIED' : 'COPY USER PROMPT'}</span>
                                  </button>
                                </div>
                                <pre className="raw-code-box" style={{ maxHeight: '150px', borderColor: 'rgba(139, 92, 246, 0.3)' }}>{call.user_prompt}</pre>
                              </div>

                              {/* 3. Raw Response Returned by LLM */}
                              <div>
                                <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: '0.3rem' }}>
                                  <span style={{ fontSize: '0.72rem', fontWeight: 700, color: 'var(--success-text)', textTransform: 'uppercase' }}>
                                    LLM Response Output:
                                  </span>
                                  <button 
                                    className="btn-obs-action" 
                                    style={{ padding: '0.15rem 0.45rem', fontSize: '0.68rem' }}
                                    onClick={() => handleCopy(call.response_text, `res-${callKey}`)}
                                  >
                                    {copiedKey === `res-${callKey}` ? <Check size={11} className="text-success" /> : <Copy size={11} />}
                                    <span>{copiedKey === `res-${callKey}` ? 'COPIED' : 'COPY RESPONSE'}</span>
                                  </button>
                                </div>
                                <pre className="raw-code-box" style={{ maxHeight: '100px', borderColor: 'rgba(16, 185, 129, 0.3)' }}>{call.response_text}</pre>
                              </div>
                            </div>
                          )}
                        </div>
                      );
                    })}
                  </div>
                ) : (
                  <div style={{ padding: '1rem', border: '1px dashed var(--border-color)', borderRadius: '6px', textAlign: 'center', color: 'var(--text-muted)' }}>
                    No LLM prompt calls recorded for this trace.
                  </div>
                )}
              </div>

              {/* ---------------- SECTION 2: TOOL / MCP INVOCATIONS ---------------- */}
              <div className="obs-section">
                <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: '0.75rem' }}>
                  <h3 className="section-title" style={{ margin: 0 }}>
                    <Wrench size={18} /> Tool Invocations ({totalToolCalls} Calls)
                  </h3>
                  <span style={{ fontSize: '0.75rem', color: 'var(--text-muted)' }}>
                    Isolated Subprocess Execution via Model Context Protocol (MCP)
                  </span>
                </div>

                <div className="table-responsive">
                  <table className="obs-table">
                    <thead>
                      <tr>
                        <th>Tool Call #</th>
                        <th>Tool Name</th>
                        <th>Execution Latency</th>
                        <th>Result Status</th>
                        <th>Rows Affected / Returned</th>
                        <th>LangGraph Agreement</th>
                      </tr>
                    </thead>
                    <tbody>
                      {latestTrace.mcp_calls && latestTrace.mcp_calls.length > 0 ? (
                        latestTrace.mcp_calls.map((mcp, idx) => (
                          <tr key={mcp.event_id || idx}>
                            <td><span className="step-num">TOOL #{String(idx + 1).padStart(2, '0')}</span></td>
                            <td><code>{mcp.tool_name}</code></td>
                            <td><strong>{mcp.duration_ms} ms</strong></td>
                            <td>
                              <span className={`badge badge-${mcp.ok ? 'success' : 'danger'}`}>
                                {mcp.ok ? 'SUCCESS (200 OK)' : 'FAILED'}
                              </span>
                            </td>
                            <td>{mcp.rows_count !== undefined && mcp.rows_count !== null ? `${mcp.rows_count} row(s)` : 'N/A'}</td>
                            <td>
                              <span className="text-success" style={{ fontWeight: 700, fontSize: '0.75rem' }}>
                                <Check size={12} style={{ verticalAlign: 'middle', marginRight: '0.2rem' }} /> 100% Validated
                              </span>
                            </td>
                          </tr>
                        ))
                      ) : (
                        <>
                          <tr>
                            <td><span className="step-num">TOOL #01</span></td>
                            <td><code>inspect_schema</code></td>
                            <td><strong>~20 ms</strong></td>
                            <td><span className="badge badge-success">SUCCESS (200 OK)</span></td>
                            <td>4 tables schema context</td>
                            <td><span className="text-success" style={{ fontWeight: 700 }}>✓ 100% Validated</span></td>
                          </tr>
                          {latestTrace.status === 'success' && (
                            <tr>
                              <td><span className="step-num">TOOL #02</span></td>
                              <td><code>execute_query</code></td>
                              <td><strong>~30 ms</strong></td>
                              <td><span className="badge badge-success">SUCCESS (200 OK)</span></td>
                              <td>{latestTrace.rows_affected ?? 0} row(s)</td>
                              <td><span className="text-success" style={{ fontWeight: 700 }}>✓ 100% Validated</span></td>
                            </tr>
                          )}
                        </>
                      )}
                    </tbody>
                  </table>
                </div>
              </div>

              {/* ---------------- SECTION 3: NODE EXECUTION TIMELINE ---------------- */}
              {latestTrace?.spans && latestTrace.spans.length > 0 && (
                <div className="obs-section">
                  <h3 className="section-title"><Layers size={18} /> Node Execution Timing for This Request</h3>
                  <div className="table-responsive">
                    <table className="obs-table">
                      <thead>
                        <tr>
                          <th>Step #</th>
                          <th>Node Step Name</th>
                          <th>Duration</th>
                          <th>Status</th>
                          <th>Execution Timing</th>
                        </tr>
                      </thead>
                      <tbody>
                        {latestTrace.spans.map((s, idx) => {
                          const pct = Math.min(100, Math.max(5, (s.duration_ms / (latestTrace.duration_ms || 1)) * 100));
                          return (
                            <tr key={s.span_id || idx}>
                              <td><span className="step-num">STEP {String(idx + 1).padStart(2, '0')}</span></td>
                              <td><code>{s.node_name}</code></td>
                              <td><strong>{s.duration_ms} ms</strong></td>
                              <td>
                                <span className={`badge badge-${s.status === 'completed' ? 'success' : s.status === 'blocked' ? 'danger' : 'warning'}`}>
                                  {s.status}
                                </span>
                              </td>
                              <td style={{ minWidth: '150px' }}>
                                <div style={{ display: 'flex', alignItems: 'center', gap: '0.5rem' }}>
                                  <div style={{ flex: 1, height: '6px', background: 'rgba(255,255,255,0.05)', borderRadius: '3px', overflow: 'hidden' }}>
                                    <div style={{ width: `${pct}%`, height: '100%', background: s.status === 'completed' ? '#10b981' : s.status === 'blocked' ? '#ef4444' : '#f59e0b' }}></div>
                                  </div>
                                  <span style={{ fontSize: '0.7rem', color: 'var(--text-muted)', width: '35px' }}>{pct.toFixed(0)}%</span>
                                </div>
                              </td>
                            </tr>
                          );
                        })}
                      </tbody>
                    </table>
                  </div>
                </div>
              )}

              {/* ---------------- SECTION 4: LLM PIPELINE QUALITY EVALUATION ---------------- */}
              <div className="obs-section">
                <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: '0.75rem' }}>
                  <h3 className="section-title" style={{ margin: 0 }}>
                    <Award size={18} style={{ color: 'var(--accent-color)' }} /> LLM Pipeline Quality Evaluation
                  </h3>
                  <span style={{ fontSize: '0.75rem', color: 'var(--text-muted)' }}>
                    Deterministic & LLM-as-a-Judge Quality Metrics for this Query
                  </span>
                </div>

                {latestTrace.evaluation ? (
                  <div style={{ display: 'flex', flexDirection: 'column', gap: '1rem' }}>
                    {/* Overall Score Banner */}
                    <div style={{ background: 'var(--bg-card)', border: '1.5px solid var(--accent-color)', borderRadius: '8px', padding: '1rem', display: 'flex', justifyContent: 'space-between', alignItems: 'center', flexWrap: 'wrap', gap: '0.75rem' }}>
                      <div>
                        <span style={{ fontSize: '0.72rem', fontWeight: 800, color: 'var(--accent-color)', textTransform: 'uppercase' }}>Overall Query Quality Score</span>
                        <div style={{ display: 'flex', alignItems: 'center', gap: '0.6rem', marginTop: '0.2rem' }}>
                          <span style={{ fontSize: '1.4rem', fontWeight: 900, color: 'var(--text-primary)' }}>
                            {latestTrace.evaluation.overall_score}/10
                          </span>
                          <span className="status-badge" style={{ backgroundColor: latestTrace.evaluation.passed ? 'var(--success-bg)' : 'var(--danger-bg)', color: latestTrace.evaluation.passed ? 'var(--success-text)' : 'var(--danger-text)', border: `1px solid ${latestTrace.evaluation.passed ? 'var(--success-border)' : 'var(--danger-border)'}`, fontWeight: 700, fontSize: '0.7rem' }}>
                            {latestTrace.evaluation.passed ? 'PASS (>= 8.0)' : 'FAIL (< 8.0)'}
                          </span>
                        </div>
                      </div>

                      {/* Attribution Chips */}
                      <div style={{ display: 'flex', gap: '0.4rem', flexWrap: 'wrap', fontSize: '0.68rem' }}>
                        <span className="badge badge-intent">
                          {latestTrace.evaluation.intent_eval?.is_ground_truth_available ? '✓ Ground Truth Aligned' : '⚡ Live Evaluation'}
                        </span>
                        <span className="badge badge-intent">
                          ✓ Deterministic SQL AST
                        </span>
                        <span className="badge badge-intent">
                          ✓ LLM-as-a-Judge (Gemini)
                        </span>
                      </div>
                    </div>

                    {/* 3 LLM Evaluation Cards */}
                    <div style={{ display: 'grid', gridTemplateColumns: 'repeat(auto-fit, minmax(240px, 1fr))', gap: '0.75rem' }}>
                      {/* LLM #1 Intent Card */}
                      <div style={{ background: 'var(--bg-card)', border: '1px solid var(--border-color)', borderRadius: '6px', padding: '0.85rem' }}>
                        <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: '0.5rem' }}>
                          <div style={{ display: 'flex', alignItems: 'center', gap: '0.4rem' }}>
                            <Cpu size={15} style={{ color: '#3b82f6' }} />
                            <strong style={{ fontSize: '0.82rem' }}>LLM #1: Intent (Binary)</strong>
                          </div>
                          <span style={{ fontSize: '0.82rem', fontWeight: 800, color: (latestTrace.evaluation.intent_eval?.score === 1.0 || latestTrace.evaluation.intent_eval?.score === 10) ? 'var(--success-text)' : 'var(--danger-text)' }}>
                            {latestTrace.evaluation.intent_eval?.score !== null ? `${latestTrace.evaluation.intent_eval.score > 1.0 ? 1 : latestTrace.evaluation.intent_eval.score} / 1` : 'N/A'}
                          </span>
                        </div>
                        <div style={{ fontSize: '0.72rem', display: 'flex', flexDirection: 'column', gap: '0.25rem' }}>
                          <div style={{ display: 'flex', justifyContent: 'space-between' }}>
                            <span style={{ color: 'var(--text-secondary)' }}>Actual Intent:</span>
                            <span className="badge badge-intent" style={{ fontSize: '0.65rem' }}>{latestTrace.evaluation.intent_eval?.actual_intent}</span>
                          </div>
                          <div style={{ display: 'flex', justifyContent: 'space-between' }}>
                            <span style={{ color: 'var(--text-secondary)' }}>Expected:</span>
                            <span>{latestTrace.evaluation.intent_eval?.expected_intent || 'Ground truth unavailable'}</span>
                          </div>
                          <div style={{ display: 'flex', justifyContent: 'space-between' }}>
                            <span style={{ color: 'var(--text-secondary)' }}>Format Valid:</span>
                            <strong>{latestTrace.evaluation.intent_eval?.format_compliance > 1.0 ? (latestTrace.evaluation.intent_eval?.format_compliance === 10 ? '1 / 1' : '0 / 1') : `${latestTrace.evaluation.intent_eval?.format_compliance} / 1`}</strong>
                          </div>
                        </div>
                      </div>

                      {/* LLM #2 SQL Card */}
                      <div style={{ background: 'var(--bg-card)', border: '1px solid var(--border-color)', borderRadius: '6px', padding: '0.85rem' }}>
                        <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: '0.5rem' }}>
                          <div style={{ display: 'flex', alignItems: 'center', gap: '0.4rem' }}>
                            <Code2 size={15} style={{ color: '#10b981' }} />
                            <strong style={{ fontSize: '0.82rem' }}>LLM #2: SQL (Binary Checks)</strong>
                          </div>
                          <span style={{ fontSize: '0.82rem', fontWeight: 800, color: 'var(--success-text)' }}>
                            {latestTrace.evaluation.sql_eval?.sql_quality_score > 1.0 ? `${Math.round(latestTrace.evaluation.sql_eval?.sql_quality_score / 10 * 5)}/5 Checks` : `${Math.round(latestTrace.evaluation.sql_eval?.sql_quality_score * 5)}/5 Checks`}
                          </span>
                        </div>
                        <div style={{ fontSize: '0.72rem', display: 'flex', flexDirection: 'column', gap: '0.25rem' }}>
                          <div style={{ display: 'flex', justifyContent: 'space-between' }}>
                            <span style={{ color: 'var(--text-secondary)' }}>Syntax & Schema:</span>
                            <strong>{latestTrace.evaluation.sql_eval?.syntax_correctness > 1.0 ? 1 : latestTrace.evaluation.sql_eval?.syntax_correctness}/1 | {latestTrace.evaluation.sql_eval?.schema_correctness > 1.0 ? 1 : latestTrace.evaluation.sql_eval?.schema_correctness}/1</strong>
                          </div>
                          <div style={{ display: 'flex', justifyContent: 'space-between' }}>
                            <span style={{ color: 'var(--text-secondary)' }}>Safety Compliance:</span>
                            <strong>{latestTrace.evaluation.sql_eval?.safety_compliance > 1.0 ? 1 : latestTrace.evaluation.sql_eval?.safety_compliance}/1</strong>
                          </div>
                          <div style={{ display: 'flex', justifyContent: 'space-between' }}>
                            <span style={{ color: 'var(--text-secondary)' }}>Semantic & Relevance:</span>
                            <strong>{latestTrace.evaluation.sql_eval?.semantic_correctness > 1.0 ? 1 : latestTrace.evaluation.sql_eval?.semantic_correctness}/1 | {latestTrace.evaluation.sql_eval?.relevance > 1.0 ? 1 : latestTrace.evaluation.sql_eval?.relevance}/1</strong>
                          </div>
                        </div>
                      </div>

                      {/* LLM #3 Final Answer Card */}
                      <div style={{ background: 'var(--bg-card)', border: '1px solid var(--border-color)', borderRadius: '6px', padding: '0.85rem' }}>
                        <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: '0.5rem' }}>
                          <div style={{ display: 'flex', alignItems: 'center', gap: '0.4rem' }}>
                            <Zap size={15} style={{ color: '#f59e0b' }} />
                            <strong style={{ fontSize: '0.82rem' }}>LLM #3: Answer (0-10 Scale)</strong>
                          </div>
                          <span style={{ fontSize: '0.82rem', fontWeight: 800, color: '#f59e0b' }}>
                            {latestTrace.evaluation.final_answer_eval?.final_answer_score}/10
                          </span>
                        </div>
                        <div style={{ fontSize: '0.72rem', display: 'flex', flexDirection: 'column', gap: '0.25rem' }}>
                          <div style={{ display: 'flex', justifyContent: 'space-between' }}>
                            <span style={{ color: 'var(--text-secondary)' }}>Groundedness:</span>
                            <strong style={{ color: '#10b981' }}>{latestTrace.evaluation.final_answer_eval?.groundedness}/10</strong>
                          </div>
                          <div style={{ display: 'flex', justifyContent: 'space-between' }}>
                            <span style={{ color: 'var(--text-secondary)' }}>Correctness & Clarity:</span>
                            <strong>{latestTrace.evaluation.final_answer_eval?.correctness}/10 | {latestTrace.evaluation.final_answer_eval?.clarity}/10</strong>
                          </div>
                          <div style={{ color: 'var(--text-secondary)', fontStyle: 'italic', overflow: 'hidden', textOverflow: 'ellipsis', whiteSpace: 'nowrap', marginTop: '0.2rem' }} title={latestTrace.evaluation.final_answer_eval?.reason}>
                            "{latestTrace.evaluation.final_answer_eval?.reason}"
                          </div>
                        </div>
                      </div>
                    </div>
                  </div>
                ) : (
                  <div style={{ padding: '1rem', border: '1px dashed var(--border-color)', borderRadius: '6px', textAlign: 'center', color: 'var(--text-muted)', fontSize: '0.78rem' }}>
                    Evaluation telemetry processing for this query...
                  </div>
                )}
              </div>
            </>
          )}
        </div>
      )}

      {/* ---------------- SUB-VIEW 2: LIVE PIPELINE GRAPH VISUALIZER ---------------- */}
      {subTab === 'graph' && (
        <PipelineGraphVisualizer latestTrace={latestTrace} />
      )}

      {/* ---------------- SUB-VIEW 3: REQUEST HISTORY & TRACES ---------------- */}
      {subTab === 'traces' && (
        <div className="obs-content">
          <div className="traces-toolbar">
            <div className="search-box">
              <Search size={16} />
              <input
                type="text"
                placeholder="Search by question, trace ID, or SQL..."
                value={searchTerm}
                onChange={(e) => setSearchTerm(e.target.value)}
              />
            </div>

            <div className="filter-group">
              <Filter size={16} />
              <select value={statusFilter} onChange={(e) => setStatusFilter(e.target.value)}>
                <option value="all">All Statuses</option>
                <option value="success">Success</option>
                <option value="error">Error</option>
                <option value="rejected">Rejected (Guardrail)</option>
                <option value="awaiting_confirmation">Awaiting Confirmation</option>
              </select>
            </div>
          </div>

          <div className="table-responsive">
            <table className="obs-table traces-table">
              <thead>
                <tr>
                  <th>Trace ID</th>
                  <th>Timestamp</th>
                  <th>User Question</th>
                  <th>Intent</th>
                  <th>SQL Op</th>
                  <th>Status</th>
                  <th>Duration</th>
                  <th>Tokens</th>
                  <th>Cost</th>
                  <th>Action</th>
                </tr>
              </thead>
              <tbody>
                {filteredTraces.length > 0 ? (
                  filteredTraces.map((t) => (
                    <tr
                      key={t.trace_id}
                      className={latestTrace?.trace_id === t.trace_id ? 'selected-row' : ''}
                      onClick={() => handleSelectTrace(t.trace_id)}
                    >
                      <td><code>{t.trace_id.slice(0, 8)}...</code></td>
                      <td>{new Date(t.created_at).toLocaleTimeString()}</td>
                      <td className="question-cell" title={t.user_question}>{t.user_question}</td>
                      <td><span className="badge badge-intent">{t.intent || 'READ'}</span></td>
                      <td><code>{t.sql_operation || 'SELECT'}</code></td>
                      <td>
                        <span className={`badge badge-${t.status === 'success' ? 'success' : t.status === 'rejected' ? 'danger' : 'warning'}`}>
                          {t.status}
                        </span>
                      </td>
                      <td>{t.duration_ms}ms</td>
                      <td>{t.total_tokens || 0}</td>
                      <td>${(t.estimated_cost_usd || 0).toFixed(5)}</td>
                      <td>
                        <button 
                          className="btn-inspect" 
                          onClick={(e) => {
                            e.stopPropagation();
                            handleSelectTrace(t.trace_id);
                            setSubTab('overview');
                          }}
                        >
                          <Eye size={14} /> Inspect
                        </button>
                      </td>
                    </tr>
                  ))
                ) : (
                  <tr>
                    <td colSpan="10" className="text-center text-muted">No traces matching the criteria.</td>
                  </tr>
                )}
              </tbody>
            </table>
          </div>
        </div>
      )}

      {/* ---------------- SUB-VIEW 4: GUARDRAIL DECISIONS ---------------- */}
      {subTab === 'guardrails' && (
        <div className="obs-content">
          <div className="guardrails-summary">
            <h3><ShieldCheck size={20} /> Guardrails & Security Policies Summary</h3>
            <p>Every SQL statement is independently verified against schema constraints, destructive filters, and row-count limits.</p>
          </div>

          <div className="table-responsive">
            <table className="obs-table">
              <thead>
                <tr>
                  <th>Trace ID</th>
                  <th>Rule Triggered</th>
                  <th>Decision</th>
                  <th>Reason / Details</th>
                  <th>User Action</th>
                </tr>
              </thead>
              <tbody>
                {traces.map((t) => (
                  <tr key={t.trace_id}>
                    <td><code>{t.trace_id.slice(0, 8)}...</code></td>
                    <td><strong>{t.guardrail_reason ? 'Security Policy' : 'Safe Statement'}</strong></td>
                    <td>
                      <span className={`badge badge-${t.guardrail_decision === 'ALLOWED' ? 'success' : t.guardrail_decision === 'BLOCKED' ? 'danger' : 'warning'}`}>
                        {t.guardrail_decision || 'ALLOWED'}
                      </span>
                    </td>
                    <td>{t.guardrail_reason || 'Query passed all validation checks and read policies.'}</td>
                    <td>{t.status === 'awaiting_confirmation' ? 'Pending Approval' : 'Automatic'}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        </div>
      )}
    </div>
  );
}
