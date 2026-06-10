import React from 'react';
import { NavLink } from 'react-router-dom';
import { Waypoints, Radio, Cpu, BookOpenText, Globe } from 'lucide-react';
import { HeaderLogo } from '@ui/header-logo';

const NAV_ITEM_BASE =
  "flex items-center px-3 py-1.5 text-sm font-normal rounded-md transition-all duration-200 ease-out w-full hover:cursor-pointer";
const NAV_ITEM_ACTIVE =
  "bg-[rgba(191,219,254,0.4)] text-[var(--color-brand-blue-800)]";
const NAV_ITEM_INACTIVE =
  "text-[var(--sidebar-text)] hover:text-[var(--color-brand-blue-700)] hover:bg-white/20";

function SidebarLink({ to, icon: Icon, label }) {
  return (
    <NavLink
      to={to}
      className={({ isActive }) => `${NAV_ITEM_BASE} ${isActive ? NAV_ITEM_ACTIVE : NAV_ITEM_INACTIVE}`}
    >
      <Icon className="w-4 h-4 mr-3" />
      {label}
    </NavLink>
  );
}

function SectionLabel({ children }) {
  return (
    <p className="text-[10px] uppercase font-normal tracking-wider text-[var(--sidebar-text-muted)] opacity-60 px-2 pt-2 pb-0.5">
      {children}
    </p>
  );
}

export function LocalSidebar() {
  return (
    <div
      className="flex flex-col flex-shrink-0 transition-all duration-300 ease-out"
      style={{
        width: '244px',
        background: '#f3f7fe',
        borderRight: '1px solid #dfe8f1',
        '--sidebar-text': '#1c2e48',
        '--sidebar-text-muted': '#677c97',
        '--sidebar-card-bg': 'rgba(255, 255, 255, 0.68)',
      }}
    >
      {/* Logo section */}
      <div className="flex items-center gap-3 px-5 pt-4 pb-2 flex-shrink-0">
        <HeaderLogo height={28} />
        <div className="flex items-center gap-1 px-2 py-0.5 rounded-full bg-gradient-to-r from-yellow-100 to-amber-100 border border-yellow-300">
          <div className="w-1.5 h-1.5 rounded-full bg-gradient-to-r from-yellow-500 to-amber-500" />
          <span className="text-xs text-yellow-800 font-semibold uppercase tracking-wider">LOCAL</span>
        </div>
      </div>

      <div className="flex-1 flex flex-col pt-1 overflow-y-auto">
        <nav className="mt-1 flex flex-col flex-1 px-3 space-y-0.5">
          <SectionLabel>Local</SectionLabel>

          <SidebarLink to="/agents" icon={Waypoints} label="Agents" />
          <SidebarLink to="/topics" icon={Radio} label="Topics" />

          <SectionLabel>Config</SectionLabel>
          <SidebarLink to="/settings/llm-keys" icon={Cpu} label="LLM Keys" />

          <div className="flex-1" />

          <div className="space-y-0.5 pb-2">
            <SectionLabel>Links</SectionLabel>
            <a
              href="https://dispatchagents.ai/docs/intro"
              target="_blank"
              rel="noopener noreferrer"
              className={`${NAV_ITEM_BASE} ${NAV_ITEM_INACTIVE}`}
            >
              <BookOpenText className="w-4 h-4 mr-3" />
              Documentation
            </a>
            <a
              href="https://dispatchagents.ai/"
              target="_blank"
              rel="noopener noreferrer"
              className={`${NAV_ITEM_BASE} ${NAV_ITEM_INACTIVE}`}
            >
              <Globe className="w-4 h-4 mr-3" />
              View web app
            </a>
          </div>
        </nav>
      </div>
    </div>
  );
}
