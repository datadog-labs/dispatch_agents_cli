import React from "react";
import { Button } from "@ui/button";
import { Waypoints, Play } from "lucide-react";
import { StatusBadge } from './StatusBadge';

export function LocalAgentTable({ agents, onAgentSelect, isLoading = false }) {

  if (isLoading) {
    return (
      <div className="bg-white rounded-lg border border-[var(--color-warm-gray-200)] p-8">
        <div className="flex items-center justify-center">
          <div className="animate-spin rounded-full h-8 w-8 border-b-2 border-blue-500"></div>
          <span className="ml-3 text-gray-600">Loading agents...</span>
        </div>
      </div>
    );
  }

  if (agents.length === 0) {
    return (
      <div className="bg-white rounded-lg border border-[var(--color-warm-gray-200)] p-8">
        <div className="text-center">
          <Waypoints className="mx-auto h-12 w-12 text-gray-400" />
          <h3 className="mt-4 text-sm font-medium text-gray-900">No agents found</h3>
          <p className="mt-2 text-sm text-gray-500">
            Deploy an agent to get started
          </p>
        </div>
      </div>
    );
  }

  return (
    <div className="bg-white rounded-lg border border-[var(--color-warm-gray-200)] overflow-hidden">
      <table className="min-w-full divide-y divide-gray-200">
        <thead className="bg-gray-50">
          <tr>
            <th className="px-6 py-3 text-left text-xs font-medium text-gray-500 uppercase tracking-wider">
              Name
            </th>
            <th className="px-6 py-3 text-left text-xs font-medium text-gray-500 uppercase tracking-wider">
              URL
            </th>
            <th className="px-6 py-3 text-left text-xs font-medium text-gray-500 uppercase tracking-wider">
              Status
            </th>
            <th className="px-6 py-3" />
          </tr>
        </thead>
        <tbody className="bg-white divide-y divide-gray-200">
          {agents.map((agent, index) => (
            <tr
              key={agent.name || index}
              className="hover:bg-gray-50 cursor-pointer transition-colors duration-150"
              onClick={() => onAgentSelect(agent)}
            >
              <td className="px-6 py-4 whitespace-nowrap">
                <div className="flex items-center">
                  <Waypoints className="w-4 h-4 text-teal-800 mr-3" />
                  <div className="text-sm font-medium text-gray-900">{agent.name}</div>
                </div>
              </td>
              <td className="px-6 py-4 whitespace-nowrap">
                <div className="text-sm text-gray-500 font-mono">{agent.url || '-'}</div>
              </td>
              <td className="px-6 py-4 whitespace-nowrap">
                <StatusBadge status={agent.status} />
              </td>
              <td className="px-6 py-4 whitespace-nowrap text-right">
                <Button
                  variant="outline"
                  size="sm"
                  onClick={(e) => { e.stopPropagation(); onAgentSelect(agent); }}
                  className="gap-1.5 border-blue-500 text-blue-600 hover:bg-blue-50 hover:text-blue-700"
                >
                  <Play className="w-3.5 h-3.5" />
                  Run
                </Button>
              </td>
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  );
}