"use client";

import { useState, useCallback } from "react";
import { parseTemplate } from "@/lib/api";
import type { TemplateResult } from "@/types";

interface TemplateUploadProps {
  userSessionId: string;
  onTemplateProcessed: (result: TemplateResult) => void;
  apiKey?: string;
}

export function TemplateUpload({
  userSessionId,
  onTemplateProcessed,
  apiKey,
}: TemplateUploadProps) {
  const [isDragging, setIsDragging] = useState(false);
  const [isProcessing, setIsProcessing] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const handleFile = useCallback(
    async (file: File) => {
      setIsProcessing(true);
      setError(null);

      try {
        const result = await parseTemplate(file, userSessionId, apiKey);

        if (!result.success) {
          throw new Error(result.error || "Template parsing failed");
        }

        onTemplateProcessed(result as TemplateResult);
      } catch (err) {
        setError(err instanceof Error ? err.message : "Unknown error");
      } finally {
        setIsProcessing(false);
      }
    },
    [userSessionId, onTemplateProcessed, apiKey]
  );

  const handleDrop = useCallback(
    (e: React.DragEvent) => {
      e.preventDefault();
      setIsDragging(false);
      const file = e.dataTransfer.files[0];
      if (file) handleFile(file);
    },
    [handleFile]
  );

  const handleFileSelect = useCallback(
    (e: React.ChangeEvent<HTMLInputElement>) => {
      const file = e.target.files?.[0];
      if (file) handleFile(file);
    },
    [handleFile]
  );

  return (
    <div className="space-y-2">
      <div className="flex items-center justify-between">
        <h4 className="text-sm font-medium text-gray-700">Style Template</h4>
      </div>
      <p className="text-xs text-gray-500">
        Upload a presentation (PPTX, PDF) to extract style references
      </p>

      <div
        onDragOver={(e) => {
          e.preventDefault();
          setIsDragging(true);
        }}
        onDragLeave={() => setIsDragging(false)}
        onDrop={handleDrop}
        className={`border-2 border-dashed rounded-lg p-4 text-center transition-colors cursor-pointer ${
          isDragging
            ? "border-blue-500 bg-blue-50"
            : "border-gray-300 hover:border-gray-400"
        } ${isProcessing ? "opacity-50 pointer-events-none" : ""}`}
      >
        {isProcessing ? (
          <div className="flex items-center justify-center gap-2 text-sm text-gray-600">
            <div className="w-4 h-4 border-2 border-blue-500 border-t-transparent rounded-full animate-spin" />
            Extracting template...
          </div>
        ) : (
          <label className="cursor-pointer block">
            <span className="text-sm text-gray-600">
              Drop template or{" "}
              <span className="text-blue-600 hover:text-blue-700">browse</span>
            </span>
            <input
              type="file"
              accept=".pptx,.ppt,.pdf"
              onChange={handleFileSelect}
              className="hidden"
            />
          </label>
        )}
      </div>

      {error && <p className="text-xs text-red-500">{error}</p>}
    </div>
  );
}
