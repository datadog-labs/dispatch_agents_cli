import React from 'react';

const BADGE_BG = {
  gray: '#9ca3af',
  amber: '#f59e0b',
};

// Shared tab bar used by AgentFunctionsPanel, TopicDetailsPage, and OutputTray.
//
// tabs: [{ key, label, badge?, badgeColor?: 'gray'|'amber' }]
// activeTab: the currently active key, or null (all tabs render as inactive)
// onChange: (key) => void
const TabBar = ({ tabs, activeTab, onChange, className = '' }) => (
  <div className={`shrink-0 flex items-stretch ${className}`}>
    {tabs.map(({ key, label, badge, badgeColor = 'gray' }) => (
      <button
        key={key}
        onClick={() => onChange(key)}
        className={`px-4 py-2.5 text-sm font-medium transition-all ${
          activeTab === key
            ? 'border-b-2 border-[var(--color-aqua-600)] text-gray-900 -mb-px'
            : 'text-[#677c97] hover:text-gray-700'
        }`}
      >
        {badge > 0 ? (
          <span className="flex items-center gap-1.5">
            {label}
            <span
              className="text-[9px] font-bold rounded-full w-4 h-4 inline-flex items-center justify-center text-white shrink-0"
              style={{ background: BADGE_BG[badgeColor] ?? BADGE_BG.gray }}
            >
              {badge > 99 ? '99+' : badge}
            </span>
          </span>
        ) : label}
      </button>
    ))}
  </div>
);

export default TabBar;
