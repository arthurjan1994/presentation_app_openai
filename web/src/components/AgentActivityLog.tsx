"use client";

import { useState } from "react";
import type { AgentLogEntry } from "@/types";

interface AgentActivityLogProps {
  log: AgentLogEntry[];
  isStreaming: boolean;
  summary?: string;
}

// Icon components for different entry types
function StatusIcon() {
  return (
    <svg className="w-4 h-4 text-gray-500" fill="none" viewBox="0 0 24 24" stroke="currentColor">
      <circle cx="12" cy="12" r="10" strokeWidth={2} />
      <path strokeLinecap="round" strokeWidth={2} d="M12 6v6l4 2" />
    </svg>
  );
}

function ToolIcon() {
  return (
    <svg className="w-4 h-4 text-blue-600" fill="none" viewBox="0 0 24 24" stroke="currentColor">
      <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M10.325 4.317c.426-1.756 2.924-1.756 3.35 0a1.724 1.724 0 002.573 1.066c1.543-.94 3.31.826 2.37 2.37a1.724 1.724 0 001.065 2.572c1.756.426 1.756 2.924 0 3.35a1.724 1.724 0 00-1.066 2.573c.94 1.543-.826 3.31-2.37 2.37a1.724 1.724 0 00-2.572 1.065c-.426 1.756-2.924 1.756-3.35 0a1.724 1.724 0 00-2.573-1.066c-1.543.94-3.31-.826-2.37-2.37a1.724 1.724 0 00-1.065-2.572c-1.756-.426-1.756-2.924 0-3.35a1.724 1.724 0 001.066-2.573c-.94-1.543.826-3.31 2.37-2.37.996.608 2.296.07 2.572-1.065z" />
      <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M15 12a3 3 0 11-6 0 3 3 0 016 0z" />
    </svg>
  );
}

function ThinkingIcon() {
  return (
    <svg className="w-4 h-4 text-purple-500" fill="none" viewBox="0 0 24 24" stroke="currentColor">
      <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M9.663 17h4.673M12 3v1m6.364 1.636l-.707.707M21 12h-1M4 12H3m3.343-5.657l-.707-.707m2.828 9.9a5 5 0 117.072 0l-.548.547A3.374 3.374 0 0014 18.469V19a2 2 0 11-4 0v-.531c0-.895-.356-1.754-.988-2.386l-.548-.547z" />
    </svg>
  );
}

function InitIcon() {
  return (
    <svg className="w-4 h-4 text-green-500" fill="none" viewBox="0 0 24 24" stroke="currentColor">
      <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M13 10V3L4 14h7v7l9-11h-7z" />
    </svg>
  );
}

function getEntryDescription(entry: AgentLogEntry): string {
  // Use content field if available (new pattern)
  if (entry.content) {
    return entry.content;
  }
  // Fallback to old pattern
  if (entry.type === "tool_use" && entry.toolName) {
    const toolName = entry.toolName.replace(/_/g, " ");
    return toolName.charAt(0).toUpperCase() + toolName.slice(1);
  }
  if (entry.type === "thinking") {
    return "Agent thinking...";
  }
  return entry.message || "Processing...";
}

function getEntryIcon(entry: AgentLogEntry) {
  switch (entry.type) {
    case "tool_use":
      return <ToolIcon />;
    case "thinking":
      return <ThinkingIcon />;
    case "init":
      return <InitIcon />;
    default:
      return <StatusIcon />;
  }
}

export function AgentActivityLog({
  log,
  isStreaming,
  summary,
}: AgentActivityLogProps) {
  const [isExpanded, setIsExpanded] = useState(false);

  if (log.length === 0) return null;

  const lastEntry = log[log.length - 1];
  const latestStatus = getEntryDescription(lastEntry);

  return (
    <div className="mt-3 bg-gray-50 rounded-lg overflow-hidden">
      {/* Header - always visible */}
      <button
        onClick={() => setIsExpanded(!isExpanded)}
        className="w-full flex items-center justify-between p-3 hover:bg-gray-100 transition-colors"
      >
        <div className="flex items-center gap-3">
          {/* Activity indicator */}
          {isStreaming ? (
            <div className="w-5 h-5 border-2 border-blue-500 border-t-transparent rounded-full animate-spin" />
          ) : (
            <div className="w-5 h-5 bg-green-500 rounded-full flex items-center justify-center">
              <svg className="w-3 h-3 text-white" fill="none" viewBox="0 0 24 24" stroke="currentColor">
                <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={3} d="M5 13l4 4L19 7" />
              </svg>
            </div>
          )}

          {/* Status text */}
          <span className="text-sm text-gray-700">
            {isStreaming ? latestStatus : (summary || "Completed")}
          </span>
        </div>

        <div className="flex items-center gap-3">
          {/* Step count */}
          <span className="text-xs text-gray-500 bg-gray-200 px-2 py-0.5 rounded-full">
            {log.length} steps
          </span>

          {/* Expand/collapse chevron */}
          <svg
            className={`w-4 h-4 text-gray-400 transition-transform ${isExpanded ? "rotate-180" : ""}`}
            fill="none"
            viewBox="0 0 24 24"
            stroke="currentColor"
          >
            <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M19 9l-7 7-7-7" />
          </svg>
        </div>
      </button>

      {/* Expanded log entries */}
      {isExpanded && (
        <div className="border-t border-gray-200 max-h-96 overflow-y-auto">
          {log.map((entry, idx) => (
            <div
              key={idx}
              className="flex items-start gap-3 px-3 py-2 hover:bg-gray-100 border-b border-gray-100 last:border-b-0"
            >
              {/* Icon */}
              <div className="mt-0.5 flex-shrink-0">
                {getEntryIcon(entry)}
              </div>

              {/* Content */}
              <div className="flex-1 min-w-0">
                <div className="flex items-center justify-between gap-2">
                  <span className={`text-sm ${entry.type === "tool_use" ? "text-blue-600 font-medium" : "text-gray-700"}`}>
                    {getEntryDescription(entry)}
                  </span>
                  <span className="text-xs text-gray-400 flex-shrink-0">
                    {entry.timestamp.toLocaleTimeString()}
                  </span>
                </div>

                {/* Details - show full slide content */}
                {entry.details && (
                  <div className="text-xs text-gray-600 mt-1.5 whitespace-pre-wrap bg-gray-100 rounded p-2 max-h-32 overflow-y-auto">
                    {entry.details}
                  </div>
                )}
                {entry.type === "thinking" && entry.thinkingSnippet && (
                  <div className="text-xs text-gray-500 mt-0.5 italic truncate">
                    {entry.thinkingSnippet}
                  </div>
                )}
              </div>

              {/* Step number */}
              <span className="text-xs text-gray-400 flex-shrink-0">
                #{idx + 1}
              </span>
            </div>
          ))}
        </div>
      )}
    </div>
  );
}
