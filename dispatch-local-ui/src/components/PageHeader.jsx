import React from 'react';

/**
 * Matches the visual style of web-app/src/components/layout/PageHeader.tsx.
 * The `namespace` prop renders as "· namespace" in warm-gray, identical to
 * how AgentRegistryPage inlines the namespace into its title ReactNode.
 */
export function PageHeader({ title, description, icon: Icon, actions, namespace }) {
  return (
    <div className="space-y-3">
      <div className="flex items-start justify-between gap-4">
        <div className="flex items-center gap-2 min-w-0 flex-1">
          {Icon && (
            <Icon className="h-5 w-5 shrink-0 text-[var(--color-brand-blue-600)]" />
          )}
          <h1 className="font-medium text-2xl text-[var(--color-steel-blue)]">
            {title}
            {namespace && (
              <>
                <span className="text-[var(--color-warm-gray-400)] mx-2">&middot;</span>
                <span className="text-[var(--color-warm-gray-400)]">{namespace}</span>
              </>
            )}
          </h1>
        </div>
        {actions && (
          <div className="flex items-center gap-2 flex-shrink-0">
            {actions}
          </div>
        )}
      </div>
      {description && (
        <div className="text-sm text-[var(--color-steel-blue-light)] max-w-3xl">
          {description}
        </div>
      )}
    </div>
  );
}
