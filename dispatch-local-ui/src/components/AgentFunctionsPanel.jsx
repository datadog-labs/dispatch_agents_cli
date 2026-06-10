import React, { useState, useEffect, useCallback, useRef } from 'react';
import { Link } from 'react-router-dom';
import { Button } from '@ui/button';
import { SchemaDisplay } from '@ui/schema-display';
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from '@ui/select';
import { Code, Radio, Zap, RotateCcw, Loader2, Braces, Copy } from 'lucide-react';
import RunHistoryPanel from './RunHistoryPanel';
import TabBar from './TabBar';
import JsonTextarea from './JsonTextarea';
import { generateExampleFromSchema } from '@/utils/schema';

// ─── Main component ──────────────────────────────────────────────────────────

const AgentFunctionsPanel = ({ appState }) => {
  const { selectedAgent } = appState;

  const [functions, setFunctions] = useState([]);
  const [selectedFunc, setSelectedFunc] = useState(null);
  const [activeTab, setActiveTab] = useState('invoke');

  const [payload, setPayload] = useState('{}');
  const [jsonError, setJsonError] = useState(null);
  const [isLoadingSchema, setIsLoadingSchema] = useState(false);
  const [schemaError, setSchemaError] = useState(null);
  const [sending, setSending] = useState(false);
  const [invocationState, setInvocationState] = useState({
    status: 'idle', invocationId: null, traceId: null, result: null, error: null,
  });
  const lastSchemaTopicRef = useRef(null);
  const mountedRef = useRef(true);
  useEffect(() => () => { mountedRef.current = false; }, []);

  // ── Run history ───────────────────────────────────────────────────────────
  // runHistory is kept here (updated via RunHistoryPanel's onAllRunsChange) so
  // the tab badge and payload dropdown stay in sync with the panel's fetch results.
  const [runHistory, setRunHistory] = useState([]);
  const [historyRefreshKey, setHistoryRefreshKey] = useState(0);

  useEffect(() => {
    if (!selectedAgent) { setFunctions([]); return; }
    const map = new Map();
    for (const func of (selectedAgent.functions || [])) {
      const topicTriggers = (func.triggers || []).filter(t => t.type === 'topic' && t.topic).map(t => t.topic);
      const callableTriggers = (func.triggers || []).filter(t => t.type === 'callable');
      const isCallable = callableTriggers.length > 0;
      const callableName = isCallable ? (callableTriggers[0].function_name || func.name) : func.name;
      if (topicTriggers.length === 0 && !isCallable) continue;
      map.set(func.name, {
        id: `fn-${func.name}`,
        functionName: callableName,
        isCallable,
        topics: topicTriggers,
        description: func.description,
        inputSchema: func.input_schema,
        outputSchema: func.output_schema,
      });
    }
    setFunctions([...map.values()]);
  }, [selectedAgent]);

  useEffect(() => {
    if (functions.length === 0) {
      setSelectedFunc(null);
      return;
    }
    if (selectedFunc) {
      const refreshed = functions.find(f => f.id === selectedFunc.id);
      if (refreshed) {
        setSelectedFunc(refreshed);
        return;
      }
    }
    handleSelectFunc(functions.find(f => f.isCallable) || functions[0]);
  }, [functions]);

  const handleSelectFunc = (func) => {
    setSelectedFunc(func);
    setActiveTab('invoke');
    setInvocationState({ status: 'idle', invocationId: null, traceId: null, result: null, error: null });
    setJsonError(null);
    setSchemaError(null);
    if (func.inputSchema) {
      try { setPayload(JSON.stringify(generateExampleFromSchema(func.inputSchema), null, 2)); }
      catch { setPayload('{}'); }
    } else if (!func.isCallable && func.topics?.length > 0) {
      populateTopicSchema(func.topics[0]);
    } else {
      setPayload('{}');
    }
  };

  const populateTopicSchema = async (topicName, force = false) => {
    if (!topicName || (!force && lastSchemaTopicRef.current === topicName)) return;
    setIsLoadingSchema(true);
    setSchemaError(null);
    lastSchemaTopicRef.current = topicName;
    try {
      const res = await fetch('/api/unstable/schemas/topics');
      if (res.ok) {
        const data = await res.json();
        const schemas = (data.topics || {})[topicName] || [];
        if (schemas.length > 0 && schemas[0].schema?.input_schema) {
          const p = JSON.stringify(generateExampleFromSchema(schemas[0].schema.input_schema), null, 2);
          setPayload(p); validatePayload(p);
          return;
        }
      }
      const res2 = await fetch(`/api/unstable/schemas/${encodeURIComponent(topicName)}`);
      if (res2.ok) {
        const info = await res2.json();
        if (info.canonical_schema?.input_schema) {
          const p = JSON.stringify(generateExampleFromSchema(info.canonical_schema.input_schema), null, 2);
          setPayload(p); validatePayload(p);
        } else {
          setSchemaError('No schema available for this topic');
        }
      } else {
        setSchemaError('Schema not yet available.');
      }
    } catch {
      setSchemaError('Could not load schema.');
    } finally {
      setIsLoadingSchema(false);
    }
  };

  const validatePayload = (val) => {
    try { JSON.parse(val); setJsonError(null); return true; }
    catch (e) { setJsonError('Invalid JSON: ' + e.message); return false; }
  };

  const handlePayloadChange = (val) => { setPayload(val); validatePayload(val); };

  const pollForResult = useCallback(async (invocationId) => {
    let attempts = 0;
    const poll = async () => {
      if (!mountedRef.current) return;
      if (attempts > 7200) { setInvocationState(p => ({ ...p, status: 'error', error: 'Timed out' })); setSending(false); return; }
      try {
        const res = await fetch(`/api/unstable/invoke/${invocationId}`);
        if (!mountedRef.current) return;
        if (!res.ok) throw new Error('Failed to get status');
        const data = await res.json();
        if (!mountedRef.current) return;
        if (data.status === 'completed') {
          setInvocationState(p => ({ ...p, status: 'completed', result: data.result, traceId: data.trace_id }));
          setSending(false);
          setHistoryRefreshKey(k => k + 1);
          return;
        }
        if (data.status === 'error') {
          setInvocationState(p => ({ ...p, status: 'error', error: data.error || 'Unknown error', traceId: data.trace_id }));
          setSending(false);
          setHistoryRefreshKey(k => k + 1);
          return;
        }
        setInvocationState(p => ({ ...p, status: data.status, traceId: data.trace_id }));
        attempts++;
        setTimeout(poll, 1000);
      } catch (e) {
        if (!mountedRef.current) return;
        setInvocationState(p => ({ ...p, status: 'error', error: e.message }));
        setSending(false);
      }
    };
    poll();
  }, []);

  const handleInvoke = async () => {
    if (!validatePayload(payload) || !selectedAgent || !selectedFunc) return;
    setSending(true);
    setInvocationState({ status: 'pending', invocationId: null, traceId: null, result: null, error: null });

    if (selectedFunc.isCallable) {
      try {
        const res = await fetch('/api/unstable/invoke', {
          method: 'POST',
          headers: { 'Content-Type': 'application/json' },
          body: JSON.stringify({ agent_name: selectedAgent.name, function_name: selectedFunc.functionName, payload: JSON.parse(payload) }),
        });
        if (!res.ok) { const d = await res.json(); throw new Error(d.detail || 'Failed to invoke'); }
        const data = await res.json();
        setInvocationState(p => ({ ...p, status: 'running', invocationId: data.invocation_id, traceId: data.trace_id }));
        if (data.trace_id) window.dispatchEvent(new CustomEvent('traceStarted', { detail: { traceId: data.trace_id, startPolling: true } }));
        pollForResult(data.invocation_id);
      } catch (e) { setInvocationState({ status: 'error', invocationId: null, traceId: null, result: null, error: e.message }); setSending(false); }
    } else {
      try {
        const res = await fetch('/api/unstable/events/publish', {
          method: 'POST',
          headers: { 'Content-Type': 'application/json' },
          body: JSON.stringify({ topic: selectedFunc.topics[0], payload: JSON.parse(payload), sender_id: 'ui-test' }),
        });
        if (!res.ok) { const d = await res.json().catch(() => ({})); throw new Error(d.detail || 'Failed to publish'); }
        const data = await res.json();
        if (!data.invocation_ids?.length) {
          setInvocationState({ status: 'completed', invocationId: null, traceId: null, result: { message: 'No handlers subscribed' }, error: null });
          setSending(false);
          return;
        }
        setInvocationState(p => ({ ...p, status: 'running', invocationId: data.invocation_ids[0], traceId: data.trace_id }));
        if (data.trace_id) window.dispatchEvent(new CustomEvent('traceStarted', { detail: { traceId: data.trace_id, startPolling: true } }));
        pollForResult(data.invocation_ids[0]);
      } catch (e) { setInvocationState({ status: 'error', invocationId: null, traceId: null, result: null, error: e.message }); setSending(false); }
    }
  };

  const isInvoking = invocationState.status === 'pending' || invocationState.status === 'running';

  // Previous runs for the currently selected function
  const relevantPrevRuns = selectedFunc
    ? runHistory.filter(r => r.function_name === selectedFunc.functionName || selectedFunc.topics?.includes(r.function_name))
    : [];

  // ── render ─────────────────────────────────────────────────────────────────

  return (
    <div className="flex h-full min-h-0">

      {/* Left: function navigator */}
      <nav className="w-48 shrink-0 border-r border-gray-200 flex flex-col overflow-y-auto px-2 pt-4 pb-4">
        <p className="text-xs font-semibold text-gray-400 uppercase tracking-wider mb-2 px-2">
          Functions
        </p>
        {functions.length === 0 ? (
          <div className="flex flex-col items-center justify-center flex-1 text-center px-2">
            <Code className="w-7 h-7 text-gray-300 mb-2" />
            <p className="text-xs text-gray-400">No functions registered</p>
          </div>
        ) : (
          <ul className="space-y-0.5">
            {functions.map((func) => {
              const isActive = selectedFunc?.id === func.id;
              return (
                <li key={func.id}>
                  <button
                    onClick={() => handleSelectFunc(func)}
                    className={`w-full text-left flex items-center gap-2 px-2 py-1.5 rounded-md text-sm transition-colors ${
                      isActive
                        ? 'bg-blue-50 text-blue-700 font-medium'
                        : 'text-gray-600 hover:bg-gray-100 hover:text-gray-900'
                    }`}
                  >
                    <Code className={`w-3.5 h-3.5 shrink-0 ${isActive ? 'text-blue-500' : 'text-gray-400'}`} />
                    <span className="truncate">{func.functionName}</span>
                  </button>
                </li>
              );
            })}
          </ul>
        )}
      </nav>

      {/* Right: function card */}
      {!selectedFunc ? (
        <div className="flex-1 flex items-center justify-center">
          <p className="text-sm text-gray-400">Select a function</p>
        </div>
      ) : (
        <div className="flex-1 flex flex-col min-w-0 min-h-0">

          {/* Card header */}
          <div className="shrink-0 bg-gray-50 border-b border-gray-200 px-5 py-4">
            <div className="flex items-center justify-between">
              <div className="flex items-center gap-3">
                <Code className="w-4 h-4 text-gray-600" />
                <span className="text-lg font-semibold text-gray-900">{selectedFunc.functionName}</span>
              </div>
              <div className="flex items-center gap-2 flex-wrap justify-end">
                {selectedFunc.isCallable && (
                  <span className="inline-flex items-center px-2.5 py-0.5 rounded-full text-xs text-gray-600 bg-white border border-gray-200">
                    Direct Invoke
                  </span>
                )}
                {selectedFunc.topics?.length > 0 && (
                  <>
                    <span className="inline-flex items-center gap-1.5 px-2.5 py-0.5 rounded-full text-xs text-gray-600 bg-white border border-purple-200">
                      <Radio className="w-3 h-3 text-purple-700" />
                      Topic
                    </span>
                    {selectedFunc.topics.map(t => (
                      <Link
                        key={t}
                        to={`/topics/${encodeURIComponent(t)}`}
                        className="px-1.5 py-0.5 bg-purple-50 text-purple-700 rounded text-xs font-mono hover:bg-purple-100 transition-colors"
                      >{t}</Link>
                    ))}
                  </>
                )}
              </div>
            </div>
          </div>

          <TabBar
            tabs={[
              { key: 'invoke', label: 'Invoke' },
              { key: 'details', label: 'Details' },
              { key: 'history', label: 'Local History', badge: relevantPrevRuns.length },
            ]}
            activeTab={activeTab}
            onChange={setActiveTab}
            className="border-b border-gray-200 bg-white"
          />

          {/* Invoke tab */}
          {activeTab === 'invoke' && (
            <div className="flex-1 flex flex-col min-h-0 px-5 pt-4 pb-4 gap-3">

              <div className="shrink-0 flex items-center justify-between gap-2">
                <label className="text-xs font-medium text-gray-700 uppercase tracking-wide shrink-0">
                  JSON Payload
                </label>
                <div className="flex items-center gap-2 min-w-0">
                  {relevantPrevRuns.length > 0 && (
                    <Select
                      value=""
                      onValueChange={(runId) => {
                        const run = relevantPrevRuns.find(r => r.run_id === runId);
                        if (run?.payload) {
                          const p = JSON.stringify(run.payload, null, 2);
                          setPayload(p);
                          validatePayload(p);
                        }
                      }}
                      disabled={isInvoking}
                    >
                      <SelectTrigger className="h-7 text-xs border-gray-200 text-gray-500 max-w-[180px]">
                        <SelectValue placeholder="Use previous run payload" />
                      </SelectTrigger>
                      <SelectContent>
                        {relevantPrevRuns.map(run => (
                          <SelectItem key={run.run_id} value={run.run_id}>
                            <div className="flex items-center gap-2">
                              <div className={`w-1.5 h-1.5 rounded-full shrink-0 ${run.status === 'error' ? 'bg-red-400' : 'bg-green-500'}`} />
                              <span className="text-xs">{new Date(run.timestamp).toLocaleTimeString()}</span>
                              <span className="text-[10px] text-gray-400">{run.function_name}</span>
                            </div>
                          </SelectItem>
                        ))}
                      </SelectContent>
                    </Select>
                  )}
                  <button
                    onClick={() => {
                      if (!selectedFunc.isCallable && selectedFunc.topics?.length > 0) {
                        populateTopicSchema(selectedFunc.topics[0], true);
                      } else if (selectedFunc.inputSchema) {
                        const p = JSON.stringify(generateExampleFromSchema(selectedFunc.inputSchema), null, 2);
                        setPayload(p); validatePayload(p);
                      }
                    }}
                    disabled={isLoadingSchema || isInvoking}
                    className="flex items-center gap-1 text-xs text-blue-600 hover:text-blue-800 disabled:opacity-40 shrink-0"
                  >
                    {isLoadingSchema ? <Loader2 className="w-3 h-3 animate-spin" /> : <RotateCcw className="w-3 h-3" />}
                    Reset payload
                  </button>
                </div>
              </div>

              <JsonTextarea
                value={payload}
                onChange={handlePayloadChange}
                error={jsonError}
                disabled={isInvoking}
              />
              {schemaError && <p className="shrink-0 text-xs text-amber-600">{schemaError}</p>}

              {isInvoking && (
                <div className="shrink-0 rounded-lg p-3 space-y-2 text-xs border bg-gray-50 border-gray-200">
                  <div className="flex items-center justify-between">
                    <span className="font-medium text-gray-700">
                      {invocationState.status === 'pending' ? 'Starting…' : 'Running…'}
                    </span>
                    <Loader2 className="w-3.5 h-3.5 animate-spin text-blue-500" />
                  </div>
                  {invocationState.traceId && (
                    <div className="flex items-center gap-1.5">
                      <span className="text-gray-500">Trace:</span>
                      <code className="px-1 py-0.5 bg-white rounded border border-gray-200 text-gray-700">{invocationState.traceId}</code>
                      <button onClick={() => navigator.clipboard.writeText(invocationState.traceId)} className="p-0.5 hover:bg-white rounded">
                        <Copy className="w-3 h-3 text-gray-400" />
                      </button>
                    </div>
                  )}
                </div>
              )}

              <Button
                onClick={handleInvoke}
                disabled={sending || !!jsonError || !selectedAgent}
                className={`shrink-0 self-start ${!selectedFunc.isCallable && selectedFunc.topics?.length > 0 ? 'bg-purple-600 hover:bg-purple-700' : 'bg-blue-600 hover:bg-blue-700'}`}
              >
                {sending ? (
                  <><Loader2 className="w-4 h-4 mr-2 animate-spin" />Invoking…</>
                ) : !selectedFunc.isCallable && selectedFunc.topics?.length > 0 ? (
                  <><Radio className="w-4 h-4 mr-2" />Publish Event</>
                ) : (
                  <><Zap className="w-4 h-4 mr-2" />Invoke Function</>
                )}
              </Button>
            </div>
          )}

          {/* Details tab */}
          {activeTab === 'details' && (
            <div className="flex-1 overflow-y-auto px-5 py-4 space-y-6">
              {!selectedFunc.description && !selectedFunc.inputSchema && !selectedFunc.outputSchema && (
                <p className="text-sm text-gray-400">No details available for this function.</p>
              )}
              {selectedFunc.description && (
                <p className="text-sm text-gray-700">{selectedFunc.description}</p>
              )}
              {selectedFunc.inputSchema && (
                <div className="space-y-2">
                  <h4 className="text-sm font-medium text-gray-900 flex items-center gap-2">
                    <Braces className="w-3.5 h-3.5 text-gray-400" />
                    Input Schema
                  </h4>
                  <div className="ml-5 bg-gray-50 p-3 rounded-md">
                    <SchemaDisplay schema={selectedFunc.inputSchema} />
                  </div>
                </div>
              )}
              {selectedFunc.outputSchema && (
                <div className="space-y-2">
                  <h4 className="text-sm font-medium text-gray-900 flex items-center gap-2">
                    <Braces className="w-3.5 h-3.5 text-gray-400" />
                    Output Schema
                  </h4>
                  <div className="ml-5 bg-gray-50 p-3 rounded-md">
                    <SchemaDisplay schema={selectedFunc.outputSchema} />
                  </div>
                </div>
              )}
            </div>
          )}

          {/* Local History tab */}
          {activeTab === 'history' && (
            <RunHistoryPanel
              agentKey={selectedAgent.name}
              refreshKey={historyRefreshKey}
              filter={(run) => run.function_name === selectedFunc?.functionName || selectedFunc?.topics?.includes(run.function_name)}
              isTopicView={false}
              emptyMessage="Invoke a function to see history here"
              showFooter
              onAllRunsChange={setRunHistory}
              agentDisplayName={selectedAgent.name}
            />
          )}
        </div>
      )}
    </div>
  );
};

export default AgentFunctionsPanel;
