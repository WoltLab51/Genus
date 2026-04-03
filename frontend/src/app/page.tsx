"use client";

import { useEffect, useState, useCallback } from "react";
import AgentCard from "@/components/AgentCard";
import DataFlowPanel from "@/components/DataFlowPanel";
import LogViewer from "@/components/LogViewer";

const API_URL = process.env.NEXT_PUBLIC_API_URL ?? "http://localhost:8000";

interface AgentStatus {
  agent_id: string;
  name: string;
  status: string;
  last_active: string | null;
}

interface SystemStatus {
  system: string;
  agents: AgentStatus[];
}

interface Event {
  type: string;
  payload: unknown;
  timestamp: string;
}

export default function Home() {
  const [systemStatus, setSystemStatus] = useState<SystemStatus | null>(null);
  const [events, setEvents] = useState<Event[]>([]);
  const [running, setRunning] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const fetchStatus = useCallback(async () => {
    try {
      const [statusRes, eventsRes] = await Promise.all([
        fetch(`${API_URL}/system/status`),
        fetch(`${API_URL}/system/events?limit=20`),
      ]);
      if (statusRes.ok) setSystemStatus(await statusRes.json());
      if (eventsRes.ok) {
        const data = await eventsRes.json();
        setEvents(data.events ?? []);
      }
      setError(null);
    } catch {
      setError("Cannot connect to GENUS backend. Is it running?");
    }
  }, []);

  useEffect(() => {
    fetchStatus();
    const interval = setInterval(fetchStatus, 5000);
    return () => clearInterval(interval);
  }, [fetchStatus]);

  const runPipeline = async () => {
    setRunning(true);
    try {
      await fetch(`${API_URL}/system/pipeline/run`, { method: "POST" });
      setTimeout(fetchStatus, 500);
    } catch {
      setError("Failed to run pipeline.");
    } finally {
      setRunning(false);
    }
  };

  return (
    <main className="max-w-6xl mx-auto p-6 space-y-6">
      <div className="flex items-center justify-between">
        <div>
          <h1 className="text-3xl font-bold text-indigo-400">GENUS</h1>
          <p className="text-gray-400 text-sm mt-1">Modular AI Multi-Agent System</p>
        </div>
        <button
          onClick={runPipeline}
          disabled={running}
          className="px-5 py-2.5 bg-indigo-600 hover:bg-indigo-500 disabled:bg-indigo-800 disabled:cursor-not-allowed rounded-lg font-medium transition-colors"
        >
          {running ? "Running..." : "▶ Run Pipeline"}
        </button>
      </div>

      {error && (
        <div className="bg-red-900/40 border border-red-700 rounded-lg p-4 text-red-300">
          {error}
        </div>
      )}

      <section>
        <h2 className="text-lg font-semibold text-gray-300 mb-3">Agent Status</h2>
        <div className="grid grid-cols-1 md:grid-cols-3 gap-4">
          {systemStatus?.agents.map((agent) => (
            <AgentCard key={agent.agent_id} agent={agent} />
          )) ?? [1, 2, 3].map((i) => (
            <div key={i} className="bg-gray-800 rounded-lg p-4 animate-pulse h-28" />
          ))}
        </div>
      </section>

      <div className="grid grid-cols-1 lg:grid-cols-2 gap-6">
        <DataFlowPanel events={events} />
        <LogViewer events={events} />
      </div>
    </main>
  );
}
