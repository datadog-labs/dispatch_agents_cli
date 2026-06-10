import React from 'react';
import { ChevronDown, ChevronUp, Trash2 } from 'lucide-react';
import TabBar from './TabBar';

const controlBtn = 'flex items-center gap-1.5 px-2 py-1 rounded hover:bg-white/50 transition-colors cursor-pointer text-[#677c97]';

// Draggable output tray shared by AgentDetailsPage and TopicDetailsPage.
// Accepts the spread of useDraggableTray() return values plus tray-level config.
//
// Props from useDraggableTray:
//   trayHeight, isCollapsed, setIsCollapsed, handleDragStart,
//   handleCollapseToggle, isOverlaying, MIN_TOP_HEIGHT
//
// Tray config:
//   tabs         — [{ key, label, badge?, badgeColor? }] for the TabBar
//   activeTab    — currently active tab key
//   onTabChange  — called with the new key; OutputTray also auto-uncollapses
//   isRunning    — show "Processing…" indicator (only when output tab is active)
//   hasFeedContent — show Clear button (only when output tab is active)
//   onClear      — called when Clear is clicked
//   children     — tab panel content; callers manage their own visibility
const OutputTray = ({
  trayHeight,
  isCollapsed,
  setIsCollapsed,
  handleDragStart,
  handleCollapseToggle,
  isOverlaying,
  MIN_TOP_HEIGHT,
  tabs,
  activeTab,
  onTabChange,
  isRunning,
  hasFeedContent,
  onClear,
  children,
}) => {
  const handleTabClick = (key) => {
    if (isCollapsed) setIsCollapsed(false);
    onTabChange(key);
  };

  // Only show running/clear indicators when the output feed is the active view.
  // For single-tab trays (TopicDetailsPage) this is always true when uncollapsed.
  const isOutputActive = !isCollapsed && (tabs.length <= 1 || activeTab === 'output');

  return (
    <div
      className="border-t border-[var(--color-warm-gray-200)] flex flex-col relative"
      style={
        isCollapsed
          ? { flexShrink: 0, background: '#f3f7fe' }
          : isOverlaying
            ? { position: 'absolute', bottom: 0, left: 0, right: 0, height: trayHeight, background: '#f3f7fe', boxShadow: '0 -6px 32px rgba(0,0,0,0.10)', zIndex: 10 }
            : { height: trayHeight, flexShrink: 0, background: '#f3f7fe', boxShadow: '0 -4px 24px rgba(0,0,0,0.06)' }
      }
    >
      {/* Drag handle — straddles the top border, visible on hover */}
      {!isCollapsed && (
        <div
          className="absolute top-0 left-0 right-0 h-2 cursor-ns-resize z-10 group flex items-center justify-center"
          style={{ marginTop: '-4px' }}
          onMouseDown={handleDragStart}
        >
          <div className="w-8 h-0.5 rounded-full bg-[var(--color-warm-gray-300)] group-hover:bg-[var(--color-aqua-500)] transition-colors" />
        </div>
      )}

      {/* Header: tabs left, controls right */}
      <div className={`shrink-0 flex items-stretch justify-between ${!isCollapsed ? 'border-b border-[var(--color-warm-gray-200)]' : ''}`}>
        <TabBar
          tabs={tabs}
          activeTab={isCollapsed ? null : activeTab}
          onChange={handleTabClick}
        />

        <div className="flex items-center gap-1 px-3">
          {isOutputActive && isRunning && (
            <span className="flex items-center gap-1.5 text-xs font-medium mr-1" style={{ color: '#677c97' }}>
              <span className="w-1.5 h-1.5 rounded-full bg-blue-400 animate-pulse" />
              Processing…
            </span>
          )}
          {isOutputActive && hasFeedContent && (
            <button
              onClick={onClear}
              className={controlBtn}
              onMouseEnter={e => e.currentTarget.style.color = '#1c2e48'}
              onMouseLeave={e => e.currentTarget.style.color = '#677c97'}
            >
              <Trash2 className="w-3.5 h-3.5" />
              <span className="text-[10px] font-medium uppercase tracking-wider">Clear</span>
            </button>
          )}
          <button
            onClick={handleCollapseToggle}
            className={controlBtn}
            onMouseEnter={e => e.currentTarget.style.color = '#1c2e48'}
            onMouseLeave={e => e.currentTarget.style.color = '#677c97'}
          >
            {isCollapsed ? <ChevronUp className="w-4 h-4" /> : <ChevronDown className="w-4 h-4" />}
            <span className="text-[10px] font-medium uppercase tracking-wider">
              {isCollapsed ? 'Show' : 'Collapse'}
            </span>
          </button>
        </div>
      </div>

      {/* Content — always rendered; children manage their own hidden state */}
      {children}
    </div>
  );
};

export default OutputTray;
