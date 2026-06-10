import React from 'react';
import { Badge } from '@ui/badge';

const GOOD = ['healthy', 'deployed', 'active', 'running'];
const PENDING = ['building', 'pending', 'deploying'];

export function dotColor(status) {
  const n = (status || '').toLowerCase();
  if (GOOD.includes(n)) return 'bg-[var(--color-status-green-500)]';
  if (PENDING.includes(n)) return 'bg-[var(--color-status-yellow-500)]';
  return 'bg-[var(--color-status-red-500)]';
}

export function StatusBadge({ status }) {
  return (
    <div className="flex items-center gap-1.5">
      <div className={`w-2 h-2 rounded-full shrink-0 ${dotColor(status)}`} />
      <Badge variant="outline" className="text-[10px] px-1.5 py-0.5 h-auto uppercase">
        {status || 'unknown'}
      </Badge>
    </div>
  );
}
