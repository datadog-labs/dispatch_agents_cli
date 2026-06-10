import React, { useState, useRef, useEffect, useCallback } from 'react';
import { useDraggableTray } from '@/hooks/useDraggableTray';
import { useParams, useNavigate, Link } from 'react-router-dom';
import { Button } from '@ui/button';
import { Waypoints, CheckCircle2, Key, Plug, Bot } from 'lucide-react';
import AgentFunctionsPanel from './AgentFunctionsPanel';
import MessageFeedCard from './MessageFeedCard';
import OutputTray from './OutputTray';
import { StatusBadge } from './StatusBadge';

// Consistent amber/yellow style for all alert types
const ALERT_STYLE = { color: '#b45309', bg: '#fef9c3', border: '#fde68a' };

const ALERT_ICONS = {
  missing_secret: Key,
  mcp_unavailable: Plug,
  llm_keys_missing: Bot,
};

const WarningsPanel = ({ warnings, isLoading, onNavigate }) => {
  if (isLoading) {
    return (
      <div className="flex items-center justify-center py-12 text-[var(--color-warm-gray-400)] text-sm">
        Checking for issues…
      </div>
    );
  }

  if (warnings.length === 0) {
    return (
      <div className="flex flex-col items-center justify-center py-12 gap-3">
        <CheckCircle2 className="w-8 h-8 text-[var(--color-status-green-500)]" />
        <p className="text-sm font-medium text-[var(--color-warm-gray-600)]">No issues detected</p>
        <p className="text-xs text-[var(--color-warm-gray-400)]">This agent should run cleanly in local dev mode.</p>
      </div>
    );
  }

  return (
    <div className="flex flex-col gap-3">
      {warnings.map((w, i) => {
        const Icon = ALERT_ICONS[w.type] || Key;
        return (
          <div
            key={i}
            className="rounded-lg border px-4 py-3 flex gap-3"
            style={{ background: ALERT_STYLE.bg, borderColor: ALERT_STYLE.border }}
          >
            <Icon className="w-4 h-4 shrink-0 mt-0.5" style={{ color: ALERT_STYLE.color }} />
            <div className="flex flex-col gap-1 min-w-0">
              <span className="text-xs font-semibold" style={{ color: ALERT_STYLE.color }}>
                {w.title}
              </span>
              <p className="text-xs text-[var(--color-warm-gray-600)] leading-relaxed">
                {w.description}
              </p>
              {w.type === 'llm_keys_missing' && (
                <button
                  onClick={() => onNavigate('/settings/llm-keys')}
                  className="self-start text-xs font-medium underline mt-0.5"
                  style={{ color: ALERT_STYLE.color }}
                >
                  Configure LLM keys →
                </button>
              )}
              {w.items && w.items.length > 0 && (
                <div className="flex flex-wrap gap-1.5 mt-1">
                  {w.items.map((item, j) => (
                    <code
                      key={j}
                      className="text-[10px] px-1.5 py-0.5 rounded font-mono"
                      style={{ background: 'rgba(0,0,0,0.06)', color: ALERT_STYLE.color }}
                    >
                      {item}
                    </code>
                  ))}
                </div>
              )}
            </div>
          </div>
        );
      })}
    </div>
  );
};

const AgentDetailsPage = ({ appState }) => {
  const { agentName } = useParams();
  const navigate = useNavigate();
  const { agents } = appState;

  const tray = useDraggableTray();
  const [trayTab, setTrayTab] = useState('output');
  const [isRunning, setIsRunning] = useState(false);
  const [hasFeedContent, setHasFeedContent] = useState(false);
  const feedClearRef = useRef(null);

  const [warnings, setWarnings] = useState([]);
  const [warningsLoading, setWarningsLoading] = useState(false);

  const selectedAgent = agents.find(a => a.name === agentName);

  const fetchWarnings = useCallback(async (name) => {
    if (!name) return;
    setWarningsLoading(true);
    try {
      const res = await fetch(`/api/unstable/agents/${encodeURIComponent(name)}/warnings`);
      if (res.ok) {
        const data = await res.json();
        setWarnings(data.warnings || []);
      }
    } catch {
      // Non-fatal — alerts tab will show empty state
    } finally {
      setWarningsLoading(false);
    }
  }, []);

  useEffect(() => {
    const name = selectedAgent?.name;
    if (name) fetchWarnings(name);
  }, [selectedAgent?.name, fetchWarnings]);

  if (!selectedAgent) {
    return (
      <div className="h-full flex items-center justify-center">
        <div className="text-center">
          <p className="text-[var(--color-warm-gray-500)] mb-4">
            {agents.length === 0 ? 'Loading...' : 'Agent not found'}
          </p>
          <Button onClick={() => navigate('/agents')} variant="outline">
            Back to Agents
          </Button>
        </div>
      </div>
    );
  }

  const pageAppState = { ...appState, selectedAgent };

  const warningCount = warnings.length;

  return (
    <div className="h-full flex flex-col">

      {/* Hero header */}
      <div
        className="shrink-0 px-6 pt-5 pb-4 border-b border-[var(--color-warm-gray-200)]"
        style={{ background: 'linear-gradient(135deg, hsl(150, 28%, 90%), hsl(178, 24%, 88%), hsl(210, 30%, 87%))' }}
      >
        <div className="flex items-center gap-4">
          <div className="flex items-center gap-2.5 px-3 py-1.5 rounded-md border border-white/40 bg-white/50 backdrop-blur-sm">
            <Waypoints className="w-5 h-5 text-teal-800 shrink-0" />
            <span className="text-lg font-semibold text-gray-900">{selectedAgent.name}</span>
            <div className="ml-1">
              <StatusBadge status={selectedAgent.status} />
            </div>
          </div>
          <span className="text-[10px] font-semibold uppercase tracking-widest text-[var(--color-warm-gray-500)]">
            • Local Testing
          </span>
        </div>
      </div>

      {/* Body */}
      <div ref={tray.bodyRef} className="flex-1 flex flex-col min-h-0 relative">

        {/* Top section — functions panel; locked at MIN_TOP_HEIGHT once tray starts overlapping */}
        <div
          className="min-h-0 overflow-hidden"
          style={tray.isOverlaying ? { height: tray.MIN_TOP_HEIGHT, flexShrink: 0 } : { flex: 1 }}
        >
          <AgentFunctionsPanel appState={pageAppState} />
        </div>

        <OutputTray
          {...tray}
          tabs={[
            { key: 'output', label: 'Output' },
            { key: 'alerts', label: 'Local Alerts', badge: warningCount, badgeColor: 'amber' },
          ]}
          activeTab={trayTab}
          onTabChange={setTrayTab}
          isRunning={isRunning}
          hasFeedContent={hasFeedContent}
          onClear={() => feedClearRef.current?.()}
        >
          {/* Output tab — always mounted so MessageFeedCard state survives tab switching */}
          <div className={`flex-1 min-h-0 overflow-y-auto px-6 py-4 bg-white ${(tray.isCollapsed || trayTab !== 'output') ? 'hidden' : ''}`}>
            <MessageFeedCard
              appState={pageAppState}
              onRunningChange={setIsRunning}
              onHasContentChange={setHasFeedContent}
              clearRef={feedClearRef}
            />
          </div>

          {/* Local Alerts tab */}
          <div className={`flex-1 min-h-0 overflow-y-auto px-6 py-4 bg-white ${(tray.isCollapsed || trayTab !== 'alerts') ? 'hidden' : ''}`}>
            <WarningsPanel
              warnings={warnings}
              isLoading={warningsLoading}
              onNavigate={navigate}
            />
          </div>
        </OutputTray>
      </div>
    </div>
  );
};

export default AgentDetailsPage;
