import React, { useState, useEffect, useCallback } from 'react';
import { useParams, useNavigate } from 'react-router-dom';
import { Button } from '@ui/button';
import { SchemaDisplay } from '@ui/schema-display';
import { Radio, Waypoints, Code, RotateCcw, Send, Loader2 } from 'lucide-react';
import MessageFeedCard from './MessageFeedCard';
import RunHistoryPanel from './RunHistoryPanel';
import TabBar from './TabBar';
import JsonTextarea from './JsonTextarea';
import OutputTray from './OutputTray';
import { dotColor } from './StatusBadge';
import { useDraggableTray } from '@/hooks/useDraggableTray';
import { generateExampleFromSchema } from '@/utils/schema';

const TopicDetailsPage = ({ appState }) => {
  const { topicName } = useParams();
  const navigate = useNavigate();
  const { agents } = appState;

  const subscribingAgents = agents.filter(agent =>
    Array.isArray(agent.topics) && agent.topics.includes(topicName)
  );

  // Panel tabs
  const [activeTab, setActiveTab] = useState('send');

  // ── Run history ────────────────────────────────────────────────────────────
  // historyAgentKey uses a topic: prefix so topic runs are stored separately
  // from agent runs in the router's in-memory store.
  const historyAgentKey = `topic:${topicName}`;
  const [runHistoryCount, setRunHistoryCount] = useState(0);

  // Schema — fetched from /schemas/topics bulk endpoint, same as SendTestEventCard
  const [inputSchema, setInputSchema] = useState(null);
  const [schemaLoading, setSchemaLoading] = useState(false);
  const [schemaError, setSchemaError] = useState(null);
  const [rawSchemaEntries, setRawSchemaEntries] = useState(null);

  // Send event
  const [payload, setPayload] = useState('{}');
  const [jsonError, setJsonError] = useState(null);
  const [isSending, setIsSending] = useState(false);
  const [sendError, setSendError] = useState(null);

  // Tray
  const tray = useDraggableTray();
  const [isRunning, setIsRunning] = useState(false);
  const [hasFeedContent, setHasFeedContent] = useState(false);
  const feedClearRef = React.useRef(null);

  const topicAppState = {
    ...appState,
    selectedAgent: { name: `topic:${topicName}` },
    isTopicDetailsPage: true,
  };

  // Fetch schema — mirrors the two-step approach in SendTestEventCard
  const fetchSchema = useCallback(async () => {
    setSchemaLoading(true);
    setSchemaError(null);
    try {
      const res = await fetch('/api/unstable/schemas/topics');
      if (res.ok) {
        const data = await res.json();
        const entries = (data.topics || {})[topicName] || [];
        setRawSchemaEntries(entries);
        if (entries.length > 0 && entries[0].schema?.input_schema) {
          const s = entries[0].schema.input_schema;
          setInputSchema(s);
          const p = JSON.stringify(generateExampleFromSchema(s), null, 2);
          setPayload(p);
          return;
        }
      }
      setSchemaError('No schema registered for this topic yet.');
    } catch {
      setSchemaError('Could not load schema.');
    } finally {
      setSchemaLoading(false);
    }
  }, [topicName]);

  useEffect(() => { fetchSchema(); }, [fetchSchema]);

  // Payload validation
  const validatePayload = (val) => {
    try { JSON.parse(val); setJsonError(null); return true; }
    catch (e) { setJsonError('Invalid JSON: ' + e.message); return false; }
  };

  const handlePayloadChange = (val) => { setPayload(val); validatePayload(val); };

  const handleResetPayload = () => {
    if (inputSchema) {
      const p = JSON.stringify(generateExampleFromSchema(inputSchema), null, 2);
      setPayload(p);
      validatePayload(p);
    }
  };

  // Send event
  const handleSend = async () => {
    if (!validatePayload(payload)) return;
    setIsSending(true);
    setSendError(null);
    try {
      const res = await fetch('/api/unstable/events/publish', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ topic: topicName, payload: JSON.parse(payload), sender_id: 'ui-test' }),
      });
      if (!res.ok) { const d = await res.json().catch(() => ({})); throw new Error(d.detail || 'Failed to publish event'); }
      const data = await res.json();
      if (data.trace_id) {
        window.dispatchEvent(new CustomEvent('traceStarted', {
          detail: { traceId: data.trace_id, startPolling: true },
        }));
      }
      if (tray.isCollapsed) tray.setIsCollapsed(false);
    } catch (e) {
      setSendError(e.message);
    } finally {
      setIsSending(false);
    }
  };


  return (
    <div className="h-full flex flex-col">

      {/* Header — flat row, white background */}
      <div className="shrink-0 px-6 pt-5 pb-4 border-b border-[var(--color-warm-gray-200)] bg-white">
        <div className="flex items-center gap-3">
          <Radio className="w-5 h-5 text-purple-600 shrink-0" />
          <span className="text-lg font-semibold text-gray-900">{topicName}</span>
          <span className="text-[var(--color-warm-gray-300)] select-none">·</span>
          <span className="text-sm text-[var(--color-warm-gray-500)]">
            {subscribingAgents.length} subscribing agent{subscribingAgents.length !== 1 ? 's' : ''}
          </span>
          <span className="text-[10px] font-semibold uppercase tracking-widest text-[var(--color-warm-gray-500)] ml-1">
            • Local Testing
          </span>
        </div>
      </div>

      {/* Body — flex-col so the tray is inside this relative container (same structure as AgentDetailsPage) */}
      <div ref={tray.bodyRef} className="flex-1 flex flex-col min-h-0 relative">

        {/* Two-column content row */}
        <div
          className="flex min-h-0"
          style={tray.isOverlaying ? { height: tray.MIN_TOP_HEIGHT, flexShrink: 0 } : { flex: 1 }}
        >
          {/* Left: Send event / Schema panel */}
          <div className="flex-1 flex flex-col min-h-0">

            <TabBar
              tabs={[
                { key: 'send', label: 'Send event' },
                { key: 'schema', label: 'Schema' },
                { key: 'history', label: 'Local History', badge: runHistoryCount },
              ]}
              activeTab={activeTab}
              onChange={setActiveTab}
              className="border-b border-[var(--color-warm-gray-200)]"
            />

            {/* Send event tab */}
            <div className={`flex-1 flex flex-col min-h-0 px-5 pt-4 pb-4 gap-3 ${activeTab !== 'send' ? 'hidden' : ''}`}>
              <div className="shrink-0 flex items-center justify-between">
                <label className="text-xs font-medium text-gray-700 uppercase tracking-wide">
                  JSON Payload
                </label>
                <button
                  onClick={handleResetPayload}
                  disabled={!inputSchema || isSending}
                  className="flex items-center gap-1 text-xs text-[#677c97] hover:text-gray-700 disabled:opacity-40"
                >
                  <RotateCcw className="w-3 h-3" />
                  Reset payload
                </button>
              </div>
              <JsonTextarea
                value={payload}
                onChange={handlePayloadChange}
                error={jsonError}
                disabled={isSending}
              />
              {sendError && <p className="shrink-0 text-xs text-red-500">{sendError}</p>}
              <div className="shrink-0">
                <Button
                  onClick={handleSend}
                  disabled={isSending || !!jsonError}
                >
                  {isSending
                    ? <><Loader2 className="w-4 h-4 mr-2 animate-spin" />Sending…</>
                    : <><Send className="w-4 h-4 mr-2" />Send event</>
                  }
                </Button>
              </div>
            </div>

            {/* Schema tab */}
            <div className={`flex-1 min-h-0 overflow-y-auto px-5 py-4 ${activeTab !== 'schema' ? 'hidden' : ''}`}>
              {schemaLoading ? (
                <div className="flex items-center gap-2 text-sm text-gray-500 py-4">
                  <Loader2 className="w-4 h-4 animate-spin" />
                  Loading schema…
                </div>
              ) : schemaError ? (
                <p className="text-sm text-gray-500 py-4">{schemaError}</p>
              ) : rawSchemaEntries?.length > 0 ? (
                <div className="space-y-6">
                  {rawSchemaEntries.map((entry, i) => (
                    <div key={i} className="space-y-3">
                      <div className="flex items-center gap-2">
                        <span className="text-xs font-semibold text-gray-700">
                          {entry.schema?.handler_name || 'Handler'}
                        </span>
                        <span className="text-xs text-gray-400">— {entry.agent_name}</span>
                      </div>
                      {entry.schema?.handler_doc && (
                        <p className="text-xs text-gray-500 italic">{entry.schema.handler_doc}</p>
                      )}
                      {entry.schema?.input_schema
                        ? <SchemaDisplay schema={entry.schema.input_schema} />
                        : <p className="text-xs text-gray-400">No input schema defined.</p>
                      }
                    </div>
                  ))}
                </div>
              ) : (
                <p className="text-sm text-gray-500 py-4">No schema registered for this topic.</p>
              )}
            </div>

            {/* Local History tab */}
            <div className={`flex-1 flex min-h-0 ${activeTab !== 'history' ? 'hidden' : ''}`}>
              <RunHistoryPanel
                agentKey={historyAgentKey}
                isTopicView
                emptyMessage="Send an event to see history here"
                onAllRunsChange={(runs) => setRunHistoryCount(runs.length)}
                agentDisplayName={topicName}
              />
            </div>
          </div>

          {/* Right: Subscribing agents */}
          <div className="w-60 shrink-0 flex flex-col border-l border-[var(--color-warm-gray-200)]">
            <div className="shrink-0 px-4 py-2.5 border-b border-[var(--color-warm-gray-200)]">
              <span className="text-xs font-semibold text-gray-500 uppercase tracking-wide">
                Subscribing agents
              </span>
            </div>
            {subscribingAgents.length === 0 ? (
              <div className="flex flex-col items-center justify-center flex-1 gap-2 px-4 py-8 text-center">
                <Waypoints className="w-7 h-7 text-gray-300" />
                <p className="text-xs text-gray-400">No agents subscribe to this topic</p>
              </div>
            ) : (
              <div className="flex-1 overflow-y-auto py-1">
                {subscribingAgents.map((agent, index) => {
                  const handlerFns = (agent.functions || [])
                    .filter(f => f.triggers?.some(t => t.type === 'topic' && t.topic === topicName))
                    .map(f => f.name)
                    .filter(Boolean);
                  return (
                    <button
                      key={agent.name || index}
                      onClick={() => navigate('/agents/' + encodeURIComponent(agent.name))}
                      className="w-full flex items-start gap-2.5 px-4 py-2.5 hover:bg-gray-50 transition-colors text-left group"
                    >
                      <Waypoints className="w-4 h-4 text-teal-800 shrink-0 mt-0.5" />
                      <div className="flex flex-col min-w-0 flex-1">
                        <span className="text-sm text-gray-800 font-medium truncate group-hover:text-blue-600 transition-colors">
                          {agent.name}
                        </span>
                        {handlerFns.length > 0 && (
                          <span className="flex items-center gap-1 text-xs text-gray-400 truncate">
                            <Code className="w-3 h-3 shrink-0" />
                            {handlerFns.join(', ')}
                          </span>
                        )}
                      </div>
                      <div className={`w-2 h-2 rounded-full shrink-0 mt-1.5 ${dotColor(agent.status)}`} />
                    </button>
                  );
                })}
              </div>
            )}
          </div>
        </div>

        <OutputTray
          {...tray}
          tabs={[{ key: 'output', label: 'Output' }]}
          activeTab="output"
          onTabChange={() => {}}
          isRunning={isRunning}
          hasFeedContent={hasFeedContent}
          onClear={() => feedClearRef.current?.()}
        >
          <div className={`flex-1 min-h-0 overflow-y-auto px-6 py-4 bg-white ${tray.isCollapsed ? 'hidden' : ''}`}>
            <MessageFeedCard
              appState={topicAppState}
              onRunningChange={setIsRunning}
              onHasContentChange={setHasFeedContent}
              clearRef={feedClearRef}
            />
          </div>
        </OutputTray>
      </div>

    </div>
  );
};

export default TopicDetailsPage;
