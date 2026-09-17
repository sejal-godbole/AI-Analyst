import React, { useState, useEffect } from 'react';
import axios from 'axios';
import {
  BarChart3,
  Play,
  CheckCircle2,
  XCircle,
  AlertTriangle,
  RefreshCw,
  Search,
  Filter,
  Eye,
  X,
  Copy,
  Check,
  Cpu,
  Code2,
  Zap,
  ShieldCheck,
  Terminal,
  Activity,
  Award,
  Layers,
  HelpCircle,
  ChevronRight,
  Database
} from 'lucide-react';

const API_BASE = import.meta.env.VITE_API_BASE_URL || 'http://localhost:8000';

export default function EvaluationDashboard() {
  const [runs, setRuns] = useState([]);
  const [selectedRun, setSelectedRun] = useState(null);
  const [loading, setLoading] = useState(true);
  const [evaluating, setEvaluating] = useState(false);
  const [evalProgress, setEvalProgress] = useState(null);
  const [searchTerm, setSearchTerm] = useState('');
  const [statusFilter, setStatusFilter] = useState('all');
  const [categoryFilter, setCategoryFilter] = useState('all');
  const [selectedResult, setSelectedResult] = useState(null);
  const [copiedKey, setCopiedKey] = useState(null);
  const [dataset, setDataset] = useState([]);

  const fetchRuns = async () => {
    try {
      const [runsRes, datasetRes] = await Promise.all([
        axios.get(`${API_BASE}/api/evaluation/runs`),
        axios.get(`${API_BASE}/api/evaluation/dataset`)
      ]);
      setRuns(runsRes.data);
      setDataset(datasetRes.data);

      if (runsRes.data.length > 0) {
        // Load latest run detail
        const latestRunId = runsRes.data[0].run_id;
        const detailRes = await axios.get(`${API_BASE}/api/evaluation/runs/${latestRunId}`);
        setSelectedRun(detailRes.data);
      }
      setLoading(false);
    } catch (err) {
      console.error('Failed to load evaluation runs:', err);
      setLoading(false);
    }
  };

  const handleSelectRun = async (runId) => {
    try {
      const res = await axios.get(`${API_BASE}/api/evaluation/runs/${runId}`);
      setSelectedRun(res.data);
    } catch (err) {
      console.error('Failed to load run detail:', err);
    }
  };

  const handleRunEvaluation = async () => {
    setEvaluating(true);
    setEvalProgress('Running Golden Dataset (35 test cases) through LangGraph & LLM Judge...');
    try {
      const res = await axios.post(`${API_BASE}/api/evaluation/run`, {
        name: `Golden Dataset Batch (${new Date().toLocaleTimeString()})`
      });
      setSelectedRun(res.data);
      await fetchRuns();
    } catch (err) {
      console.error('Evaluation run failed:', err);
      alert('Evaluation run encountered an issue. Check backend logs.');
    } finally {
      setEvaluating(false);
      setEvalProgress(null);
    }
  };

  const handleCopy = (text, key) => {
    if (!text) return;
    navigator.clipboard.writeText(text);
    setCopiedKey(key);
    setTimeout(() => setCopiedKey(null), 2000);
  };

  useEffect(() => {
    fetchRuns();
  }, []);

  const results = selectedRun?.results || [];
  const summary = selectedRun?.summary;

  const filteredResults = results.filter((r) => {
    const qMatch = !searchTerm || r.question.toLowerCase().includes(searchTerm.toLowerCase()) || (r.test_case_id && r.test_case_id.toLowerCase().includes(searchTerm.toLowerCase()));
    const statusMatch = statusFilter === 'all' || (statusFilter === 'pass' && r.passed) || (statusFilter === 'fail' && !r.passed) || (statusFilter === 'error' && r.status === 'error');
    const catMatch = categoryFilter === 'all' || (r.test_case_id && r.test_case_id.startsWith(categoryFilter));
    return qMatch && statusMatch && catMatch;
  });

  return (
    <div style={{ padding: '0 2rem 2rem 2rem', flex: 1, overflowY: 'auto' }}>
      {/* Top Banner & Run Controller */}
      <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'flex-start', flexWrap: 'wrap', gap: '1rem', marginBottom: '1.5rem' }}>
        <div>
          <div style={{ display: 'flex', alignItems: 'center', gap: '0.6rem', marginBottom: '0.35rem' }}>
            <span className="status-badge" style={{ backgroundColor: 'rgba(139, 92, 246, 0.15)', color: 'var(--accent-color)', borderColor: 'rgba(139, 92, 246, 0.4)', fontWeight: 700, fontSize: '0.72rem' }}>
              <Award size={12} style={{ verticalAlign: 'middle', marginRight: '0.25rem' }} />
              LLM EVALUATION FRAMEWORK
            </span>
            <span style={{ fontSize: '0.75rem', color: 'var(--text-secondary)' }}>
              Golden Dataset: <strong>{dataset.length} Test Cases</strong>
            </span>
          </div>
          <h2 style={{ fontSize: '1.35rem', fontWeight: 800, margin: 0 }}>Model & Pipeline Quality Evaluation</h2>
          <p style={{ color: 'var(--text-secondary)', fontSize: '0.82rem', marginTop: '0.25rem' }}>
            Multi-stage ground truth evaluation: Deterministic checks for <strong>Intent</strong> & <strong>SQL</strong>, plus <strong>LLM-as-a-Judge</strong> for Final Answer quality.
          </p>
        </div>

        <div style={{ display: 'flex', alignItems: 'center', gap: '0.75rem', flexWrap: 'wrap' }}>
          {runs.length > 0 && (
            <div style={{ display: 'flex', alignItems: 'center', gap: '0.5rem' }}>
              <span style={{ fontSize: '0.75rem', color: 'var(--text-secondary)' }}>Select Run:</span>
              <select
                value={selectedRun?.summary?.run_id || ''}
                onChange={(e) => handleSelectRun(e.target.value)}
                style={{
                  background: 'var(--bg-panel)',
                  color: 'var(--text-primary)',
                  border: '1px solid var(--border-color)',
                  borderRadius: '4px',
                  padding: '0.4rem 0.6rem',
                  fontSize: '0.78rem',
                  fontWeight: 600
                }}
              >
                {runs.map((rn) => (
                  <option key={rn.run_id} value={rn.run_id}>
                    {new Date(rn.created_at).toLocaleTimeString()} - Score: {rn.overall_score}/10 ({rn.passed_cases}/{rn.total_cases} PASS)
                  </option>
                ))}
              </select>
            </div>
          )}

          <button
            className="neo-button primary"
            onClick={handleRunEvaluation}
            disabled={evaluating}
            style={{ padding: '0.45rem 1rem', height: '2.4rem', fontWeight: 700, gap: '0.4rem' }}
          >
            {evaluating ? <RefreshCw size={14} className="spinning" /> : <Play size={14} />}
            <span>{evaluating ? 'Running Evaluation...' : 'Run Evaluation'}</span>
          </button>
        </div>
      </div>

      {/* Progress Notification Banner */}
      {evalProgress && (
        <div style={{ background: 'rgba(139, 92, 246, 0.1)', border: '1px solid rgba(139, 92, 246, 0.3)', padding: '0.75rem 1rem', borderRadius: '6px', marginBottom: '1.25rem', display: 'flex', alignItems: 'center', gap: '0.6rem', fontSize: '0.82rem', color: 'var(--accent-color)' }}>
          <RefreshCw size={14} className="spinning" />
          <span>{evalProgress}</span>
        </div>
      )}

      {/* Overview KPI Cards */}
      {summary ? (
        <div style={{ display: 'grid', gridTemplateColumns: 'repeat(auto-fit, minmax(200px, 1fr))', gap: '1rem', marginBottom: '1.5rem' }}>
          {/* Card 1: Total & Pass Rate */}
          <div className="neo-box" style={{ padding: '1rem' }}>
            <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: '0.35rem' }}>
              <span style={{ fontSize: '0.72rem', fontWeight: 700, color: 'var(--text-secondary)', textTransform: 'uppercase' }}>Test Cases & Pass Rate</span>
              <Award size={16} style={{ color: 'var(--accent-color)' }} />
            </div>
            <div style={{ fontSize: '1.6rem', fontWeight: 800, color: 'var(--text-primary)' }}>
              {summary.passed_cases} <span style={{ fontSize: '1rem', color: 'var(--text-secondary)', fontWeight: 500 }}>/ {summary.total_cases}</span>
            </div>
            <div style={{ display: 'flex', alignItems: 'center', gap: '0.4rem', marginTop: '0.25rem', fontSize: '0.75rem' }}>
              <span className={`status-badge`} style={{ backgroundColor: summary.failed_cases === 0 ? 'var(--success-bg)' : 'var(--danger-bg)', color: summary.failed_cases === 0 ? 'var(--success-text)' : 'var(--danger-text)', border: `1px solid ${summary.failed_cases === 0 ? 'var(--success-border)' : 'var(--danger-border)'}`, padding: '0.1rem 0.35rem', fontSize: '0.7rem' }}>
                {summary.total_cases > 0 ? `${Math.round((summary.passed_cases / summary.total_cases) * 100)}% PASS` : '0%'}
              </span>
              <span style={{ color: 'var(--text-muted)' }}>Threshold: &ge; 8.0/10</span>
            </div>
          </div>

          {/* Card 2: Intent Accuracy */}
          <div className="neo-box" style={{ padding: '1rem' }}>
            <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: '0.35rem' }}>
              <span style={{ fontSize: '0.72rem', fontWeight: 700, color: 'var(--text-secondary)', textTransform: 'uppercase' }}>LLM #1 Intent Accuracy</span>
              <Cpu size={16} style={{ color: '#3b82f6' }} />
            </div>
            <div style={{ fontSize: '1.6rem', fontWeight: 800, color: '#3b82f6' }}>
              {summary.avg_intent_score > 1.0 ? round(summary.avg_intent_score / 10, 2) : summary.avg_intent_score} <span style={{ fontSize: '0.9rem', color: 'var(--text-secondary)', fontWeight: 500 }}>/ 1</span>
            </div>
            <div style={{ fontSize: '0.72rem', color: 'var(--text-secondary)', marginTop: '0.25rem' }}>
              Deterministic ground truth (Binary 0/1, 20% weight)
            </div>
          </div>

          {/* Card 3: SQL Quality */}
          <div className="neo-box" style={{ padding: '1rem' }}>
            <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: '0.35rem' }}>
              <span style={{ fontSize: '0.72rem', fontWeight: 700, color: 'var(--text-secondary)', textTransform: 'uppercase' }}>LLM #2 SQL Quality</span>
              <Code2 size={16} style={{ color: '#10b981' }} />
            </div>
            <div style={{ fontSize: '1.6rem', fontWeight: 800, color: '#10b981' }}>
              {summary.avg_sql_score > 1.0 ? round(summary.avg_sql_score / 10, 2) : summary.avg_sql_score} <span style={{ fontSize: '0.9rem', color: 'var(--text-secondary)', fontWeight: 500 }}>/ 1</span>
            </div>
            <div style={{ fontSize: '0.72rem', color: 'var(--text-secondary)', marginTop: '0.25rem' }}>
              AST, Schema & Safety (Binary 0/1 checks, 40% weight)
            </div>
          </div>

          {/* Card 4: Final Answer (Judge) */}
          <div className="neo-box" style={{ padding: '1rem' }}>
            <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: '0.35rem' }}>
              <span style={{ fontSize: '0.72rem', fontWeight: 700, color: 'var(--text-secondary)', textTransform: 'uppercase' }}>LLM #3 Answer (Judge)</span>
              <Zap size={16} style={{ color: '#f59e0b' }} />
            </div>
            <div style={{ fontSize: '1.6rem', fontWeight: 800, color: '#f59e0b' }}>
              {summary.avg_final_score} <span style={{ fontSize: '0.9rem', color: 'var(--text-secondary)', fontWeight: 500 }}>/ 10</span>
            </div>
            <div style={{ fontSize: '0.72rem', color: 'var(--text-secondary)', marginTop: '0.25rem' }}>
              Groundedness & Clarity (0-10 Scale, 40% weight)
            </div>
          </div>

          {/* Card 5: Overall Quality Score */}
          <div className="neo-box" style={{ padding: '1rem', border: '2px solid var(--accent-color)' }}>
            <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: '0.35rem' }}>
              <span style={{ fontSize: '0.72rem', fontWeight: 800, color: 'var(--accent-color)', textTransform: 'uppercase' }}>Overall Quality Score</span>
              <ShieldCheck size={16} style={{ color: 'var(--accent-color)' }} />
            </div>
            <div style={{ fontSize: '1.6rem', fontWeight: 900, color: 'var(--text-primary)' }}>
              {summary.overall_score} <span style={{ fontSize: '0.9rem', color: 'var(--text-secondary)', fontWeight: 500 }}>/ 10</span>
            </div>
            <div style={{ fontSize: '0.72rem', color: 'var(--accent-color)', marginTop: '0.25rem', fontWeight: 600 }}>
              Composite Weighted Score
            </div>
          </div>
        </div>
      ) : (
        <div style={{ border: '2px dashed var(--border-color)', borderRadius: '8px', padding: '2.5rem', textAlign: 'center', marginBottom: '1.5rem' }}>
          <Award size={32} style={{ color: 'var(--accent-color)', margin: '0 auto 0.75rem auto', display: 'block' }} />
          <h3 style={{ fontSize: '1.1rem', fontWeight: 700, marginBottom: '0.35rem' }}>No Evaluation Runs Yet</h3>
          <p style={{ fontSize: '0.82rem', color: 'var(--text-secondary)', maxWidth: '480px', margin: '0 auto 1.25rem auto' }}>
            Click the "Run Evaluation" button above to evaluate all 35+ test cases from the Golden Dataset across Intent, SQL, and Answer generation.
          </p>
          <button className="neo-button primary" onClick={handleRunEvaluation} disabled={evaluating}>
            <Play size={14} /> Run Evaluation Now
          </button>
        </div>
      )}

      {/* Toolbar & Filter */}
      {results.length > 0 && (
        <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', gap: '1rem', flexWrap: 'wrap', marginBottom: '1rem' }}>
          <div style={{ display: 'flex', alignItems: 'center', gap: '0.5rem', flex: 1, minWidth: '240px' }}>
            <div style={{ position: 'relative', width: '100%', maxWidth: '360px' }}>
              <Search size={14} style={{ position: 'absolute', left: '0.6rem', top: '50%', transform: 'translateY(-50%)', color: 'var(--text-secondary)' }} />
              <input
                type="text"
                placeholder="Search question or test ID..."
                value={searchTerm}
                onChange={(e) => setSearchTerm(e.target.value)}
                style={{ width: '100%', paddingLeft: '2rem', paddingRight: '0.75rem', height: '2.2rem', fontSize: '0.78rem', background: 'var(--bg-panel)', border: '1px solid var(--border-color)', borderRadius: '4px', color: 'var(--text-primary)' }}
              />
            </div>
          </div>

          <div style={{ display: 'flex', alignItems: 'center', gap: '0.5rem' }}>
            <Filter size={14} style={{ color: 'var(--text-secondary)' }} />
            <select
              value={statusFilter}
              onChange={(e) => setStatusFilter(e.target.value)}
              style={{ background: 'var(--bg-panel)', color: 'var(--text-primary)', border: '1px solid var(--border-color)', borderRadius: '4px', padding: '0.3rem 0.6rem', fontSize: '0.75rem' }}
            >
              <option value="all">All Statuses ({results.length})</option>
              <option value="pass">Passed (&ge; 8.0)</option>
              <option value="fail">Failed (&lt; 8.0)</option>
              <option value="error">Execution Errors</option>
            </select>
          </div>
        </div>
      )}

      {/* Test Case Results Table */}
      {results.length > 0 && (
        <div className="neo-box" style={{ overflow: 'hidden', padding: 0 }}>
          <div style={{ overflowX: 'auto' }}>
            <table className="obs-table" style={{ width: '100%', borderCollapse: 'collapse', fontSize: '0.78rem' }}>
              <thead>
                <tr>
                  <th style={{ width: '85px' }}>Test ID</th>
                  <th>User Question</th>
                  <th>Expected Intent</th>
                  <th>Actual Intent</th>
                  <th>Intent (20%)</th>
                  <th>SQL Score (40%)</th>
                  <th>Answer Score (40%)</th>
                  <th>Overall</th>
                  <th>Status</th>
                  <th>Action</th>
                </tr>
              </thead>
              <tbody>
                {filteredResults.map((r) => {
                  const intentPass = r.intent_eval.score === 1.0 || r.intent_eval.score === 10;
                  const sqlPass = r.sql_eval.sql_quality_score >= 0.8;
                  const ansColor = r.final_answer_eval.final_answer_score >= 8 ? '#10b981' : r.final_answer_eval.final_answer_score >= 5 ? '#f59e0b' : '#ef4444';
                  
                  return (
                    <tr
                      key={r.result_id}
                      onClick={() => setSelectedResult(r)}
                      style={{ cursor: 'pointer', transition: 'background 0.15s' }}
                      className={selectedResult?.result_id === r.result_id ? 'selected-row' : ''}
                    >
                      <td><code style={{ fontWeight: 700 }}>{r.test_case_id || 'LIVE'}</code></td>
                      <td style={{ maxWidth: '280px', fontWeight: 600 }}>{r.question}</td>
                      <td>
                        <span className="badge badge-intent">{r.intent_eval.expected_intent || 'N/A'}</span>
                      </td>
                      <td>
                        <span className="badge badge-intent" style={{ borderColor: r.intent_eval.expected_intent === r.intent_eval.actual_intent ? 'var(--success-border)' : 'var(--danger-border)' }}>
                          {r.intent_eval.actual_intent}
                        </span>
                      </td>
                      <td>
                        <strong style={{ color: intentPass ? '#10b981' : '#ef4444' }}>
                          {r.intent_eval.score !== null ? (intentPass ? '1 / 1' : '0 / 1') : 'N/A'}
                        </strong>
                      </td>
                      <td>
                        <strong style={{ color: sqlPass ? '#10b981' : '#ef4444' }}>
                          {r.sql_eval.sql_quality_score > 1.0 ? `${Math.round(r.sql_eval.sql_quality_score / 10 * 5)}/5` : `${Math.round(r.sql_eval.sql_quality_score * 5)}/5 (${r.sql_eval.sql_quality_score > 1.0 ? r.sql_eval.sql_quality_score / 10 : r.sql_eval.sql_quality_score})`}
                        </strong>
                      </td>
                      <td>
                        <strong style={{ color: ansColor }}>{r.final_answer_eval.final_answer_score}/10</strong>
                      </td>
                      <td>
                        <span style={{ fontSize: '0.85rem', fontWeight: 800, color: r.passed ? 'var(--success-text)' : 'var(--danger-text)' }}>
                          {r.overall_score}/10
                        </span>
                      </td>
                      <td>
                        <span className={`status-badge`} style={{ backgroundColor: r.passed ? 'var(--success-bg)' : 'var(--danger-bg)', color: r.passed ? 'var(--success-text)' : 'var(--danger-text)', border: `1px solid ${r.passed ? 'var(--success-border)' : 'var(--danger-border)'}`, padding: '0.15rem 0.45rem', fontSize: '0.68rem', fontWeight: 700 }}>
                          {r.passed ? 'PASS' : 'FAIL'}
                        </span>
                      </td>
                      <td>
                        <button
                          className="neo-button secondary"
                          style={{ padding: '0.2rem 0.5rem', fontSize: '0.7rem' }}
                          onClick={(e) => {
                            e.stopPropagation();
                            setSelectedResult(r);
                          }}
                        >
                          <Eye size={12} /> Inspect
                        </button>
                      </td>
                    </tr>
                  );
                })}
              </tbody>
            </table>
          </div>
        </div>
      )}

      {/* Detailed Result Inspection Modal / Drawer */}
      {selectedResult && (
        <div className="obs-dialog-backdrop" onClick={() => setSelectedResult(null)}>
          <div className="obs-dialog-container" onClick={(e) => e.stopPropagation()} style={{ maxWidth: '900px', maxHeight: '90vh', overflowY: 'auto' }}>
            <div className="obs-header">
              <div className="obs-title-group">
                <div style={{ display: 'flex', alignItems: 'center', gap: '0.6rem', marginBottom: '0.25rem' }}>
                  <span className="status-badge" style={{ backgroundColor: selectedResult.passed ? 'var(--success-bg)' : 'var(--danger-bg)', color: selectedResult.passed ? 'var(--success-text)' : 'var(--danger-text)', border: `1px solid ${selectedResult.passed ? 'var(--success-border)' : 'var(--danger-border)'}`, fontWeight: 800 }}>
                    {selectedResult.test_case_id || 'LIVE QUERY'} — {selectedResult.passed ? 'PASS' : 'FAIL'} ({selectedResult.overall_score}/10)
                  </span>
                  {selectedResult.trace_id && (
                    <span className="obs-active-trace-tag">
                      Trace: <code>{selectedResult.trace_id.slice(0, 10)}...</code>
                    </span>
                  )}
                </div>
                <h3 style={{ margin: '0.25rem 0', fontSize: '1.15rem', fontWeight: 800 }}>"{selectedResult.question}"</h3>
              </div>
              <button className="btn-close-modal" onClick={() => setSelectedResult(null)}>
                <X size={18} />
              </button>
            </div>

            <div style={{ padding: '1.5rem', display: 'flex', flexDirection: 'column', gap: '1.25rem' }}>
              {/* STAGE 1: INTENT CLASSIFICATION */}
              <div className="neo-box" style={{ padding: '1.25rem', borderColor: (selectedResult.intent_eval.score === 1.0 || selectedResult.intent_eval.score === 10) ? 'rgba(16, 185, 129, 0.3)' : 'rgba(239, 68, 68, 0.3)' }}>
                <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: '0.75rem', borderBottom: '1px solid var(--border-color)', paddingBottom: '0.5rem' }}>
                  <div style={{ display: 'flex', alignItems: 'center', gap: '0.5rem' }}>
                    <Cpu size={18} style={{ color: '#3b82f6' }} />
                    <h4 style={{ margin: 0, fontSize: '0.95rem', fontWeight: 700 }}>Stage 1: Intent Classification (Binary 0/1)</h4>
                  </div>
                  <span style={{ fontSize: '0.9rem', fontWeight: 800, color: (selectedResult.intent_eval.score === 1.0 || selectedResult.intent_eval.score === 10) ? 'var(--success-text)' : 'var(--danger-text)' }}>
                    Score: {selectedResult.intent_eval.score !== null ? `${selectedResult.intent_eval.score > 1.0 ? 1 : selectedResult.intent_eval.score} / 1` : 'N/A'}
                  </span>
                </div>

                <div style={{ display: 'grid', gridTemplateColumns: 'repeat(auto-fit, minmax(180px, 1fr))', gap: '0.75rem', fontSize: '0.78rem', marginBottom: '0.5rem' }}>
                  <div>
                    <span style={{ color: 'var(--text-secondary)' }}>Expected Intent: </span>
                    <span className="badge badge-intent" style={{ fontWeight: 700 }}>{selectedResult.intent_eval.expected_intent || 'Not defined (Live query)'}</span>
                  </div>
                  <div>
                    <span style={{ color: 'var(--text-secondary)' }}>Actual Intent: </span>
                    <span className="badge badge-intent" style={{ fontWeight: 700 }}>{selectedResult.intent_eval.actual_intent}</span>
                  </div>
                  <div>
                    <span style={{ color: 'var(--text-secondary)' }}>Format Valid: </span>
                    <strong>{selectedResult.intent_eval.format_compliance > 1.0 ? (selectedResult.intent_eval.format_compliance === 10 ? '1 / 1 (Valid)' : '0 / 1') : (selectedResult.intent_eval.format_compliance === 1 ? '1 / 1 (Valid)' : '0 / 1')}</strong>
                  </div>
                  <div>
                    <span style={{ color: 'var(--text-secondary)' }}>Instruction Token: </span>
                    <strong>{selectedResult.intent_eval.instruction_compliance > 1.0 ? (selectedResult.intent_eval.instruction_compliance === 10 ? '1 / 1 (Valid)' : '0 / 1') : (selectedResult.intent_eval.instruction_compliance === 1 ? '1 / 1 (Valid)' : '0 / 1')}</strong>
                  </div>
                </div>

                {selectedResult.intent_eval.notes && (
                  <p style={{ fontSize: '0.75rem', color: 'var(--text-secondary)', margin: 0, fontStyle: 'italic' }}>
                    Note: {selectedResult.intent_eval.notes}
                  </p>
                )}
              </div>

              {/* STAGE 2: SQL GENERATION */}
              <div className="neo-box" style={{ padding: '1.25rem', borderColor: 'rgba(16, 185, 129, 0.3)' }}>
                <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: '0.75rem', borderBottom: '1px solid var(--border-color)', paddingBottom: '0.5rem' }}>
                  <div style={{ display: 'flex', alignItems: 'center', gap: '0.5rem' }}>
                    <Code2 size={18} style={{ color: '#10b981' }} />
                    <h4 style={{ margin: 0, fontSize: '0.95rem', fontWeight: 700 }}>Stage 2: SQL Generation Quality (Binary 0/1 Checks)</h4>
                  </div>
                  <span style={{ fontSize: '0.9rem', fontWeight: 800, color: 'var(--success-text)' }}>
                    Passed: {selectedResult.sql_eval.sql_quality_score > 1.0 ? `${Math.round(selectedResult.sql_eval.sql_quality_score / 10 * 5)}/5 Checks` : `${Math.round(selectedResult.sql_eval.sql_quality_score * 5)}/5 Checks`}
                  </span>
                </div>

                {/* Sub-metric chips */}
                <div style={{ display: 'grid', gridTemplateColumns: 'repeat(auto-fit, minmax(130px, 1fr))', gap: '0.5rem', marginBottom: '0.75rem' }}>
                  <div style={{ background: 'var(--bg-panel)', padding: '0.4rem 0.6rem', borderRadius: '4px', border: '1px solid var(--border-color)' }}>
                    <div style={{ fontSize: '0.68rem', color: 'var(--text-secondary)' }}>Syntax (sqlglot AST)</div>
                    <strong style={{ fontSize: '0.85rem' }}>{selectedResult.sql_eval.syntax_correctness > 1.0 ? (selectedResult.sql_eval.syntax_correctness === 10 ? '1 / 1' : '0 / 1') : `${selectedResult.sql_eval.syntax_correctness} / 1`}</strong>
                  </div>
                  <div style={{ background: 'var(--bg-panel)', padding: '0.4rem 0.6rem', borderRadius: '4px', border: '1px solid var(--border-color)' }}>
                    <div style={{ fontSize: '0.68rem', color: 'var(--text-secondary)' }}>Schema Validity</div>
                    <strong style={{ fontSize: '0.85rem' }}>{selectedResult.sql_eval.schema_correctness > 1.0 ? (selectedResult.sql_eval.schema_correctness === 10 ? '1 / 1' : '0 / 1') : `${selectedResult.sql_eval.schema_correctness} / 1`}</strong>
                  </div>
                  <div style={{ background: 'var(--bg-panel)', padding: '0.4rem 0.6rem', borderRadius: '4px', border: '1px solid var(--border-color)' }}>
                    <div style={{ fontSize: '0.68rem', color: 'var(--text-secondary)' }}>Safety & Policy</div>
                    <strong style={{ fontSize: '0.85rem' }}>{selectedResult.sql_eval.safety_compliance > 1.0 ? (selectedResult.sql_eval.safety_compliance === 10 ? '1 / 1' : '0 / 1') : `${selectedResult.sql_eval.safety_compliance} / 1`}</strong>
                  </div>
                  <div style={{ background: 'var(--bg-panel)', padding: '0.4rem 0.6rem', borderRadius: '4px', border: '1px solid var(--border-color)' }}>
                    <div style={{ fontSize: '0.68rem', color: 'var(--text-secondary)' }}>Semantic Match</div>
                    <strong style={{ fontSize: '0.85rem' }}>{selectedResult.sql_eval.semantic_correctness > 1.0 ? (selectedResult.sql_eval.semantic_correctness === 10 ? '1 / 1' : '0 / 1') : `${selectedResult.sql_eval.semantic_correctness} / 1`}</strong>
                  </div>
                  <div style={{ background: 'var(--bg-panel)', padding: '0.4rem 0.6rem', borderRadius: '4px', border: '1px solid var(--border-color)' }}>
                    <div style={{ fontSize: '0.68rem', color: 'var(--text-secondary)' }}>Relevance</div>
                    <strong style={{ fontSize: '0.85rem' }}>{selectedResult.sql_eval.relevance > 1.0 ? (selectedResult.sql_eval.relevance === 10 ? '1 / 1' : '0 / 1') : `${selectedResult.sql_eval.relevance} / 1`}</strong>
                  </div>
                </div>

                {/* Generated SQL code block */}
                {selectedResult.sql_eval.generated_sql ? (
                  <div>
                    <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: '0.25rem' }}>
                      <span style={{ fontSize: '0.72rem', fontWeight: 700, color: 'var(--text-secondary)' }}>GENERATED SQL:</span>
                      <button
                        className="btn-obs-action"
                        style={{ padding: '0.15rem 0.45rem', fontSize: '0.68rem' }}
                        onClick={() => handleCopy(selectedResult.sql_eval.generated_sql, 'sql-detail')}
                      >
                        {copiedKey === 'sql-detail' ? <Check size={10} /> : <Copy size={10} />}
                        <span>{copiedKey === 'sql-detail' ? 'COPIED' : 'COPY SQL'}</span>
                      </button>
                    </div>
                    <pre className="raw-code-box" style={{ maxHeight: '120px' }}>{selectedResult.sql_eval.generated_sql}</pre>
                  </div>
                ) : (
                  <p style={{ fontSize: '0.75rem', color: 'var(--text-muted)', fontStyle: 'italic', margin: 0 }}>No executable SQL generated (as expected for this intent).</p>
                )}
              </div>

              {/* STAGE 3: FINAL ANSWER (LLM-AS-A-JUDGE) */}
              <div className="neo-box" style={{ padding: '1.25rem', borderColor: 'rgba(245, 158, 11, 0.3)' }}>
                <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: '0.75rem', borderBottom: '1px solid var(--border-color)', paddingBottom: '0.5rem' }}>
                  <div style={{ display: 'flex', alignItems: 'center', gap: '0.5rem' }}>
                    <Zap size={18} style={{ color: '#f59e0b' }} />
                    <h4 style={{ margin: 0, fontSize: '0.95rem', fontWeight: 700 }}>Stage 3: Final Answer Quality (LLM-as-a-Judge)</h4>
                  </div>
                  <span style={{ fontSize: '0.9rem', fontWeight: 800, color: '#f59e0b' }}>
                    Judge Score: {selectedResult.final_answer_eval.final_answer_score}/10
                  </span>
                </div>

                {/* 5 Judge Criteria Chips */}
                <div style={{ display: 'grid', gridTemplateColumns: 'repeat(auto-fit, minmax(130px, 1fr))', gap: '0.5rem', marginBottom: '0.75rem' }}>
                  <div style={{ background: 'var(--bg-panel)', padding: '0.4rem 0.6rem', borderRadius: '4px', border: '1px solid var(--border-color)' }}>
                    <div style={{ fontSize: '0.68rem', color: 'var(--text-secondary)' }}>Relevance</div>
                    <strong style={{ fontSize: '0.85rem' }}>{selectedResult.final_answer_eval.relevance}/10</strong>
                  </div>
                  <div style={{ background: 'var(--bg-panel)', padding: '0.4rem 0.6rem', borderRadius: '4px', border: '1px solid var(--border-color)' }}>
                    <div style={{ fontSize: '0.68rem', color: 'var(--text-secondary)' }}>Correctness</div>
                    <strong style={{ fontSize: '0.85rem' }}>{selectedResult.final_answer_eval.correctness}/10</strong>
                  </div>
                  <div style={{ background: 'var(--bg-panel)', padding: '0.4rem 0.6rem', borderRadius: '4px', border: '1px solid var(--border-color)' }}>
                    <div style={{ fontSize: '0.68rem', color: 'var(--text-secondary)' }}>Groundedness</div>
                    <strong style={{ fontSize: '0.85rem', color: '#10b981' }}>{selectedResult.final_answer_eval.groundedness}/10</strong>
                  </div>
                  <div style={{ background: 'var(--bg-panel)', padding: '0.4rem 0.6rem', borderRadius: '4px', border: '1px solid var(--border-color)' }}>
                    <div style={{ fontSize: '0.68rem', color: 'var(--text-secondary)' }}>Completeness</div>
                    <strong style={{ fontSize: '0.85rem' }}>{selectedResult.final_answer_eval.completeness}/10</strong>
                  </div>
                  <div style={{ background: 'var(--bg-panel)', padding: '0.4rem 0.6rem', borderRadius: '4px', border: '1px solid var(--border-color)' }}>
                    <div style={{ fontSize: '0.68rem', color: 'var(--text-secondary)' }}>Clarity</div>
                    <strong style={{ fontSize: '0.85rem' }}>{selectedResult.final_answer_eval.clarity}/10</strong>
                  </div>
                </div>

                {/* Judge Reasoning */}
                <div style={{ background: 'rgba(245, 158, 11, 0.06)', border: '1px solid rgba(245, 158, 11, 0.25)', padding: '0.75rem', borderRadius: '4px', marginBottom: '0.75rem' }}>
                  <div style={{ fontSize: '0.72rem', fontWeight: 700, color: '#f59e0b', marginBottom: '0.2rem' }}>
                    JUDGE REASONING ({selectedResult.final_answer_eval.judge_model || 'gemini-2.5-flash'}):
                  </div>
                  <p style={{ fontSize: '0.8rem', margin: 0, lineHeight: 1.4 }}>
                    "{selectedResult.final_answer_eval.reason}"
                  </p>
                </div>

                {/* Final Answer output */}
                <div>
                  <span style={{ fontSize: '0.72rem', fontWeight: 700, color: 'var(--text-secondary)' }}>GENERATED FINAL ANSWER:</span>
                  <pre className="raw-code-box" style={{ maxHeight: '100px', borderColor: 'rgba(245, 158, 11, 0.3)' }}>
                    {selectedResult.final_answer_eval.generated_answer || 'No answer output recorded.'}
                  </pre>
                </div>
              </div>
            </div>
          </div>
        </div>
      )}
    </div>
  );
}
