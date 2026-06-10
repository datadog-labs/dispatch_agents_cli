import React, { useState, useEffect, useCallback } from 'react';
import { HashRouter, Routes, Route, Navigate } from 'react-router-dom';
import { Toaster } from 'sonner';
import { LocalSidebar } from './LocalSidebar';
import { LocalHeader } from './LocalHeader';
import AgentListPage from './AgentListPage';
import AgentDetailsPage from './AgentDetailsPage';
import TopicsPage from './TopicsPage';
import TopicDetailsPage from './TopicDetailsPage';
import LLMConfigPage from './LLMConfigPage';

const App = () => {
  // Core app state
  const [loading, setLoading] = useState(true);
  const [agents, setAgents] = useState([]);
  const [systemStatus, setSystemStatus] = useState({});
  const [topics, setTopics] = useState([]);
  const [healthStatus, setHealthStatus] = useState('loading');

  // Persists output (messages + llmCalls) across navigation, keyed by agent name
  const [agentOutputs, setAgentOutputs] = useState({});
  const updateAgentOutput = useCallback((agentName, data) => {
    setAgentOutputs(prev => ({ ...prev, [agentName]: data }));
  }, []);
  const getAgentOutput = useCallback((agentName) => agentOutputs[agentName] || null, [agentOutputs]);

  // Status helper methods
  const statusLevel = (status) => {
    const normalized = (status || '').toString().toLowerCase();
    if (['healthy', 'deployed', 'active', 'running'].includes(normalized)) return 'good';
    if (['building', 'pending', 'deploying'].includes(normalized)) return 'pending';
    return 'bad';
  };

  const statusBadgeClass = (status) => {
    const level = statusLevel(status);
    if (level === 'good') return 'bg-emerald-500 text-white px-2 py-1 text-xs font-medium rounded-md';
    if (level === 'pending') return 'bg-amber-500 text-white px-2 py-1 text-xs font-medium rounded-md';
    return 'bg-red-500 text-white px-2 py-1 text-xs font-medium rounded-md';
  };

  // Computed properties
  const runningAgents = agents.filter(agent => statusLevel(agent.status) === 'good').length;
  const totalTopics = topics.length || 0;

  // API functions
  const checkHealth = async () => {
    try {
      const response = await fetch('/health');
      setHealthStatus(response.ok ? 'healthy' : 'error');
    } catch (error) {
      setHealthStatus('error');
    }
  };

  const loadSystemStatus = async () => {
    try {
      const response = await fetch('/system/status');
      if (response.ok) setSystemStatus(await response.json());
    } catch (error) {}
  };

  const loadAgents = async () => {
    try {
      const response = await fetch('/api/unstable/agents/list');
      if (response.ok) {
        const data = await response.json();
        setAgents((data || []).map(agent => ({
          ...agent,
          status: agent?.status ? agent.status.toString().toLowerCase() : '',
        })));
      }
    } catch (error) {
      setAgents([]);
    }
  };

  const loadTopics = async () => {
    try {
      const response = await fetch('/ui/topics');
      if (response.ok) {
        const data = await response.json();
        setTopics(data.topics || []);
      } else {
        setTopics([]);
      }
    } catch (error) {
      setTopics([]);
    }
  };

  const refreshAgents = async () => {
    setLoading(true);
    await loadAgents();
    setLoading(false);
  };

  // Initialization + polling
  useEffect(() => {
    const init = async () => {
      await checkHealth();
      await loadSystemStatus();
      await loadAgents();
      await loadTopics();
      setLoading(false);
    };

    init();

    const interval = setInterval(() => {
      checkHealth();
      if (Math.random() < 0.6) {
        loadSystemStatus();
        loadTopics();
      }
      if (Math.random() < 0.8) {
        loadAgents();
      }
    }, 5000);

    return () => clearInterval(interval);
  }, []);

  const appState = {
    loading,
    setLoading,
    agents,
    setAgents,
    systemStatus,
    topics,
    healthStatus,
    runningAgents,
    totalTopics,
    statusLevel,
    statusBadgeClass,
    refreshAgents,
    checkHealth,
    loadSystemStatus,
    loadAgents,
    loadTopics,
    getAgentOutput,
    updateAgentOutput,
  };

  return (
    <HashRouter>
      <div className="h-screen flex flex-col relative app-background">
        <div className="h-1 bg-gradient-to-r from-yellow-400 via-yellow-500 to-amber-500 flex-shrink-0" />
        <div className="flex flex-1 overflow-hidden">
          <LocalSidebar />
          <div className="flex-1 flex flex-col overflow-hidden relative" style={{ background: '#fcfdff' }}>
            <LocalHeader />
            <div className="flex-1 overflow-hidden bg-white relative flex flex-col">
              <Routes>
                <Route path="/" element={<Navigate to="/agents" replace />} />
                <Route path="/agents" element={<AgentListPage appState={appState} />} />
                <Route path="/agents/:agentName" element={<AgentDetailsPage appState={appState} />} />
                <Route path="/topics" element={<TopicsPage appState={appState} />} />
                <Route path="/topics/:topicName" element={<TopicDetailsPage appState={appState} />} />
                <Route path="/settings/llm-keys" element={<LLMConfigPage />} />
              </Routes>
            </div>
          </div>
        </div>
      </div>
      <Toaster position="bottom-right" richColors />
    </HashRouter>
  );
};

export default App;
