import React, { useState, useEffect, useCallback, useRef } from 'react';
import { History, Trash2, ChevronRight } from 'lucide-react';
import { Button } from '@ui/button';
import { Dialog, DialogContent, DialogHeader, DialogTitle } from '@ui/dialog';
import MessageFeedCard from './MessageFeedCard';

// Shared run-history tab used by AgentFunctionsPanel and TopicDetailsPage.
// Manages its own fetch/clear state so neither parent has to duplicate that logic.
//
// Props:
//   agentKey          — identifies the agent in /api/unstable/agents/{key}/runs
//   refreshKey        — increment to trigger a refetch (e.g. after a run completes)
//   filter            — optional (run) => boolean; filters the displayed list
//   isTopicView       — passed to MessageFeedCard so it renders the topic-feed layout
//   emptyMessage      — secondary text under "No runs yet" (context-specific)
//   showFooter        — show "Runs are cleared when the router stops" footer
//   onAllRunsChange   — called with the full unfiltered list whenever it changes
//   agentDisplayName  — shown in the clear-history confirmation dialog
const RunHistoryPanel = ({
  agentKey,
  refreshKey,
  filter,
  isTopicView = false,
  emptyMessage = 'Run a function to see history here',
  showFooter = false,
  onAllRunsChange,
  agentDisplayName,
}) => {
  const [allRuns, setAllRuns] = useState([]);
  const [selectedEntry, setSelectedEntry] = useState(null);
  const [showClearConfirm, setShowClearConfirm] = useState(false);

  // Keep the callback current without adding it to fetchRuns' deps — avoids
  // re-creating fetchRuns (and re-triggering the fetch effect) on every parent render.
  const onAllRunsChangeRef = useRef(onAllRunsChange);
  onAllRunsChangeRef.current = onAllRunsChange;

  const fetchRuns = useCallback(async () => {
    if (!agentKey) return;
    try {
      const res = await fetch(`/api/unstable/agents/${encodeURIComponent(agentKey)}/runs`);
      if (res.ok) {
        const data = await res.json();
        const runs = data.runs || [];
        setAllRuns(runs);
        onAllRunsChangeRef.current?.(runs);
      }
    } catch { /* non-fatal */ }
  }, [agentKey]);

  useEffect(() => { fetchRuns(); }, [fetchRuns, refreshKey]);

  const handleClear = async () => {
    try {
      await fetch(`/api/unstable/agents/${encodeURIComponent(agentKey)}/runs`, { method: 'DELETE' });
      setAllRuns([]);
      setSelectedEntry(null);
      onAllRunsChangeRef.current?.([]);
    } catch { /* non-fatal */ }
    setShowClearConfirm(false);
  };

  const displayRuns = filter ? allRuns.filter(filter) : allRuns;

  return (
    <div className="flex-1 flex min-h-0">
      {/* Left: run list */}
      <div className="w-52 shrink-0 border-r border-gray-200 flex flex-col min-h-0">
        <div className="shrink-0 flex items-center justify-between px-3 py-2 border-b border-gray-100">
          <span className="text-xs font-semibold text-gray-500 uppercase tracking-wide">
            {displayRuns.length} run{displayRuns.length !== 1 ? 's' : ''}
          </span>
          {allRuns.length > 0 && (
            <button
              onClick={() => setShowClearConfirm(true)}
              className="flex items-center gap-1 text-xs text-gray-400 hover:text-red-500 transition-colors"
            >
              <Trash2 className="w-3 h-3" />
              Clear
            </button>
          )}
        </div>
        <div className="flex-1 overflow-y-auto flex flex-col">
          {displayRuns.length === 0 ? (
            <div className="flex flex-col items-center justify-center flex-1 text-center px-3 py-8">
              <History className="w-6 h-6 text-gray-300 mb-2" />
              <p className="text-xs text-gray-400">No runs yet</p>
              <p className="text-xs text-gray-300 mt-1">{emptyMessage}</p>
            </div>
          ) : (
            <div className="flex-1">
              {displayRuns.map(run => {
                const isSelected = selectedEntry?.run_id === run.run_id;
                return (
                  <button
                    key={run.run_id}
                    onClick={() => setSelectedEntry(run)}
                    className={`w-full text-left px-3 py-2.5 transition-colors border-b border-gray-100 last:border-0 flex items-start gap-2 ${
                      isSelected ? 'bg-blue-50' : 'hover:bg-gray-50'
                    }`}
                  >
                    <div className={`w-1.5 h-1.5 rounded-full shrink-0 mt-1.5 ${run.status === 'error' ? 'bg-red-400' : 'bg-green-500'}`} />
                    <div className="flex-1 min-w-0">
                      {run.function_name && (
                        <p className="text-xs font-medium text-gray-700 truncate">{run.function_name}</p>
                      )}
                      <p className="text-[11px] text-gray-400 mt-0.5">
                        {new Date(run.timestamp).toLocaleTimeString()}
                      </p>
                    </div>
                    {isSelected && <ChevronRight className="w-3 h-3 text-blue-400 shrink-0 mt-1" />}
                  </button>
                );
              })}
            </div>
          )}
          {showFooter && (
            <p className="shrink-0 text-[10px] text-gray-300 text-center px-3 py-2 border-t border-gray-100">
              Runs are cleared when the router stops.
            </p>
          )}
        </div>
      </div>

      {/* Right: run detail */}
      <div className="flex-1 min-h-0 overflow-y-auto px-5 py-4">
        {selectedEntry ? (
          <MessageFeedCard
            key={selectedEntry.run_id}
            appState={{ isTopicDetailsPage: isTopicView }}
            staticData={{ messages: selectedEntry.messages, llm_calls: selectedEntry.llm_calls }}
          />
        ) : (
          <div className="flex flex-col items-center justify-center h-full gap-2">
            <History className="w-8 h-8 text-gray-200" />
            <p className="text-sm text-gray-400">Select a run to view its output</p>
          </div>
        )}
      </div>

      {/* Clear confirmation — lives here so neither parent needs to manage it */}
      <Dialog open={showClearConfirm} onOpenChange={setShowClearConfirm}>
        <DialogContent className="sm:max-w-sm">
          <DialogHeader>
            <DialogTitle>Clear run history?</DialogTitle>
          </DialogHeader>
          <p className="text-sm text-gray-600 pt-1">
            This will permanently delete all {allRuns.length} saved run{allRuns.length !== 1 ? 's' : ''}
            {agentDisplayName && <> for <span className="font-medium">{agentDisplayName}</span></>}.{' '}
            This cannot be undone.
          </p>
          <div className="flex justify-end gap-2 pt-2">
            <Button variant="outline" onClick={() => setShowClearConfirm(false)}>Cancel</Button>
            <Button variant="destructive" onClick={handleClear}>Clear history</Button>
          </div>
        </DialogContent>
      </Dialog>
    </div>
  );
};

export default RunHistoryPanel;
