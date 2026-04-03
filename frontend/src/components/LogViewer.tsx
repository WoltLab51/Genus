interface Event {
  type: string;
  payload: unknown;
  timestamp: string;
}

export default function LogViewer({ events }: { events: Event[] }) {
  return (
    <div className="bg-gray-800 border border-gray-700 rounded-xl p-5">
      <h2 className="text-lg font-semibold text-gray-300 mb-4">Event Log</h2>
      {events.length === 0 ? (
        <p className="text-gray-500 text-sm text-center py-8">No events yet.</p>
      ) : (
        <div className="space-y-1.5 max-h-64 overflow-y-auto font-mono text-xs">
          {[...events].reverse().map((event, i) => (
            <div key={`${event.type}-${event.timestamp}-${i}`} className="flex gap-2 text-gray-400">
              <span className="text-gray-600 shrink-0">
                {new Date(event.timestamp).toLocaleTimeString()}
              </span>
              <span className="text-indigo-400">[{event.type}]</span>
              <span className="truncate text-gray-300">
                {JSON.stringify(event.payload).slice(0, 80)}
              </span>
            </div>
          ))}
        </div>
      )}
    </div>
  );
}
