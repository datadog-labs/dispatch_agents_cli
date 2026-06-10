import React, { useState, useEffect, useRef } from 'react';
import { Link } from 'react-router-dom';
import { Badge } from '@ui/badge';
import { Bot, Code, Copy, Check, Waypoints, Radio } from 'lucide-react';

import LLMCallCard, { LLMMessageCard } from './LLMCallCard';

const CopyButton = ({ text }) => {
  const [copied, setCopied] = useState(false);
  const handleCopy = () => {
    navigator.clipboard.writeText(text ?? '');
    setCopied(true);
    setTimeout(() => setCopied(false), 1500);
  };
  return (
    <button
      onClick={handleCopy}
      className="flex items-center gap-1 text-xs text-gray-400 hover:text-gray-600 transition-colors"
    >
      {copied ? <Check className="w-3 h-3" /> : <Copy className="w-3 h-3" />}
      {copied ? 'Copied' : 'Copy'}
    </button>
  );
};

// Build the unified LLM conversation timeline for a set of LLM calls.
// Groups by subprocess_id, uses the largest subprocess as the primary thread.
const buildConversationMessages = (llmCallsList) => {
  if (llmCallsList.length === 0) return [];
  const conversationMessages = [];

  const subprocessGroups = new Map();
  llmCallsList.forEach(call => {
    const spId = call.subprocess_id || '_default';
    if (!subprocessGroups.has(spId)) subprocessGroups.set(spId, []);
    subprocessGroups.get(spId).push(call);
  });

  let primaryCalls = llmCallsList;
  if (subprocessGroups.size > 1) {
    let maxSize = 0;
    subprocessGroups.forEach(calls => {
      if (calls.length > maxSize) { maxSize = calls.length; primaryCalls = calls; }
    });
  }

  const lastCall = primaryCalls[primaryCalls.length - 1];
  (lastCall.messages || []).forEach(msg => {
    if (msg.role === 'assistant') {
      const match = primaryCalls.find(c =>
        c.response_content && msg.content &&
        typeof msg.content === 'string' &&
        c.response_content === msg.content
      );
      conversationMessages.push({ ...msg, _model: match?.model || primaryCalls[0]?.model });
    } else {
      conversationMessages.push({ ...msg });
    }
  });

  if (lastCall.response_content && lastCall.response_content !== '[streamed]') {
    conversationMessages.push({ role: 'assistant', content: lastCall.response_content, _model: lastCall.model });
  } else if (lastCall.tool_calls?.length > 0) {
    conversationMessages.push({ role: 'assistant', content: null, tool_calls: lastCall.tool_calls, _model: lastCall.model });
  }

  return conversationMessages;
};

const MessageFeedCard = ({ appState, onRunningChange, clearRef, onHasContentChange, staticData }) => {
  const { selectedAgent, getAgentOutput, updateAgentOutput, isTopicDetailsPage } = appState || {};
  const agentName = selectedAgent?.name;
  const isStatic = !!staticData;

  const [messages, setMessages] = useState(() => {
    if (isStatic) return staticData.messages || [];
    const saved = getAgentOutput?.(agentName);
    return saved?.messages || [];
  });
  const [llmCalls, setLlmCalls] = useState(() => {
    if (isStatic) return staticData.llm_calls || [];
    const saved = getAgentOutput?.(agentName);
    return saved?.llmCalls || [];
  });
  const [activeTraceId, setActiveTraceId] = useState(null);
  const pollingIntervalRef = useRef(null);
  // Traces actively polled in this component instance — only these get saved to history.
  // Prevents re-hydrated historical traces from being re-saved on every mount.
  const tracesPolledRef = useRef(new Set());
  // Deduplicates saves: once a trace is saved, subsequent effect re-runs skip it.
  const savedTracesRef = useRef(new Set());

  useEffect(() => {
    if (isStatic) return;
    if (agentName && updateAgentOutput) updateAgentOutput(agentName, { messages, llmCalls });
  }, [messages, llmCalls]);

  useEffect(() => {
    if (isStatic) return;
    onRunningChange?.(!!activeTraceId);
  }, [activeTraceId]);

  useEffect(() => {
    if (isStatic) return;
    onHasContentChange?.(messages.length > 0 || llmCalls.length > 0);
  }, [messages, llmCalls]);

  // Save completed traces to run history on the router backend
  useEffect(() => {
    if (isStatic || !agentName || messages.length === 0) return;
    const byTrace = new Map();
    messages.forEach(msg => {
      const tid = msg.trace_id || 'no-trace';
      if (!byTrace.has(tid)) byTrace.set(tid, []);
      byTrace.get(tid).push(msg);
    });
    byTrace.forEach((traceMsgs, traceId) => {
      if (traceId === 'no-trace' || savedTracesRef.current.has(traceId)) return;
      // Only save traces that were polled live in this session, not re-hydrated ones
      if (!tracesPolledRef.current.has(traceId)) return;
      const invMsgs = traceMsgs.filter(m => m.invocation_id);
      if (invMsgs.length === 0) return;
      const allDone = invMsgs.every(m =>
        m.invocation_status === 'completed' || m.invocation_status === 'error'
      );
      if (!allDone) return;
      savedTracesRef.current.add(traceId);
      const firstInv = invMsgs[0];
      const functionName = firstInv.function_name || firstInv.topic || 'unknown';
      const hasError = invMsgs.some(m => m.invocation_status === 'error');
      const errorInv = invMsgs.find(m => m.invocation_status === 'error');
      const traceLlmCalls = llmCalls.filter(c => c.trace_id === traceId);
      const runRecord = {
        run_id: traceId,
        function_name: functionName,
        payload: firstInv.payload || null,
        messages: traceMsgs,
        llm_calls: traceLlmCalls,
        status: hasError ? 'error' : 'success',
        error_message: errorInv?.invocation_error || null,
        timestamp: traceMsgs[0]?.ts || traceMsgs[0]?.stored_at || new Date().toISOString(),
      };
      fetch(`/api/unstable/agents/${encodeURIComponent(agentName)}/runs`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify(runRecord),
      }).catch(() => {});
    });
  }, [messages, llmCalls]);

  const messagesEndRef = useRef(null);
  const clearedRef = useRef(false);

  useEffect(() => {
    if (isStatic) return;
    messagesEndRef.current?.scrollIntoView({ behavior: 'smooth' });
  }, [messages, llmCalls]);

  const flattenEventTree = (events, result = []) => {
    for (const event of events) {
      const { children, ...eventWithoutChildren } = event;
      result.push(eventWithoutChildren);
      if (children?.length > 0) flattenEventTree(children, result);
    }
    return result;
  };

  const pollTraceMessages = async (traceId) => {
    if (!traceId) return;
    try {
      const response = await fetch(`/api/unstable/events/trace/${traceId}`);
      if (!response.ok) return;
      const data = await response.json();

      let traceEvents = data.events || data.messages || [];
      if (traceEvents.some(e => e.children?.length > 0)) {
        traceEvents = flattenEventTree(traceEvents);
      }
      traceEvents.sort((a, b) => {
        const timeA = a.effective_timestamp || a.timestamp || a.ts || '';
        const timeB = b.effective_timestamp || b.timestamp || b.ts || '';
        return timeA.localeCompare(timeB);
      });

      const llmCallEvents = traceEvents.filter(e => e.message_type === 'llm_call');
      const nonLlmEvents = traceEvents.filter(e => e.message_type !== 'llm_call');
      const legacyLlmCalls = data.llm_calls || [];

      if (nonLlmEvents.length > 0) {
        let shouldStop = false;

        setMessages(prevMessages => {
          if (clearedRef.current) return prevMessages;
          const existingByUid = new Map(prevMessages.map(m => [m.uid, m]));
          const existingMessageKeys = new Set(prevMessages.map(m =>
            `${m.trace_id || ''}-${m.topic || m.function_name}-${m.sender_id}-${JSON.stringify(m.payload)}`
          ));

          const updatedUids = new Set();
          const newMessages = [];

          for (const m of nonLlmEvents) {
            const existing = existingByUid.get(m.uid);
            if (existing) {
              if (existing.invocation_status !== m.invocation_status) {
                updatedUids.add(m.uid);
                existingByUid.set(m.uid, m);
              }
            } else {
              const key = `${m.trace_id || ''}-${m.topic || m.function_name}-${m.sender_id}-${JSON.stringify(m.payload)}`;
              if (!existingMessageKeys.has(key)) newMessages.push(m);
            }
          }

          const allChangedMessages = [
            ...newMessages,
            ...[...updatedUids].map(uid => existingByUid.get(uid)),
          ];

          if (updatedUids.size > 0 || newMessages.length > 0) {
            const rebuilt = prevMessages.map(m =>
              updatedUids.has(m.uid) ? existingByUid.get(m.uid) : m
            );
            const nextMessages = [...rebuilt, ...newMessages];

            // Stop only when ALL invocations in the trace are terminal
            const invocationMessages = nextMessages.filter(m => m.invocation_id);
            const hasLegacyComplete = allChangedMessages.some(msg => msg?.topic?.endsWith('.response'));
            const allInvocationsDone = invocationMessages.length > 0 &&
              invocationMessages.every(m =>
                m.invocation_status === 'completed' || m.invocation_status === 'error'
              );
            if (allInvocationsDone || hasLegacyComplete) shouldStop = true;

            return nextMessages;
          }
          return prevMessages;
        });

        if (shouldStop) stopPolling();
      }

      const allLlmCalls = [
        ...llmCallEvents.map(e => ({
          ...e,
          llm_call_id: e.uid,
          messages: e.request_messages,
          tool_calls: e.response_tool_calls,
        })),
        ...legacyLlmCalls,
      ];

      if (allLlmCalls.length > 0) {
        setLlmCalls(prevLlmCalls => {
          if (clearedRef.current) return prevLlmCalls;
          const existingIds = new Set(prevLlmCalls.map(c => c.llm_call_id || c.uid));
          const newCalls = allLlmCalls.filter(c => !existingIds.has(c.llm_call_id || c.uid));
          return newCalls.length > 0 ? [...prevLlmCalls, ...newCalls] : prevLlmCalls;
        });
      }
    } catch {
      // Transient polling error — next 2-second tick will retry
    }
  };

  const stopPolling = () => {
    if (pollingIntervalRef.current) {
      clearInterval(pollingIntervalRef.current);
      pollingIntervalRef.current = null;
      setActiveTraceId(null);
    }
  };

  const startTracePolling = (traceId, timeoutSeconds = 3600) => {
    tracesPolledRef.current.add(traceId);
    clearedRef.current = false;
    if (pollingIntervalRef.current) {
      clearInterval(pollingIntervalRef.current);
      pollingIntervalRef.current = null;
    }
    setActiveTraceId(traceId);
    pollTraceMessages(traceId);
    const interval = setInterval(() => pollTraceMessages(traceId), 2000);
    pollingIntervalRef.current = interval;
    // 2× multiplier is intentional: matches SendTestEventCard's safety margin
    // so the UI doesn't cut off before the backend's own timeout fires.
    setTimeout(() => {
      if (pollingIntervalRef.current === interval) {
        clearInterval(interval);
        pollingIntervalRef.current = null;
        setActiveTraceId(null);
      }
    }, timeoutSeconds * 2 * 1000);
  };

  const clearMessages = () => {
    clearedRef.current = true;
    setMessages([]);
    setLlmCalls([]);
    stopPolling();
  };

  useEffect(() => {
    if (isStatic) return;
    // When navigating to a different agent/topic, sync local state from the store.
    // For topic pages, getAgentOutput returns null → always resets to empty.
    // For agent pages, this re-hydrates from whatever was persisted for that agent.
    const saved = getAgentOutput?.(agentName);
    const restoredMessages = saved?.messages || [];
    setMessages(restoredMessages);
    setLlmCalls(saved?.llmCalls || []);
    // Pre-populate savedTracesRef with existing trace IDs so re-hydrated runs aren't re-saved
    savedTracesRef.current = new Set(restoredMessages.map(m => m.trace_id).filter(Boolean));
    return () => { stopPolling(); };
  }, [agentName]);

  useEffect(() => {
    if (isStatic) return;
    const runningMsgs = messages.filter(m => m.invocation_status === 'running' && m.trace_id);
    if (runningMsgs.length > 0) startTracePolling(runningMsgs[0].trace_id);
  }, []); // eslint-disable-line react-hooks/exhaustive-deps

  useEffect(() => {
    if (isStatic) return;
    const handleTraceEvent = (event) => {
      if (event.detail.immediateMessages?.length > 0) {
        const immediateMessages = event.detail.immediateMessages;
        setMessages(prevMessages => {
          const existingUids = new Set(prevMessages.map(m => m.uid));
          const newMessages = immediateMessages.filter(m => !existingUids.has(m.uid));
          return newMessages.length > 0 ? [...prevMessages, ...newMessages] : prevMessages;
        });
        if (immediateMessages.some(msg => msg.topic?.includes('.response'))) return;
      }
      if (event.detail.startPolling && event.detail.traceId) {
        startTracePolling(event.detail.traceId, event.detail.timeoutSeconds);
      }
    };
    window.addEventListener('traceStarted', handleTraceEvent);
    return () => window.removeEventListener('traceStarted', handleTraceEvent);
  }, []);

  const formatTimestamp = (timestamp) => new Date(timestamp).toLocaleTimeString();

  // Build trace groups: one group per trace_id, each with a tree of per-invocation buckets.
  //
  // The parent_id chain is:
  //   TopicA (parent_id=null)
  //     → inv1 synthetic event (parent_id=TopicA.uid)     [backend fix]
  //       → TopicB (parent_id=inv1.invocation_id)         [set by SDK on publish]
  //         → inv2 synthetic event (parent_id=TopicB.uid) [backend fix]
  //
  // We use eventsByUid to walk this chain and compute parentInvocationId for each invocation,
  // then wire up children[] so the render can recurse.
  const traceGroups = React.useMemo(() => {
    const byTrace = new Map();

    messages.forEach(msg => {
      const traceId = msg.trace_id || 'no-trace';
      if (!byTrace.has(traceId)) {
        byTrace.set(traceId, {
          traceId,
          timestamp: msg.ts || msg.stored_at || '',
          eventsByUid: new Map(),
          topicEvents: [],
          invocationMap: new Map(),
        });
      }
      const group = byTrace.get(traceId);

      const msgTime = msg.ts || msg.stored_at || '';
      if (msgTime && (!group.timestamp || msgTime < group.timestamp)) group.timestamp = msgTime;

      if (msg.uid) group.eventsByUid.set(msg.uid, msg);

      if (msg.message_type === 'topic' || msg.type === 'topic') {
        group.topicEvents.push(msg);
      } else if (msg.invocation_id) {
        group.invocationMap.set(msg.invocation_id, { event: msg, llmCalls: [], children: [] });
      } else if (msg.message_type === 'function' || msg.function_name) {
        const key = msg.uid || `fn-${msg.function_name}-${msg.sender_id}`;
        if (!group.invocationMap.has(key)) {
          group.invocationMap.set(key, { event: msg, llmCalls: [], children: [] });
        }
      }
    });

    llmCalls.forEach(call => {
      const traceId = call.trace_id || 'no-trace';
      if (!byTrace.has(traceId)) return;
      const group = byTrace.get(traceId);
      const invId = call.parent_id || call.invocation_id;
      if (invId && group.invocationMap.has(invId)) {
        group.invocationMap.get(invId).llmCalls.push(call);
      }
      // Unmatched calls (arrived before their invocation event) are dropped rather than
      // misattributed to the first invocation in a multi-agent trace.
    });

    const result = Array.from(byTrace.values()).map(group => {
      const { traceId, eventsByUid, topicEvents, invocationMap } = group;

      // Root topic = the originating event (no parent_id, or earliest if all have parents)
      const rootTopic = topicEvents.find(t => !t.parent_id) || topicEvents[0] || null;

      // Enrich each invocation: walk inv.event.parent_id → topic → topic.parent_id → parentInv
      const invocations = Array.from(invocationMap.values()).map(inv => {
        const triggerTopicUid = inv.event?.parent_id;
        let parentInvocationId = null;
        let triggerTopicName = null;

        if (triggerTopicUid) {
          const triggerTopic = eventsByUid.get(triggerTopicUid);
          if (triggerTopic) {
            triggerTopicName = triggerTopic.topic || null;
            // triggerTopic.parent_id is the invocation_id that emitted this topic
            parentInvocationId = triggerTopic.parent_id || null;
          }
        }

        return {
          ...inv,
          traceId,
          parentInvocationId,
          triggerTopicName,
          llmCalls: inv.llmCalls.slice().sort((a, b) => (a.ts || '').localeCompare(b.ts || '')),
        };
      });

      // Wire parent→children
      const invById = new Map(invocations.map(inv => [
        inv.event?.invocation_id || inv.event?.uid,
        inv,
      ]));
      invocations.forEach(inv => {
        if (inv.parentInvocationId && invById.has(inv.parentInvocationId)) {
          invById.get(inv.parentInvocationId).children.push(inv);
        }
      });
      invocations.forEach(inv => {
        inv.children.sort((a, b) => (a.event?.ts || '').localeCompare(b.event?.ts || ''));
      });

      const rootInvocations = invocations
        .filter(inv => !inv.parentInvocationId)
        .sort((a, b) => (a.event?.ts || a.event?.stored_at || '').localeCompare(b.event?.ts || b.event?.stored_at || ''));

      return {
        traceId,
        timestamp: group.timestamp,
        rootTopicName: rootTopic?.topic || null,
        invocations: rootInvocations,
      };
    });

    result.sort((a, b) => (a.timestamp || '').localeCompare(b.timestamp || ''));
    return result;
  }, [messages, llmCalls]);

  const hasContent = messages.length > 0 || llmCalls.length > 0;
  if (clearRef) clearRef.current = clearMessages;

  // Renders one invocation card and recursively renders any child invocations beneath it.
  // depth > 0 means this invocation was triggered by a topic emitted from a parent invocation.
  // isInMultiAgentTrace means multiple agents responded to the same root topic.
  const renderInvocationCard = (inv, depth, isInMultiAgentTrace, groupTraceId, groupTimestamp) => {
    const invocation = inv.event;
    const llmCallsList = inv.llmCalls;
    const conversationMessages = buildConversationMessages(llmCallsList);

    const totalCost = llmCallsList.reduce((sum, c) => sum + (c.cost_usd || 0), 0);
    const totalInputTokens = llmCallsList.reduce((sum, c) => sum + (c.input_tokens || 0), 0);
    const totalOutputTokens = llmCallsList.reduce((sum, c) => sum + (c.output_tokens || 0), 0);
    const totalLatency = llmCallsList.reduce((sum, c) => sum + (c.latency_ms || 0), 0);

    // Show the agent chip whenever we're in a topic context (topic page, multi-agent, or chained)
    const showAgentChip = (isTopicDetailsPage || isInMultiAgentTrace || depth > 0) && invocation?.target_agent;

    return (
      <div key={`inv-${invocation?.invocation_id || invocation?.uid || depth}`}>
        <div className="rounded-lg border border-gray-200 bg-white overflow-hidden shadow-sm">
          {/* Invocation Header */}
          <div className="bg-gradient-to-r from-gray-50 to-gray-100 px-4 py-3 border-b border-gray-200">
            <div className="flex items-center justify-between">
              <div className="flex items-center gap-2">
                {invocation && (
                  <>
                    {showAgentChip && (
                      <Badge className="bg-white text-gray-700 border-gray-200 flex items-center gap-1">
                        <Waypoints className="w-3 h-3 shrink-0 text-teal-800" />
                        {invocation.target_agent}
                      </Badge>
                    )}
                    <Badge className="bg-gray-100 text-gray-700 border-gray-200 flex items-center gap-1">
                      <Code className="w-3 h-3 shrink-0" />
                      {invocation.function_name || invocation.target_agent || 'unknown'}
                    </Badge>
                  </>
                )}
                {invocation?.invocation_status === 'completed' && (
                  <Badge className="bg-green-100 text-green-800 text-xs">Completed</Badge>
                )}
                {invocation?.invocation_status === 'error' && (
                  <Badge className="bg-red-100 text-red-800 text-xs">Error</Badge>
                )}
                {invocation?.invocation_status === 'running' && (
                  <Badge className="bg-yellow-100 text-yellow-800 text-xs">Running</Badge>
                )}
              </div>
              {/* Show timestamp only on root cards in single-agent traces */}
              {depth === 0 && !isInMultiAgentTrace && (
                <span className="text-xs text-gray-500">{formatTimestamp(groupTimestamp)}</span>
              )}
            </div>

            {llmCallsList.length > 0 && (
              <div className="flex items-center gap-4 mt-2 text-xs text-gray-600">
                <span className="flex items-center gap-1">
                  <Bot className="w-3.5 h-3.5" />
                  {llmCallsList.length} LLM call{llmCallsList.length !== 1 ? 's' : ''}
                </span>
                {(() => {
                  const models = [...new Set(llmCallsList.map(c => c.model).filter(Boolean))];
                  return models.length > 0 ? (
                    <span className="font-medium text-gray-700">{models.join(', ')}</span>
                  ) : null;
                })()}
                <span>{(totalInputTokens + totalOutputTokens).toLocaleString()} tokens</span>
                <span>{totalCost < 0.0001 ? '<$0.0001' : `$${totalCost.toFixed(4)}`}</span>
                <span>{totalLatency}ms</span>
              </div>
            )}
          </div>

          {/* Invocation Content */}
          <div className="p-4 space-y-3">
            {invocation?.payload && (
              <div className="bg-white border border-gray-200 rounded-lg p-3">
                <div className="flex items-center justify-between mb-1.5">
                  <span className="text-xs font-semibold text-gray-500 uppercase tracking-wide">Input</span>
                  <CopyButton text={JSON.stringify(invocation.payload, null, 2)} />
                </div>
                <pre className="text-xs font-mono text-gray-800 whitespace-pre-wrap break-words">
                  {JSON.stringify(invocation.payload, null, 2)}
                </pre>
              </div>
            )}

            {conversationMessages.length > 0 && (
              <div className="space-y-2">
                {conversationMessages.map((msg, idx) => (
                  <LLMMessageCard key={`msg-${idx}`} message={msg} index={idx} />
                ))}
              </div>
            )}

            {invocation?.invocation_status === 'completed' && invocation?.invocation_result && (
              <div className="bg-white border border-gray-200 rounded-lg p-3">
                <div className="flex items-center justify-between mb-1.5">
                  <span className="text-xs font-semibold text-gray-500 uppercase tracking-wide">Response</span>
                  <CopyButton text={JSON.stringify(invocation.invocation_result, null, 2)} />
                </div>
                <pre className="text-xs font-mono text-gray-800 whitespace-pre-wrap break-words">
                  {JSON.stringify(invocation.invocation_result, null, 2)}
                </pre>
              </div>
            )}

            {invocation?.invocation_status === 'error' && invocation?.invocation_error && (
              <div className="bg-white border border-red-200 rounded-lg p-3">
                <div className="flex items-center justify-between mb-1.5">
                  <span className="text-xs font-semibold text-red-600 uppercase tracking-wide">Error</span>
                  <CopyButton text={invocation.invocation_error} />
                </div>
                <pre className="text-xs font-mono text-red-800 whitespace-pre-wrap break-words">
                  {invocation.invocation_error}
                </pre>
              </div>
            )}

            {groupTraceId && groupTraceId !== 'no-trace' && depth === 0 && (
              <div className="text-xs text-gray-400">
                Trace: {groupTraceId.substring(0, 8)}...
              </div>
            )}
          </div>
        </div>

        {/* Child invocations: triggered by topics emitted from this invocation */}
        {inv.children?.length > 0 && (
          <div className="mt-2 ml-3 pl-3 border-l-2 border-gray-100 space-y-2">
            {inv.children.map(child => (
              <div key={`child-${child.event?.invocation_id || child.event?.uid}`}>
                {/* Topic bridge: chip linking to the topic page that chains these invocations */}
                {child.triggerTopicName && (
                  <div className="flex items-center py-1 pb-2">
                    <Link
                      to={`/topics/${encodeURIComponent(child.triggerTopicName)}`}
className="inline-flex items-center gap-1 px-2 py-0.5 bg-purple-50 text-purple-700 border border-purple-200 rounded-full text-xs font-mono hover:bg-purple-100 transition-colors relative -left-[7px]"
                    >
                      <Radio className="w-2.5 h-2.5 shrink-0" />
                      {child.triggerTopicName}
                    </Link>
                  </div>
                )}
                {renderInvocationCard(child, depth + 1, isInMultiAgentTrace, groupTraceId, groupTimestamp)}
              </div>
            ))}
          </div>
        )}
      </div>
    );
  };

  return (
    <div>
      {llmCalls.length > 0 && (
        <div className="flex items-center gap-1 mb-3 text-xs text-indigo-600">
          <Bot className="w-3 h-3" />
          {llmCalls.length} LLM call{llmCalls.length !== 1 ? 's' : ''}
        </div>
      )}

      {!hasContent ? (
        <div className="py-8 text-center text-gray-400">
          <p className="text-sm">No output yet</p>
          <p className="text-xs mt-1">Invoke a function to see results here</p>
        </div>
      ) : (
        <div className="space-y-4">
          {traceGroups.map((group, groupIndex) => {
            // Multiple root invocations = same topic triggered more than one agent simultaneously
            const isMultiAgent = group.invocations.length > 1;

            return (
              <div key={`trace-${group.traceId}-${groupIndex}`}>
                {/* Header for traces where one topic triggered multiple agents in parallel */}
                {isMultiAgent && (
                  <div className="flex items-center gap-2 mb-2 pr-1 text-xs text-gray-500">
                    <Radio className="w-3 h-3 text-purple-500 shrink-0 relative -left-1" />
                    <span className="font-medium text-gray-700">{group.rootTopicName || 'Topic'}</span>
                    <span>•</span>
                    <span>{group.invocations.length} agents</span>
                    <span className="flex-1" />
                    <span>{formatTimestamp(group.timestamp)}</span>
                  </div>
                )}

                <div className={isMultiAgent ? 'space-y-2 pl-3 border-l-2 border-purple-100' : 'space-y-0'}>
                  {group.invocations.map(inv =>
                    renderInvocationCard(inv, 0, isMultiAgent, group.traceId, group.timestamp)
                  )}
                </div>
              </div>
            );
          })}
          <div ref={messagesEndRef} />
        </div>
      )}
    </div>
  );
};

export default MessageFeedCard;
