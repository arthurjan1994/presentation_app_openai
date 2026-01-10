"use client";

import type { TemplateResult } from "@/types";

interface TemplatePreviewProps {
  template: TemplateResult;
  onRemove: () => void;
}

export function TemplatePreview({ template, onRemove }: TemplatePreviewProps) {
  return (
    <div className="border rounded-lg p-3 bg-gray-50">
      <div className="flex items-center justify-between mb-2">
        <h4 className="text-sm font-medium text-gray-700 truncate flex-1 mr-2">
          {template.filename}
        </h4>
        <button
          onClick={onRemove}
          className="text-gray-400 hover:text-red-500 p-1 flex-shrink-0"
          title="Remove template"
        >
          <svg
            className="w-4 h-4"
            fill="none"
            viewBox="0 0 24 24"
            stroke="currentColor"
          >
            <path
              strokeLinecap="round"
              strokeLinejoin="round"
              strokeWidth={2}
              d="M6 18L18 6M6 6l12 12"
            />
          </svg>
        </button>
      </div>

      {/* Screenshot previews - horizontal scroll */}
      {template.screenshots.length > 0 && (
        <div className="flex gap-2 mb-2 overflow-x-auto pb-1">
          {template.screenshots.map((screenshot, idx) => (
            <div
              key={idx}
              className="flex-shrink-0 w-24 aspect-video bg-white border rounded overflow-hidden"
            >
              <img
                src={`data:image/png;base64,${screenshot.data}`}
                alt={`Slide ${screenshot.index + 1}`}
                className="w-full h-full object-cover"
              />
            </div>
          ))}
        </div>
      )}

      <p className="text-xs text-gray-500">
        {template.screenshots.length > 0
          ? `${template.screenshots.length} screenshot${template.screenshots.length !== 1 ? "s" : ""} extracted`
          : "Text content extracted"}
      </p>
    </div>
  );
}
