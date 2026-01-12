'use client';

import { useState, useEffect } from 'react';
import { validateApiKey } from '@/lib/api';

const API_KEY_STORAGE_KEY = 'llama-cloud-api-key';

interface ApiKeyGateProps {
  children: React.ReactNode;
  onApiKeyValidated: (apiKey: string) => void;
}

export default function ApiKeyGate({ children, onApiKeyValidated }: ApiKeyGateProps) {
  const [apiKey, setApiKey] = useState('');
  const [isValidating, setIsValidating] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [isValidated, setIsValidated] = useState(false);
  const [isCheckingStored, setIsCheckingStored] = useState(true);

  // Check for stored API key on mount
  useEffect(() => {
    const storedKey = localStorage.getItem(API_KEY_STORAGE_KEY);
    if (storedKey) {
      // Validate the stored key
      setIsValidating(true);
      validateApiKey(storedKey)
        .then(() => {
          setIsValidated(true);
          onApiKeyValidated(storedKey);
        })
        .catch(() => {
          // Stored key is invalid, clear it
          localStorage.removeItem(API_KEY_STORAGE_KEY);
        })
        .finally(() => {
          setIsCheckingStored(false);
          setIsValidating(false);
        });
    } else {
      setIsCheckingStored(false);
    }
  }, [onApiKeyValidated]);

  const handleSubmit = async (e: React.FormEvent) => {
    e.preventDefault();

    if (!apiKey.trim()) {
      setError('Please enter an API key');
      return;
    }

    setIsValidating(true);
    setError(null);

    try {
      await validateApiKey(apiKey.trim());
      // Store the key
      localStorage.setItem(API_KEY_STORAGE_KEY, apiKey.trim());
      setIsValidated(true);
      onApiKeyValidated(apiKey.trim());
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Failed to validate API key');
    } finally {
      setIsValidating(false);
    }
  };

  // Show loading while checking stored key
  if (isCheckingStored) {
    return (
      <div className="min-h-screen flex items-center justify-center bg-gray-50">
        <div className="flex items-center gap-3 text-gray-500">
          <div className="w-5 h-5 border-2 border-gray-400 border-t-transparent rounded-full animate-spin" />
          <span>Loading...</span>
        </div>
      </div>
    );
  }

  // Show main app if validated
  if (isValidated) {
    return <>{children}</>;
  }

  // Show API key entry form
  return (
    <div className="min-h-screen flex items-center justify-center bg-gray-50 p-4">
      <div className="w-full max-w-md">
        {/* Header */}
        <div className="text-center mb-8">
          <div className="w-16 h-16 rounded-2xl bg-blue-600 flex items-center justify-center mx-auto mb-4">
            <svg className="w-8 h-8 text-white" fill="none" viewBox="0 0 24 24" stroke="currentColor">
              <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M7 12l3-3 3 3 4-4M8 21l4-4 4 4M3 4h18M4 4h16v12a1 1 0 01-1 1H5a1 1 0 01-1-1V4z" />
            </svg>
          </div>
          <h1 className="text-2xl font-bold text-gray-900">AI Presentation Generator</h1>
          <p className="text-gray-500 mt-2">Create beautiful presentations with AI</p>
        </div>

        {/* API Key Form */}
        <div className="bg-white rounded-xl p-6 border border-gray-200 shadow-sm">
          <h2 className="text-lg font-semibold text-gray-900 mb-2">Enter Your API Key</h2>
          <p className="text-sm text-gray-500 mb-6">
            This app requires a LlamaCloud API key for document parsing. Your key is stored locally in your browser.
          </p>

          <form onSubmit={handleSubmit} className="space-y-4">
            <div>
              <label htmlFor="apiKey" className="block text-sm font-medium text-gray-700 mb-2">
                LlamaCloud API Key
              </label>
              <input
                id="apiKey"
                type="password"
                value={apiKey}
                onChange={(e) => setApiKey(e.target.value)}
                placeholder="llx-..."
                disabled={isValidating}
                className="w-full px-4 py-3 rounded-lg bg-gray-50 border border-gray-300 text-gray-900 placeholder:text-gray-400 focus:outline-none focus:ring-2 focus:ring-blue-500 focus:border-blue-500 disabled:opacity-50"
              />
            </div>

            {error && (
              <div className="px-4 py-3 rounded-lg bg-red-50 border border-red-200 text-red-700 text-sm">
                {error}
              </div>
            )}

            <button
              type="submit"
              disabled={isValidating || !apiKey.trim()}
              className="w-full px-4 py-3 rounded-lg bg-blue-600 text-white font-medium hover:bg-blue-700 disabled:opacity-50 disabled:cursor-not-allowed transition-colors flex items-center justify-center gap-2"
            >
              {isValidating ? (
                <>
                  <div className="w-4 h-4 border-2 border-white border-t-transparent rounded-full animate-spin" />
                  Validating...
                </>
              ) : (
                'Continue'
              )}
            </button>
          </form>

          <div className="mt-6 pt-6 border-t border-gray-200 space-y-2">
            <p className="text-xs text-gray-500 text-center">
              Don&apos;t have an API key?{' '}
              <a
                href="https://cloud.llamaindex.ai/"
                target="_blank"
                rel="noopener noreferrer"
                className="text-blue-600 hover:underline font-medium"
              >
                Sign up for LlamaCloud
              </a>
            </p>
          </div>
        </div>
      </div>
    </div>
  );
}

// Export helper to get stored API key
export function getStoredApiKey(): string | null {
  if (typeof window === 'undefined') return null;
  return localStorage.getItem(API_KEY_STORAGE_KEY);
}

// Export helper to clear stored API key
export function clearStoredApiKey(): void {
  if (typeof window === 'undefined') return;
  localStorage.removeItem(API_KEY_STORAGE_KEY);
}
