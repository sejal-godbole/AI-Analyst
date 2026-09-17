import React, { useState, useEffect, useMemo, useCallback } from 'react';
import {
  ReactFlow,
  Background,
  Controls,
  MiniMap,
  useNodesState,
  useEdgesState,
  MarkerType,
  Position,
  Handle
} from '@xyflow/react';
import '@xyflow/react/dist/style.css';
import axios from 'axios';
import {
  Play,
  Layers,
  Database,
  FileCode2,
  Cpu,
  Code2,
  CheckCircle2,
  ShieldCheck,
  AlertTriangle,
  Server,
  Activity,
  Zap,
  RefreshCw,
  XCircle,
  Award,
  Clock,
  Check,
  X,
  ChevronRight,
  ChevronDown,
  Terminal,
  Lock,
  Copy,
  Info,
  ExternalLink
} from 'lucide-react';

const API_BASE = import.meta.env.VITE_API_BASE_URL || 'http://localhost:8000';

const ICON_MAP = {
  Play,
  Layers,
  Database,
  FileCode2,
  Cpu,
  Code2,
  CheckCircle2,
  ShieldCheck,
  AlertTriangle,
  Server,
  Activity,
  Zap,
  RefreshCw,
  XCircle,
  Award
};

// Precise LangGraph Topological Positions (Center Spine, Left Error/Approval column, Right Retry column)
const NODE_POSITIONS = {
  __start__: { x: 0, y: 0 },
  receive_question: { x: 0, y: 75 },
  inspect_schema: { x: 0, y: 175 },
  build_schema_context: { x: 0, y: 275 },
  classify_intent: { x: 0, y: 375 },
  generate_sql: { x: 90, y: 485 },
  validate_sql: { x: 90, y: 590 },
  safety_check: { x: 0, y: 695 },
  human_confirmation: { x: -220, y: 805 },
  execute_query: { x: 90, y: 805 },
  check_result: { x: 90, y: 910 },
  final_answer: { x: 90, y: 1015 },
  error_terminal: { x: -260, y: 1015 },
  increment_retry: { x: 410, y: 910 },
  __end__: { x: 0, y: 1125 }
};

// Fallback LangGraph node definitions
const DEFAULT_GRAPH_NODES = [
  { id: '__start__', label: 'START', desc: 'Workflow entry point', type: 'start', icon: 'Play' },
  { id: 'receive_question', label: 'Receive Question', desc: 'Initialize context & query trace', type: 'node', icon: 'Layers' },
  { id: 'inspect_schema', label: 'Inspect Schema', desc: 'Fetch DB structure via MCP', type: 'node', icon: 'Database' },
  { id: 'build_schema_context', label: 'Schema Context', desc: 'Format active schema & relations', type: 'node', icon: 'FileCode2' },
  { id: 'classify_intent', label: 'Classify Intent', desc: 'READ / WRITE / DESTRUCTIVE', type: 'node', icon: 'Cpu' },
  { id: 'generate_sql', label: 'Generate SQL', desc: 'Gemini LLM query generation', type: 'node', icon: 'Code2' },
  { id: 'validate_sql', label: 'Validate SQL', desc: 'AST & semantic security check', type: 'node', icon: 'CheckCircle2' },
  { id: 'safety_check', label: 'Guardrails Check', desc: 'Security & policy enforcement', type: 'node', icon: 'ShieldCheck' },
  { id: 'human_confirmation', label: 'Human Confirm', desc: 'HITL interrupt for sensitive operations', type: 'node', icon: 'AlertTriangle' },
  { id: 'execute_query', label: 'MCP Execute', desc: 'Controlled isolated query execution', type: 'node', icon: 'Server' },
  { id: 'check_result', label: 'Check Result', desc: 'Validate DB return dataset', type: 'node', icon: 'Activity' },
  { id: 'final_answer', label: 'Final Answer', desc: 'Synthesize natural language response', type: 'node', icon: 'Zap' },
  { id: 'increment_retry', label: 'Increment Retry', desc: 'Track attempt count & error history', type: 'retry', icon: 'RefreshCw' },
  { id: 'error_terminal', label: 'Error Terminal', desc: 'Error handling & safe failure exit', type: 'error', icon: 'XCircle' },
  { id: '__end__', label: 'END', desc: 'Workflow termination', type: 'end', icon: 'Award' }
];

// Exact LangGraph edge routing & handle specifications to avoid overlapping lines
const DEFAULT_GRAPH_EDGES = [
  { id: '__start__->receive_question', source: '__start__', target: 'receive_question', label: '', edge_type: 'default', sourceHandle: 'bottom', targetHandle: 'top' },
  { id: 'receive_question->inspect_schema', source: 'receive_question', target: 'inspect_schema', label: '', edge_type: 'default', sourceHandle: 'bottom', targetHandle: 'top' },
  { id: 'inspect_schema->build_schema_context', source: 'inspect_schema', target: 'build_schema_context', label: '', edge_type: 'default', sourceHandle: 'bottom', targetHandle: 'top' },
  { id: 'build_schema_context->classify_intent', source: 'build_schema_context', target: 'classify_intent', label: '', edge_type: 'default', sourceHandle: 'bottom', targetHandle: 'top' },
  { id: 'classify_intent->generate_sql', source: 'classify_intent', target: 'generate_sql', label: 'safe intent (read/write)', edge_type: 'conditional', sourceHandle: 'bottom', targetHandle: 'top' },
  { id: 'classify_intent->error_terminal', source: 'classify_intent', target: 'error_terminal', label: 'DESTRUCTIVE / UNKNOWN', edge_type: 'error', sourceHandle: 'source-left', targetHandle: 'left' },
  { id: 'generate_sql->validate_sql', source: 'generate_sql', target: 'validate_sql', label: '', edge_type: 'default', sourceHandle: 'bottom', targetHandle: 'top' },
  { id: 'validate_sql->safety_check', source: 'validate_sql', target: 'safety_check', label: 'valid', edge_type: 'conditional', sourceHandle: 'bottom', targetHandle: 'top' },
  { id: 'validate_sql->increment_retry', source: 'validate_sql', target: 'increment_retry', label: 'invalid (retry)', edge_type: 'retry', sourceHandle: 'right', targetHandle: 'top' },
  { id: 'validate_sql->error_terminal', source: 'validate_sql', target: 'error_terminal', label: 'exhausted', edge_type: 'error', sourceHandle: 'source-left', targetHandle: 'left' },
  { id: 'safety_check->execute_query', source: 'safety_check', target: 'execute_query', label: 'safe', edge_type: 'conditional', sourceHandle: 'bottom', targetHandle: 'top' },
  { id: 'safety_check->human_confirmation', source: 'safety_check', target: 'human_confirmation', label: 'needs confirmation', edge_type: 'conditional', sourceHandle: 'source-left', targetHandle: 'top' },
  { id: 'safety_check->error_terminal', source: 'safety_check', target: 'error_terminal', label: 'unsafe', edge_type: 'error', sourceHandle: 'source-left', targetHandle: 'left' },
  { id: 'human_confirmation->execute_query', source: 'human_confirmation', target: 'execute_query', label: 'approved', edge_type: 'conditional', sourceHandle: 'right', targetHandle: 'left' },
  { id: 'human_confirmation->error_terminal', source: 'human_confirmation', target: 'error_terminal', label: 'rejected', edge_type: 'error', sourceHandle: 'bottom', targetHandle: 'top' },
  { id: 'execute_query->check_result', source: 'execute_query', target: 'check_result', label: 'succeeded', edge_type: 'conditional', sourceHandle: 'bottom', targetHandle: 'top' },
  { id: 'execute_query->increment_retry', source: 'execute_query', target: 'increment_retry', label: 'error (retry)', edge_type: 'retry', sourceHandle: 'right', targetHandle: 'left' },
  { id: 'execute_query->error_terminal', source: 'execute_query', target: 'error_terminal', label: 'exhausted', edge_type: 'error', sourceHandle: 'source-left', targetHandle: 'right' },
  { id: 'check_result->final_answer', source: 'check_result', target: 'final_answer', label: 'ok', edge_type: 'conditional', sourceHandle: 'bottom', targetHandle: 'top' },
  { id: 'check_result->increment_retry', source: 'check_result', target: 'increment_retry', label: 'suspicious (retry)', edge_type: 'retry', sourceHandle: 'right', targetHandle: 'left' },
  { id: 'check_result->error_terminal', source: 'check_result', target: 'error_terminal', label: 'exhausted', edge_type: 'error', sourceHandle: 'source-left', targetHandle: 'right' },
  { id: 'increment_retry->generate_sql', source: 'increment_retry', target: 'generate_sql', label: 'retry loop', edge_type: 'retry_loop', sourceHandle: 'right', targetHandle: 'target-right' },
  { id: 'final_answer->__end__', source: 'final_answer', target: '__end__', label: '', edge_type: 'default', sourceHandle: 'bottom', targetHandle: 'top' },
  { id: 'error_terminal->__end__', source: 'error_terminal', target: '__end__', label: '', edge_type: 'default', sourceHandle: 'bottom', targetHandle: 'left' }
];

// Custom Start/End Node Component
function StartEndNode({ data, selected }) {
  const isStart = data.id === '__start__';
  const isEnd = data.id === '__end__';
  const status = data.status || 'pending';

  return (
    <div className={`flow-pill-node ${isStart ? 'start-pill' : 'end-pill'} ${status} ${selected ? 'selected' : ''}`}>
      {!isStart && <Handle type="target" position={Position.Top} id="top" className="flow-handle" />}
      {!isStart && <Handle type="target" position={Position.Left} id="left" className="flow-handle" />}
      <div className="flow-pill-content">
        <span className={`flow-pill-dot ${status}`}></span>
        <span className="flow-pill-label">{data.label}</span>
      </div>
      {!isEnd && <Handle type="source" position={Position.Bottom} id="bottom" className="flow-handle" />}
    </div>
  );
}

// Custom Process Node Component
function PipelineNode({ data, selected }) {
  const Icon = ICON_MAP[data.icon] || Layers;
  const status = data.status || 'pending';
  const durationMs = data.duration_ms;
  const retryCount = data.retry_count;
  const intent = data.intent;

  return (
    <div className={`flow-pipeline-node ${data.nodeType || 'node'} ${status} ${selected ? 'selected' : ''}`}>
      {/* 4 Multi-directional handles (both source & target for each direction) */}
      <Handle type="target" position={Position.Top} id="top" className="flow-handle handle-top" />
      <Handle type="source" position={Position.Top} id="source-top" className="flow-handle handle-top" />

      <Handle type="target" position={Position.Left} id="left" className="flow-handle handle-left" />
      <Handle type="source" position={Position.Left} id="source-left" className="flow-handle handle-left" />

      <Handle type="source" position={Position.Right} id="right" className="flow-handle handle-right" />
      <Handle type="target" position={Position.Right} id="target-right" className="flow-handle handle-right" />

      <Handle type="source" position={Position.Bottom} id="bottom" className="flow-handle handle-bottom" />
      <Handle type="target" position={Position.Bottom} id="target-bottom" className="flow-handle handle-bottom" />

      <div className="node-inner-wrapper">
        <div className="node-header">
          <div className="node-icon-wrapper">
            <Icon size={14} />
          </div>
          <div className="node-title-group">
            <span className="node-name">{data.label}</span>
            <span className="node-id-sub">
              {data.id === 'classify_intent' && intent ? (
                <strong style={{ color: '#c084fc' }}>Intent: {intent}</strong>
              ) : (
                data.id
              )}
            </span>
          </div>
          <span className={`flow-status-pill ${status}`}>
            {status.toUpperCase()}
          </span>
        </div>

        <div className="node-footer">
          <span className="node-metric-text">
            {status === 'completed' && durationMs !== undefined ? (
              <>
                <Clock size={11} /> {durationMs} ms
              </>
            ) : status === 'running' ? (
              <>
                <span className="pulse-dot"></span> Executing...
              </>
            ) : status === 'waiting' ? (
              <>
                <AlertTriangle size={11} /> Awaiting Approval
              </>
            ) : status === 'retried' ? (
              <>
                <RefreshCw size={11} /> Retry #{retryCount || 1}
              </>
            ) : status === 'failed' || status === 'blocked' ? (
              <>
                <XCircle size={11} /> Terminated
              </>
            ) : status === 'skipped' ? (
              <>
                <span className="dot-dim"></span> Skipped
              </>
            ) : (
              <>
                <span className="dot-dim"></span> Ready
              </>
            )}
          </span>

          {status === 'completed' && (
            <span className="node-check-icon">
              <Check size={12} />
            </span>
          )}
        </div>
      </div>
    </div>
  );
}

const nodeTypes = {
  startEndNode: StartEndNode,
  pipelineNode: PipelineNode
};

export default function PipelineGraphVisualizer({ latestTrace }) {
  const [graphDef, setGraphDef] = useState({
    nodes: DEFAULT_GRAPH_NODES,
    edges: DEFAULT_GRAPH_EDGES
  });
  const [nodes, setNodes, onNodesChange] = useNodesState([]);
  const [edges, setEdges, onEdgesChange] = useEdgesState([]);
  const [selectedNode, setSelectedNode] = useState(null);
  const [copiedKey, setCopiedKey] = useState(null);
  const [expandedLlmCall, setExpandedLlmCall] = useState({});
  const [showMiniMap, setShowMiniMap] = useState(true);

  // Fetch dynamic graph definition from backend
  useEffect(() => {
    axios
      .get(`${API_BASE}/api/observability/graph-definition`)
      .then((res) => {
        if (res.data?.nodes && res.data?.edges) {
          // Merge with predefined handle routing if present
          const enhancedEdges = res.data.edges.map((e) => {
            const predefined = DEFAULT_GRAPH_EDGES.find((de) => de.id === e.id);
            return {
              ...e,
              sourceHandle: predefined?.sourceHandle || 'bottom',
              targetHandle: predefined?.targetHandle || 'top'
            };
          });
          setGraphDef({
            nodes: res.data.nodes,
            edges: enhancedEdges
          });
        }
      })
      .catch((err) => {
        console.warn('Using default LangGraph topology:', err);
      });
  }, []);

  // Compute node status map from current trace telemetry
  const traceNodeStatus = useMemo(() => {
    if (!latestTrace) return {};

    const statusMap = {};
    const spans = latestTrace.spans || [];
    const isGlobalRunning = latestTrace.status === 'running' || latestTrace.status === 'awaiting_confirmation';
    const isTraceFailed = latestTrace.status === 'error' || latestTrace.status === 'failed';
    const isTraceRejected = latestTrace.status === 'rejected';

    // Check spans
    spans.forEach((span) => {
      const nodeName = span.node_name;
      let nodeStatus = 'pending';

      if (span.status === 'completed') {
        nodeStatus = 'completed';
      } else if (span.status === 'running' && isGlobalRunning) {
        nodeStatus = 'running';
      } else if (span.status === 'needs_confirmation') {
        nodeStatus = 'waiting';
      } else if (span.status === 'failed') {
        nodeStatus = 'failed';
      } else if (span.status === 'blocked') {
        nodeStatus = 'blocked';
      } else if (span.status === 'retried') {
        nodeStatus = 'retried';
      }

      statusMap[nodeName] = {
        status: nodeStatus,
        duration_ms: span.duration_ms,
        span
      };
    });

    // Handle Start & End
    if (spans.length > 0) {
      statusMap['__start__'] = { status: 'completed' };
      if (!isGlobalRunning) {
        statusMap['__end__'] = { status: isTraceFailed || isTraceRejected ? 'failed' : 'completed' };
      }
    } else if (latestTrace.status === 'success') {
      const standardNodes = [
        'receive_question',
        'inspect_schema',
        'build_schema_context',
        'classify_intent',
        'generate_sql',
        'validate_sql',
        'safety_check',
        'execute_query',
        'check_result',
        'final_answer'
      ];
      statusMap['__start__'] = { status: 'completed' };
      standardNodes.forEach((n) => {
        statusMap[n] = { status: 'completed' };
      });
      statusMap['__end__'] = { status: 'completed' };
    }

    // Special node heuristics
    if (latestTrace.retry_count && latestTrace.retry_count > 0) {
      if (!statusMap['increment_retry']) {
        statusMap['increment_retry'] = { status: 'completed', duration_ms: 1 };
      }
    }

    if (isTraceFailed || isTraceRejected) {
      if (!statusMap['error_terminal']) {
        statusMap['error_terminal'] = {
          status: isTraceRejected ? 'blocked' : 'failed',
          duration_ms: 1
        };
      }
    }

    return statusMap;
  }, [latestTrace]);

  // Build ReactFlow Nodes and Edges using clean LangGraph topology
  useEffect(() => {
    const rawNodes = graphDef.nodes.map((node) => {
      const isStartEnd = node.id === '__start__' || node.id === '__end__';
      const nodeExec = traceNodeStatus[node.id];
      const status = nodeExec ? nodeExec.status : 'pending';
      const duration_ms = nodeExec ? nodeExec.duration_ms : undefined;
      const pos = NODE_POSITIONS[node.id] || { x: 0, y: 0 };

      return {
        id: node.id,
        type: isStartEnd ? 'startEndNode' : 'pipelineNode',
        selected: selectedNode?.id === node.id,
        data: {
          id: node.id,
          label: node.label,
          desc: node.desc,
          icon: node.icon,
          nodeType: node.type,
          status,
          duration_ms,
          retry_count: latestTrace?.retry_count,
          intent: latestTrace?.intent,
          span: nodeExec?.span
        },
        position: pos
      };
    });

    // Compute the exact set of traversed and active edges from the chronological trace spans
    const executedEdgeSet = new Set();
    const activeEdgeSet = new Set();
    const spans = latestTrace?.spans || [];
    const isGlobalRunning = latestTrace?.status === 'running';
    const isAwaitingConfirmation =
      latestTrace?.status === 'awaiting_confirmation' || traceNodeStatus['safety_check']?.status === 'waiting';

    if (spans.length > 0) {
      // First edge from START to first executed node
      executedEdgeSet.add(`__start__->${spans[0].node_name}`);

      // Sequential pairwise transitions between spans
      for (let i = 0; i < spans.length - 1; i++) {
        const fromNode = spans[i].node_name;
        const toNode = spans[i + 1].node_name;
        executedEdgeSet.add(`${fromNode}->${toNode}`);
      }

      const lastSpan = spans[spans.length - 1];
      if (lastSpan.status === 'running' && spans.length > 1) {
        const prevSpan = spans[spans.length - 2];
        activeEdgeSet.add(`${prevSpan.node_name}->${lastSpan.node_name}`);
      }

      // If awaiting confirmation after safety_check
      if (isAwaitingConfirmation && (lastSpan.node_name === 'safety_check' || traceNodeStatus['safety_check'])) {
        activeEdgeSet.add('safety_check->human_confirmation');
      }

      // If trace has concluded
      if (!isGlobalRunning && !isAwaitingConfirmation) {
        if (lastSpan.node_name === 'final_answer') {
          executedEdgeSet.add('final_answer->__end__');
        } else if (lastSpan.node_name === 'error_terminal') {
          executedEdgeSet.add('error_terminal->__end__');
        }
      }
    } else if (latestTrace?.status === 'success') {
      const defaultSuccessPath = [
        '__start__->receive_question',
        'receive_question->inspect_schema',
        'inspect_schema->build_schema_context',
        'build_schema_context->classify_intent',
        'classify_intent->generate_sql',
        'generate_sql->validate_sql',
        'validate_sql->safety_check',
        'safety_check->execute_query',
        'execute_query->check_result',
        'check_result->final_answer',
        'final_answer->__end__'
      ];
      defaultSuccessPath.forEach((id) => executedEdgeSet.add(id));
    }

    const rawEdges = graphDef.edges.map((edge) => {
      const isExecuted = executedEdgeSet.has(edge.id);
      const isActive = activeEdgeSet.has(edge.id);

      // Default: Clean muted gray for ANY non-running, un-traversed edge
      let strokeColor = '#4b5563';
      let strokeWidth = 1.2;
      let strokeDash =
        edge.edge_type === 'error' || edge.edge_type === 'retry' || edge.edge_type === 'retry_loop' ? '4,4' : undefined;
      let animated = false;
      let labelColor = '#9ca3af';
      let labelBgColor = '#18181b';
      let labelBgOpacity = 0.85;

      if (isActive) {
        if (edge.id === 'safety_check->human_confirmation') {
          strokeColor = '#f59e0b'; // amber for human approval branch
          strokeWidth = 2.5;
          labelColor = '#fde68a';
          labelBgColor = '#451a03';
          labelBgOpacity = 0.95;
          strokeDash = undefined;
        } else {
          strokeColor = '#8b5cf6'; // active purple
          strokeWidth = 2.5;
          animated = true;
          labelColor = '#c084fc';
          labelBgColor = '#2e1065';
          labelBgOpacity = 0.95;
        }
      } else if (isExecuted) {
        if (edge.edge_type === 'error' || edge.target === 'error_terminal') {
          strokeColor = '#ef4444'; // ONLY the specific error edge that was executed
          strokeWidth = 2;
          strokeDash = '4,4';
          labelColor = '#fca5a5';
          labelBgColor = '#450a0a';
          labelBgOpacity = 0.95;
        } else if (edge.edge_type === 'retry' || edge.edge_type === 'retry_loop' || edge.target === 'increment_retry') {
          strokeColor = '#f59e0b'; // ONLY the specific retry edge if retry occurred
          strokeWidth = 2;
          strokeDash = '4,4';
          labelColor = '#fde68a';
          labelBgColor = '#451a03';
          labelBgOpacity = 0.95;
        } else {
          strokeColor = '#10b981'; // completed happy path green
          strokeWidth = 2;
          strokeDash = undefined;
          labelColor = '#a7f3d0';
          labelBgColor = '#064e3b';
          labelBgOpacity = 0.95;
        }
      }

      return {
        id: edge.id,
        source: edge.source,
        target: edge.target,
        sourceHandle: edge.sourceHandle || 'bottom',
        targetHandle: edge.targetHandle || 'top',
        type: 'smoothstep',
        animated,
        label: edge.label || undefined,
        labelStyle: {
          fill: labelColor,
          fontSize: 10,
          fontWeight: 600,
          fontFamily: 'Outfit, sans-serif'
        },
        labelBgStyle: {
          fill: labelBgColor,
          fillOpacity: labelBgOpacity,
          rx: 4,
          ry: 4
        },
        labelBgPadding: [6, 3],
        style: {
          stroke: strokeColor,
          strokeWidth,
          strokeDasharray: strokeDash
        },
        markerEnd: {
          type: MarkerType.ArrowClosed,
          color: strokeColor,
          width: 14,
          height: 14
        }
      };
    });

    setNodes(rawNodes);
    setEdges(rawEdges);
  }, [graphDef, traceNodeStatus, latestTrace, selectedNode]);

  const handleNodeClick = useCallback((event, node) => {
    setSelectedNode(node.data);
  }, []);

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

  // Find detailed telemetry associated with selected node
  const selectedSpan = useMemo(() => {
    if (!selectedNode || !latestTrace?.spans) return null;
    return [...latestTrace.spans].reverse().find((s) => s.node_name === selectedNode.id);
  }, [selectedNode, latestTrace]);

  const selectedLlmCalls = useMemo(() => {
    if (!selectedNode || !latestTrace?.llm_calls) return [];
    return latestTrace.llm_calls.filter((c) => c.node_name === selectedNode.id);
  }, [selectedNode, latestTrace]);

  const selectedMcpCalls = useMemo(() => {
    if (!selectedNode || !latestTrace?.mcp_calls) return [];
    if (selectedNode.id === 'inspect_schema') {
      return latestTrace.mcp_calls.filter((c) => c.tool_name === 'inspect_schema');
    }
    if (selectedNode.id === 'execute_query') {
      return latestTrace.mcp_calls.filter((c) => c.tool_name === 'execute_query' || c.tool_name === 'preview_query');
    }
    return [];
  }, [selectedNode, latestTrace]);

  const selectedGuardrails = useMemo(() => {
    if (!selectedNode || !latestTrace?.guardrail_records) return [];
    if (selectedNode.id === 'safety_check' || selectedNode.id === 'human_confirmation') {
      return latestTrace.guardrail_records;
    }
    return [];
  }, [selectedNode, latestTrace]);

  return (
    <div className="pipeline-graph-container">
      {/* Top Banner with Active Trace Status */}
      <div className="graph-banner">
        <div>
          <h3>LangGraph Execution Pipeline</h3>
          <p>Deterministic directed execution graph with live trace routing, retry loops, and guardrail branches.</p>
        </div>
        {latestTrace && (
          <div className="latest-trace-pill">
            <span>Active Trace:</span>
            <code>{latestTrace.trace_id?.slice(0, 14)}...</code>
            <span
              className={`badge badge-${
                latestTrace.status === 'success'
                  ? 'success'
                  : latestTrace.status === 'rejected'
                  ? 'danger'
                  : latestTrace.status === 'running'
                  ? 'primary'
                  : 'warning'
              }`}
            >
              {latestTrace.status?.toUpperCase()}
            </span>
          </div>
        )}
      </div>

      {/* Main Canvas & Side Drawer */}
      <div className="flow-canvas-wrapper">
        <div className="flow-canvas">
          <ReactFlow
            nodes={nodes}
            edges={edges}
            onNodesChange={onNodesChange}
            onEdgesChange={onEdgesChange}
            onNodeClick={handleNodeClick}
            nodeTypes={nodeTypes}
            fitView
            fitViewOptions={{ padding: 0.15, maxZoom: 1.1 }}
            minZoom={0.25}
            maxZoom={1.6}
            defaultEdgeOptions={{ type: 'smoothstep' }}
            proOptions={{ hideAttribution: true }}
          >
            <Background color="#27272a" gap={18} size={1} />
            <Controls className="flow-controls-custom" showInteractive={false} />
            {showMiniMap && (
              <MiniMap
                className="flow-minimap-custom"
                nodeStrokeWidth={3}
                nodeColor={(n) => {
                  if (n.data?.status === 'completed') return '#10b981';
                  if (n.data?.status === 'running') return '#8b5cf6';
                  if (n.data?.status === 'failed') return '#ef4444';
                  if (n.data?.status === 'waiting') return '#f59e0b';
                  return '#3f3f46';
                }}
                maskColor="rgba(9, 9, 11, 0.75)"
              />
            )}
          </ReactFlow>

          {/* Canvas Floating Legend */}
          <div className="flow-legend">
            <span className="legend-item"><span className="legend-dot completed"></span> Completed</span>
            <span className="legend-item"><span className="legend-dot running"></span> Running</span>
            <span className="legend-item"><span className="legend-dot waiting"></span> Waiting (HITL)</span>
            <span className="legend-item"><span className="legend-dot retry"></span> Retry Loop</span>
            <span className="legend-item"><span className="legend-dot failed"></span> Error / Terminal</span>
          </div>
        </div>

        {/* Node Telemetry Slide-Over Drawer */}
        {selectedNode && (
          <div className="node-detail-drawer">
            <div className="drawer-header">
              <div className="drawer-title-group">
                <div className={`drawer-icon-badge ${selectedNode.status}`}>
                  {React.createElement(ICON_MAP[selectedNode.icon] || Layers, { size: 16 })}
                </div>
                <div>
                  <h4 className="drawer-title">{selectedNode.label}</h4>
                  <p className="drawer-subtitle">{selectedNode.id}</p>
                </div>
              </div>
              <div className="drawer-actions">
                <span className={`status-pill ${selectedNode.status}`}>
                  {selectedNode.status.toUpperCase()}
                </span>
                <button
                  className="drawer-close-btn"
                  onClick={() => setSelectedNode(null)}
                  title="Close inspector"
                >
                  <X size={16} />
                </button>
              </div>
            </div>

            <div className="drawer-body">
              {/* Description */}
              <div className="drawer-desc-card">
                <p>{selectedNode.desc}</p>
              </div>

              {/* Execution Timing */}
              <div className="drawer-section">
                <h5 className="section-title"><Clock size={13} /> Node Execution Metrics</h5>
                <div className="metric-row-grid">
                  <div className="metric-pill">
                    <span className="metric-pill-label">Duration</span>
                    <span className="metric-pill-val">
                      {selectedSpan?.duration_ms !== undefined ? `${selectedSpan.duration_ms} ms` : (selectedNode.duration_ms !== undefined ? `${selectedNode.duration_ms} ms` : 'Not executed')}
                    </span>
                  </div>
                  <div className="metric-pill">
                    <span className="metric-pill-label">Status</span>
                    <span className="metric-pill-val uppercase">{selectedNode.status}</span>
                  </div>
                  <div className="metric-pill">
                    <span className="metric-pill-label">Start Time</span>
                    <span className="metric-pill-val mono">
                      {selectedSpan?.start_time ? selectedSpan.start_time.slice(11, 23) : '—'}
                    </span>
                  </div>
                  <div className="metric-pill">
                    <span className="metric-pill-label">End Time</span>
                    <span className="metric-pill-val mono">
                      {selectedSpan?.end_time ? selectedSpan.end_time.slice(11, 23) : '—'}
                    </span>
                  </div>
                </div>
              </div>

              {/* LLM Calls in this node */}
              {selectedLlmCalls.length > 0 && (
                <div className="drawer-section">
                  <h5 className="section-title"><Cpu size={13} /> LLM Generation Telemetry</h5>
                  {selectedLlmCalls.map((call, idx) => (
                    <div key={call.call_id || idx} className="telemetry-box">
                      <div className="telemetry-box-header" onClick={() => toggleLlmExpand(call.call_id || idx)}>
                        <div className="box-title">
                          <code>{call.model}</code>
                          <span className="badge badge-primary">{call.duration_ms} ms</span>
                        </div>
                        <div className="box-meta">
                          <span>{call.total_tokens || (call.prompt_tokens + call.completion_tokens)} tokens</span>
                          <span>${call.estimated_cost_usd?.toFixed(6) || '0.000000'}</span>
                          {expandedLlmCall[call.call_id || idx] ? <ChevronDown size={14} /> : <ChevronRight size={14} />}
                        </div>
                      </div>

                      {expandedLlmCall[call.call_id || idx] && (
                        <div className="telemetry-box-content">
                          <div className="prompt-block">
                            <div className="block-label">User / System Prompt</div>
                            <pre className="code-snippet">{call.user_prompt || call.system_prompt}</pre>
                          </div>
                          <div className="prompt-block">
                            <div className="block-label">LLM Output</div>
                            <pre className="code-snippet output">{call.response_text}</pre>
                          </div>
                        </div>
                      )}
                    </div>
                  ))}
                </div>
              )}

              {/* MCP Tool Calls in this node */}
              {selectedMcpCalls.length > 0 && (
                <div className="drawer-section">
                  <h5 className="section-title"><Database size={13} /> Model Context Protocol (MCP) Events</h5>
                  {selectedMcpCalls.map((mcp, idx) => (
                    <div key={mcp.event_id || idx} className="mcp-event-card">
                      <div className="mcp-card-header">
                        <span className="mcp-tool-name">
                          <Terminal size={12} /> {mcp.tool_name}
                        </span>
                        <span className={`badge ${mcp.ok ? 'badge-success' : 'badge-danger'}`}>
                          {mcp.ok ? 'SUCCESS' : 'FAILED'}
                        </span>
                      </div>
                      <div className="mcp-card-stats">
                        <span>Latency: <strong>{mcp.duration_ms} ms</strong></span>
                        <span>Rows: <strong>{mcp.rows_count}</strong></span>
                        <span>Agreement: <strong>{mcp.langgraph_mcp_agreement ? 'AGREED' : 'DIVERGED'}</strong></span>
                      </div>
                      {mcp.error && (
                        <div className="error-box">
                          <code>{mcp.error}</code>
                        </div>
                      )}
                    </div>
                  ))}
                </div>
              )}

              {/* Guardrail Decisions in this node */}
              {selectedGuardrails.length > 0 && (
                <div className="drawer-section">
                  <h5 className="section-title"><ShieldCheck size={13} /> Guardrail Evaluations</h5>
                  {selectedGuardrails.map((gr, idx) => (
                    <div key={gr.record_id || idx} className={`guardrail-pill-card ${gr.decision.toLowerCase()}`}>
                      <div className="gr-top">
                        <span className="gr-rule">{gr.rule_name}</span>
                        <span className={`badge badge-${gr.decision === 'ALLOWED' ? 'success' : gr.decision === 'BLOCKED' ? 'danger' : 'warning'}`}>
                          {gr.decision}
                        </span>
                      </div>
                      <p className="gr-reason">{gr.reason}</p>
                    </div>
                  ))}
                </div>
              )}

              {/* Span Input / Output Payloads */}
              {selectedSpan && (selectedSpan.input_data || selectedSpan.output_data) && (
                <div className="drawer-section">
                  <h5 className="section-title"><FileCode2 size={13} /> Node State Transition Payloads</h5>
                  {selectedSpan.input_data && (
                    <div className="payload-box">
                      <div className="payload-header">
                        <span>Input State Snapshot</span>
                        <button
                          className="copy-btn-tiny"
                          onClick={() => handleCopy(JSON.stringify(selectedSpan.input_data, null, 2), 'input_payload')}
                        >
                          {copiedKey === 'input_payload' ? <Check size={11} /> : <Copy size={11} />} Copy JSON
                        </button>
                      </div>
                      <pre className="code-snippet">{JSON.stringify(selectedSpan.input_data, null, 2)}</pre>
                    </div>
                  )}

                  {selectedSpan.output_data && (
                    <div className="payload-box">
                      <div className="payload-header">
                        <span>Output State Snapshot</span>
                        <button
                          className="copy-btn-tiny"
                          onClick={() => handleCopy(JSON.stringify(selectedSpan.output_data, null, 2), 'output_payload')}
                        >
                          {copiedKey === 'output_payload' ? <Check size={11} /> : <Copy size={11} />} Copy JSON
                        </button>
                      </div>
                      <pre className="code-snippet output">{JSON.stringify(selectedSpan.output_data, null, 2)}</pre>
                    </div>
                  )}
                </div>
              )}

              {/* Node Error (if any) */}
              {selectedSpan?.error && (
                <div className="drawer-section">
                  <h5 className="section-title error-text"><XCircle size={13} /> Error Details</h5>
                  <div className="error-box">
                    <code>{selectedSpan.error}</code>
                  </div>
                </div>
              )}
            </div>
          </div>
        )}
      </div>
    </div>
  );
}
