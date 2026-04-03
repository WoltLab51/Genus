interface Event {
  type: string;
  payload: unknown;
  timestamp: string;
}

const EVENT_COLORS: Record<string, string> = {
  "data.collected": "text-blue-400",
  "data.analyzed": "text-purple-400",
  "decision.made": "text-green-400",
};

export default function DataFlowPanel({ events }: { events: Event[] }) {
  const flowEvents = events.filter((e) =>
    ["data.collected", "data.analyzed", "decision.made"].includes(e.type)
  );

  return (
    <div className="bg-gray-800 border border-gray-700 rounded-xl p-5">
      <h2 className="text-lg font-semibold text-gray-300 mb-4">Data Flow</h2>
      {flowEvents.length === 0 ? (
        <p className="text-gray-500 text-sm text-center py-8">
          No data flow events yet. Run the pipeline to see activity.
        </p>
      ) : (
        <div className="space-y-2 max-h-64 overflow-y-auto">
          {[...flowEvents].reverse().map((event, i) => (
            <div key={`${event.type}-${event.timestamp}-${i}`} className="flex items-start gap-3 text-sm">
              <span className="text-gray-500 font-mono text-xs shrink-0 pt-0.5">
                {new Date(event.timestamp).toLocaleTimeString()}
              </span>
              <span className={`font-medium ${EVENT_COLORS[event.type] ?? "text-gray-400"}`}>
                {event.type}
              </span>
            </div>
          ))}
        </div>
      )}
      {flowEvents.length > 0 && (
        <div className="mt-4 pt-4 border-t border-gray-700">
          <div className="flex justify-between text-xs text-gray-500">
            <span>📡 Collected → 🔬 Analyzed → 🎯 Decided</span>
            <span>{flowEvents.length} events</span>
          </div>
        </div>
      )}
    </div>
  );
}
