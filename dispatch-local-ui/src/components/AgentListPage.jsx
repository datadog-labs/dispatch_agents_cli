import React from 'react';
import { useNavigate } from 'react-router-dom';
import { Button } from '@ui/button';
import { Waypoints, RefreshCw } from 'lucide-react';
import { LocalAgentTable } from './LocalAgentTable';
import { PageHeader } from './PageHeader';

const AgentListPage = ({ appState }) => {
  const navigate = useNavigate();
  const {
    loading,
    agents,
    refreshAgents,
    runningAgents,
    totalTopics
  } = appState;

  const handleAgentSelect = (agent) => {
    navigate('/agents/' + encodeURIComponent(agent.name));
  };

  return (
    <div className="h-full overflow-y-auto pt-3 px-6 pb-6">
    <div className="space-y-6">
      <PageHeader
        title="Agents"
        description={`Test and monitor your agents locally • ${runningAgents} running`}
        icon={Waypoints}
        namespace="Local"
        actions={
          <Button onClick={refreshAgents} variant="outline" className="gap-2">
            <RefreshCw className="w-4 h-4" />
            Refresh
          </Button>
        }
      />

      {/* Agent Table */}
      <LocalAgentTable
        agents={agents}
        onAgentSelect={handleAgentSelect}
        isLoading={loading}
      />
    </div>
    </div>
  );
};

export default AgentListPage;