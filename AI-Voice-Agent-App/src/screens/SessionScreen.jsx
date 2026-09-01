import { useEffect, useState } from 'react';

export default function SessionScreen() {
  const [backendStatus, setBackendStatus] = useState(null);
  const [error, setError] = useState(null);

  useEffect(() => {
    let cancelled = false;
    fetch('http://localhost:8000/api/health')
      .then((res) => res.json())
      .then((data) => {
        if (!cancelled) {
          setBackendStatus(data);
        }
      })
      .catch((err) => {
        if (!cancelled) {
          setError(err.message);
        }
      });
    return () => {
      cancelled = true;
    };
  }, []);

  return (
    <div className="p-6">
      <h1 className="text-2xl font-semibold">Session</h1>
      <div className="mt-4 text-sm text-gray-700">
        <p className="font-medium">Backend health check:</p>
        {backendStatus ? (
          <pre className="mt-2 p-3 bg-gray-100 rounded">{JSON.stringify(backendStatus, null, 2)}</pre>
        ) : error ? (
          <p className="mt-2 text-red-600">Error: {error}</p>
        ) : (
          <p className="mt-2 text-gray-500">Loading...</p>
        )}
      </div>
    </div>
  );
}
