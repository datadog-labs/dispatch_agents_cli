import React, { useState, useEffect } from "react";
import { toast } from "sonner";
import { Cpu, KeyRound, RefreshCw, Trash2, Shield, MoreHorizontal, Pencil } from "lucide-react";
import { Button } from "@ui/button";
import { Dialog, DialogContent, DialogHeader, DialogTitle } from "@ui/dialog";
import {
  DropdownMenu,
  DropdownMenuTrigger,
  DropdownMenuContent,
  DropdownMenuItem,
  DropdownMenuSeparator,
} from "@ui/dropdown-menu";
import { PageHeader } from "./PageHeader";

const LLMConfigPage = () => {
  const [providers, setProviders] = useState([]);
  const [loading, setLoading] = useState(true);
  const [saving, setSaving] = useState(false);

  // modalProvider: null = closed, string = open for that provider
  const [modalProvider, setModalProvider] = useState(null);
  const [apiKey, setApiKey] = useState("");

  const loadProviders = async () => {
    try {
      const response = await fetch("/api/unstable/llm-config/local");
      if (response.ok) {
        const data = await response.json();
        setProviders(data.providers || []);
      } else {
        toast.error("Failed to load provider configuration");
      }
    } catch (err) {
      console.error("Failed to load LLM config:", err);
      toast.error("Failed to connect to router");
    } finally {
      setLoading(false);
    }
  };

  useEffect(() => { loadProviders(); }, []);

  const handleRefresh = async () => {
    setLoading(true);
    await loadProviders();
  };

  const openModal = (providerName) => {
    setModalProvider(providerName);
    setApiKey("");
  };

  const closeModal = () => {
    setModalProvider(null);
    setApiKey("");
  };

  const handleSaveKey = async (e) => {
    e.preventDefault();
    if (!modalProvider || !apiKey.trim()) return;

    setSaving(true);

    try {
      const response = await fetch("/api/unstable/llm-config/local", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ provider: modalProvider, api_key: apiKey.trim() }),
      });

      if (response.ok) {
        const data = await response.json();
        toast.success(data.message);
        closeModal();
        await loadProviders();
      } else {
        const data = await response.json();
        toast.error(data.detail || "Failed to save API key");
      }
    } catch (err) {
      toast.error("Failed to connect to router");
    } finally {
      setSaving(false);
    }
  };

  const handleRemoveKey = async (provider) => {
    if (!confirm(`Remove API key for ${provider}? This will delete it from your Keychain.`)) return;

    try {
      const response = await fetch(`/api/unstable/llm-config/local/${provider}`, {
        method: "DELETE",
      });

      if (response.ok) {
        const data = await response.json();
        toast.success(data.message);
        await loadProviders();
      } else {
        const data = await response.json();
        toast.error(data.detail || "Failed to remove API key");
      }
    } catch (err) {
      toast.error("Failed to connect to router");
    }
  };

  const modalProviderData = providers.find(p => p.provider === modalProvider);
  const isUpdate = modalProviderData?.configured;

  if (loading && providers.length === 0) {
    return (
      <div className="h-full overflow-y-auto pt-3 px-6 pb-6 space-y-6">
        <PageHeader title="LLM Keys" description="Manage API keys for local LLM providers" icon={Cpu} namespace="local" />
        <div className="bg-white rounded-lg border border-[var(--color-warm-gray-200)] p-8">
          <div className="flex items-center justify-center">
            <div className="animate-spin rounded-full h-8 w-8 border-b-2 border-blue-500"></div>
            <span className="ml-3 text-gray-600">Loading provider configuration...</span>
          </div>
        </div>
      </div>
    );
  }

  return (
    <div className="h-full overflow-y-auto pt-3 px-6 pb-6 space-y-6">
      <PageHeader
        title="LLM Keys"
        description="Manage API keys for calling LLMs from local agents"
        icon={Cpu}
        actions={
          <Button onClick={handleRefresh} disabled={loading} variant="outline" className="flex items-center gap-2">
            <RefreshCw className={`w-4 h-4 ${loading ? "animate-spin" : ""}`} />
            Refresh
          </Button>
        }
      />

      {/* Info Banner */}
      <div className="flex items-start gap-3 p-4 bg-blue-50 border border-blue-200 rounded-lg">
        <Shield className="w-5 h-5 text-blue-600 mt-0.5 flex-shrink-0" />
        <div className="text-sm text-blue-800">
          <span className="font-medium">Local Development Only</span> &mdash; API keys are stored
          securely in your macOS Keychain. Changes take effect immediately without restarting the
          router.
        </div>
      </div>

      {/* Providers Table */}
      <div className="bg-white rounded-lg border border-[var(--color-warm-gray-200)] overflow-hidden">
        <table className="min-w-full divide-y divide-gray-200">
          <thead className="bg-gray-50">
            <tr>
              <th className="px-6 py-3 text-left text-xs font-medium text-gray-500 uppercase tracking-wider">
                Provider
              </th>
              <th className="px-6 py-3 text-left text-xs font-medium text-gray-500 uppercase tracking-wider">
                Status
              </th>
              <th className="px-6 py-3 text-left text-xs font-medium text-gray-500 uppercase tracking-wider">
                Storage
              </th>
              <th className="px-6 py-3 text-left text-xs font-medium text-gray-500 uppercase tracking-wider">
                Environment Variable
              </th>
              <th className="px-6 py-3 text-right text-xs font-medium text-gray-500 uppercase tracking-wider">
                Actions
              </th>
            </tr>
          </thead>
          <tbody className="bg-white divide-y divide-gray-200">
            {providers.map((provider) => (
              <tr key={provider.provider} className="hover:bg-gray-50 transition-colors duration-150">
                <td className="px-6 py-4 whitespace-nowrap">
                  <div className="flex items-center">
                    <KeyRound
                      className={`w-4 h-4 mr-3 ${
                        provider.configured ? "text-[var(--color-brand-blue-500)]" : "text-gray-300"
                      }`}
                    />
                    <span className="text-sm font-medium text-gray-900">
                      {provider.provider.charAt(0).toUpperCase() + provider.provider.slice(1)}
                    </span>
                  </div>
                </td>
                <td className="px-6 py-4 whitespace-nowrap">
                  {provider.configured ? (
                    <span className="inline-flex items-center gap-1.5 px-2.5 py-0.5 text-xs font-medium rounded-full bg-green-100 text-green-800">
                      <span className="w-1.5 h-1.5 rounded-full bg-green-500"></span>
                      Configured
                    </span>
                  ) : (
                    <span className="inline-flex items-center gap-1.5 px-2.5 py-0.5 text-xs font-medium rounded-full bg-gray-100 text-gray-600">
                      <span className="w-1.5 h-1.5 rounded-full bg-gray-400"></span>
                      Not configured
                    </span>
                  )}
                </td>
                <td className="px-6 py-4 whitespace-nowrap">
                  <span className="text-sm text-gray-500">
                    {provider.storage_type || (provider.configured ? "unknown" : "—")}
                  </span>
                </td>
                <td className="px-6 py-4 whitespace-nowrap">
                  <code className="text-xs text-gray-500 bg-gray-100 px-1.5 py-0.5 rounded">
                    {provider.env_var}
                  </code>
                </td>
                <td className="px-6 py-4 whitespace-nowrap text-right">
                  {provider.configured ? (
                    <DropdownMenu>
                      <DropdownMenuTrigger asChild>
                        <button className="p-1 rounded hover:bg-gray-100 text-gray-400 hover:text-gray-600 transition-colors">
                          <MoreHorizontal className="w-4 h-4" />
                        </button>
                      </DropdownMenuTrigger>
                      <DropdownMenuContent align="end">
                        <DropdownMenuItem onClick={() => openModal(provider.provider)}>
                          <Pencil className="w-3.5 h-3.5 mr-2" />
                          Update key
                        </DropdownMenuItem>
                        <DropdownMenuSeparator />
                        <DropdownMenuItem
                          onClick={() => handleRemoveKey(provider.provider)}
                          className="text-red-600 focus:text-red-600"
                        >
                          <Trash2 className="w-3.5 h-3.5 mr-2" />
                          Remove key
                        </DropdownMenuItem>
                      </DropdownMenuContent>
                    </DropdownMenu>
                  ) : (
                    <button
                      onClick={() => openModal(provider.provider)}
                      className="text-xs text-blue-600 hover:text-blue-800 font-medium"
                    >
                      Set
                    </button>
                  )}
                </td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>

      {/* Set / Update key modal */}
      <Dialog open={!!modalProvider} onOpenChange={(open) => { if (!open) closeModal(); }}>
        <DialogContent className="sm:max-w-md">
          <DialogHeader>
            <DialogTitle>
              {isUpdate ? "Update API Key" : "Set API Key"} &mdash;{" "}
              <span className="font-mono text-[var(--color-steel-blue)]">
                {modalProvider?.charAt(0).toUpperCase()}{modalProvider?.slice(1)}
              </span>
            </DialogTitle>
          </DialogHeader>
          <form onSubmit={handleSaveKey} className="space-y-4 pt-1">
            <div>
              <label className="block text-xs font-medium text-gray-600 mb-1.5">
                API Key
              </label>
              <input
                type="password"
                value={apiKey}
                onChange={(e) => setApiKey(e.target.value)}
                placeholder={`Enter ${modalProvider} API key...`}
                className="block w-full rounded-md border border-gray-300 px-3 py-2 text-sm focus:border-blue-500 focus:ring-1 focus:ring-blue-500"
                autoFocus
              />
              {modalProviderData?.env_var && (
                <p className="mt-1.5 text-xs text-gray-400">
                  Stored as <code className="bg-gray-100 px-1 py-0.5 rounded">{modalProviderData.env_var}</code>
                </p>
              )}
            </div>
            <div className="flex justify-end gap-2">
              <Button type="button" variant="outline" onClick={closeModal}>
                Cancel
              </Button>
              <Button type="submit" disabled={!apiKey.trim() || saving}>
                {saving ? "Saving…" : "Save"}
              </Button>
            </div>
          </form>
        </DialogContent>
      </Dialog>
    </div>
  );
};

export default LLMConfigPage;
