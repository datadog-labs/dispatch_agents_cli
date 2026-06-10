import React from "react";
import { Link, useLocation } from "react-router-dom";
import { ChevronRight } from "lucide-react";

function useBreadcrumbs() {
  const location = useLocation();
  const parts = location.pathname.split('/').filter(Boolean);

  if (parts[0] === 'agents') {
    if (parts[1]) {
      return [
        { label: 'Agents', to: '/agents' },
        { label: decodeURIComponent(parts[1]) },
      ];
    }
    return [{ label: 'Agents' }];
  }
  if (parts[0] === 'topics') {
    if (parts[1]) {
      return [
        { label: 'Topics', to: '/topics' },
        { label: decodeURIComponent(parts[1]) },
      ];
    }
    return [{ label: 'Topics' }];
  }
  if (parts[0] === 'settings') {
    return [{ label: 'LLM Keys' }];
  }
  return [];
}

export function LocalHeader() {
  const breadcrumbs = useBreadcrumbs();

  return (
    <header className="bg-white px-6 py-3 flex items-center border-b border-[var(--color-warm-gray-100)]">
      <div className="flex-1 flex items-center">
        {breadcrumbs.length > 0 && (
          <div className="flex items-center gap-2 text-sm">
            {breadcrumbs.map((crumb, index) => (
              <div key={index} className="flex items-center gap-2">
                {index > 0 && <ChevronRight className="w-3 h-3 text-[var(--color-warm-gray-400)]" />}
                {crumb.to ? (
                  <Link
                    to={crumb.to}
                    className="text-[var(--color-warm-gray-600)] hover:text-[var(--color-warm-gray-900)] font-medium transition-colors duration-200"
                  >
                    {crumb.label}
                  </Link>
                ) : (
                  <span className="text-[var(--color-warm-gray-900)] font-medium">
                    {crumb.label}
                  </span>
                )}
              </div>
            ))}
          </div>
        )}
      </div>

      <div className="flex items-center gap-2">
        <span className="text-sm text-[var(--color-warm-gray-600)] font-medium">
          Local Development
        </span>
      </div>
    </header>
  );
}
