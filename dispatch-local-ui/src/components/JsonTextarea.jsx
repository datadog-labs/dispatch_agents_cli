import React from 'react';

// Shared JSON payload textarea with inline error display.
// Used by AgentFunctionsPanel (invoke tab) and TopicDetailsPage (send tab).
const JsonTextarea = ({ value, onChange, error, disabled, placeholder = '{}' }) => (
  <>
    <textarea
      className={`flex-1 min-h-0 w-full resize-none px-3 py-2 border rounded-md font-mono text-sm focus:outline-none focus:ring-2 focus:ring-blue-500 focus:border-blue-500 ${
        error ? 'border-red-400' : 'border-gray-300'
      } ${disabled ? 'bg-gray-50' : 'bg-white'}`}
      value={value}
      onChange={e => onChange(e.target.value)}
      placeholder={placeholder}
      disabled={disabled}
      spellCheck={false}
    />
    {error && <p className="shrink-0 text-xs text-red-500">{error}</p>}
  </>
);

export default JsonTextarea;
