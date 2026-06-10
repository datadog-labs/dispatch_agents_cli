import React, { useState } from "react";
import { useNavigate } from "react-router-dom";
import { Radio, RefreshCw, Play } from "lucide-react";
import { Button } from "@ui/button";
import { PageHeader } from "./PageHeader";

const TopicsPage = ({ appState }) => {
  const navigate = useNavigate();
  const {
    topics,
    agents,
    loadTopics,
    loading: appLoading
  } = appState;

  const [loading, setLoading] = useState(false);

  // Simple: show loading if app is loading AND we don't have topics yet
  // This ensures we show spinner on initial load until topics arrive
  const showLoading = appLoading && topics.length === 0;



  // Get agent count for a topic
  const getAgentCountForTopic = (topicName) => {
    if (!agents || !Array.isArray(agents)) return 0;

    return agents.filter(agent => {
      if (!agent.topics || !Array.isArray(agent.topics)) return false;
      return agent.topics.includes(topicName);
    }).length;
  };

  // Handle refresh
  const handleRefresh = async () => {
    setLoading(true);
    await loadTopics();
    setLoading(false);
  };

  // Handle topic click
  const handleTopicClick = (topic) => {
    const topicName = typeof topic === 'string' ? topic : topic.name;
    navigate('/topics/' + encodeURIComponent(topicName));
  };

  // Format topics data
  const topicsData = Array.isArray(topics) ? topics.map(topic => {
    const topicName = typeof topic === 'string' ? topic : topic.topic || topic.name;
    return {
      name: topicName,
      subscribers: getAgentCountForTopic(topicName),
    };
  }) : [];

  if (showLoading) {
    return (
      <div className="h-full overflow-y-auto pt-3 px-6 pb-6 space-y-6">
        <PageHeader title="Topics" description="Sent test events to trigger local agents" icon={Radio} chips={[{ label: 'LOCAL' }]} />

        <div className="bg-white rounded-lg border border-[var(--color-warm-gray-200)] p-8">
          <div className="flex items-center justify-center">
            <div className="animate-spin rounded-full h-8 w-8 border-b-2 border-blue-500"></div>
            <span className="ml-3 text-gray-600">Loading topics...</span>
          </div>
        </div>
      </div>
    );
  }

  return (
    <div className="h-full overflow-y-auto pt-3 px-6 pb-6 space-y-6">
      <PageHeader
        title="Topics"
        description="Registered topics that agents can subscribe to"
        icon={Radio}
        namespace="Local"
        actions={
          <Button onClick={handleRefresh} disabled={loading} variant="outline" className="flex items-center gap-2">
            <RefreshCw className={`w-4 h-4 ${loading ? 'animate-spin' : ''}`} />
            Refresh
          </Button>
        }
      />

      {/* Topics Table */}
      {topicsData.length === 0 ? (
        <div className="bg-white rounded-lg border border-[var(--color-warm-gray-200)] p-8">
          <div className="text-center">
            <Radio className="mx-auto h-12 w-12 text-gray-400" />
            <h3 className="mt-4 text-sm font-medium text-gray-900">No topics found</h3>
            <p className="mt-2 text-sm text-gray-500">
              Deploy agents with topic subscriptions to see topics here
            </p>
          </div>
        </div>
      ) : (
        <div className="bg-white rounded-lg border border-[var(--color-warm-gray-200)] overflow-hidden">
          <table className="min-w-full divide-y divide-gray-200">
            <thead className="bg-gray-50">
              <tr>
                <th className="px-6 py-3 text-left text-xs font-medium text-gray-500 uppercase tracking-wider">
                  Topic Name
                </th>
                <th className="px-6 py-3 text-left text-xs font-medium text-gray-500 uppercase tracking-wider">
                  Subscribers
                </th>
                <th className="px-6 py-3" />
              </tr>
            </thead>
            <tbody className="bg-white divide-y divide-gray-200">
              {topicsData.map((topic, index) => (
                <tr
                  key={topic.name || index}
                  className="hover:bg-gray-50 cursor-pointer transition-colors duration-150"
                  onClick={() => handleTopicClick(topic)}
                >
                  <td className="px-6 py-4 whitespace-nowrap">
                    <div className="flex items-center">
                      <Radio className="w-4 h-4 text-purple-600 mr-3" />
                      <div className="text-sm font-medium text-gray-900">{topic.name}</div>
                    </div>
                  </td>
                  <td className="px-6 py-4 whitespace-nowrap">
                    <div className="text-sm text-gray-900">{topic.subscribers}</div>
                  </td>
                  <td className="px-6 py-4 whitespace-nowrap text-right">
                    <Button
                      variant="outline"
                      size="sm"
                      onClick={(e) => { e.stopPropagation(); handleTopicClick(topic); }}
                      className="gap-1.5 border-blue-500 text-blue-600 hover:bg-blue-50 hover:text-blue-700"
                    >
                      <Play className="w-3.5 h-3.5" />
                      Test
                    </Button>
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )}
    </div>
  );
};

export default TopicsPage;