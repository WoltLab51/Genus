interface AgentStatus {
  agent_id: string;
  name: string;
  status: string;
  last_active: string | null;
}

const STATUS_STYLES: Record<string, string> = {
  idle: "bg-gray-700 text-gray-300",
  running: "bg-green-700 text-green-100 animate-pulse",
  error: "bg-red-700 text-red-100",
};

const STATUS_DOT: Record<string, string> = {
  idle: "bg-gray-400",
  running: "bg-green-400",
  error: "bg-red-400",
};

const AGENT_ICONS: Record<string, string> = {
  data_collector: "📡",
  analysis: "🔬",
  decision: "🎯",
};

export default function AgentCard({ agent }: { agent: AgentStatus }) {
  const statusStyle = STATUS_STYLES[agent.status] ?? STATUS_STYLES.idle;
  const dotStyle = STATUS_DOT[agent.status] ?? STATUS_DOT.idle;
  const icon = AGENT_ICONS[agent.agent_id] ?? "🤖";

  return (
    <div className="bg-gray-800 border border-gray-700 rounded-xl p-5 flex flex-col gap-3">
      <div className="flex items-center gap-3">
        <span className="text-2xl">{icon}</span>
        <div>
          <h3 className="font-semibold text-white">{agent.name}</h3>
          <p className="text-xs text-gray-400 font-mono">{agent.agent_id}</p>
        </div>
      </div>
      <div className={`flex items-center gap-2 px-3 py-1.5 rounded-full text-sm font-medium w-fit ${statusStyle}`}>
        <span className={`w-2 h-2 rounded-full ${dotStyle}`} />
        {agent.status}
      </div>
      {agent.last_active && (
        <p className="text-xs text-gray-500">
          Last active: {new Date(agent.last_active).toLocaleTimeString()}
        </p>
      )}
    </div>
  );
}
