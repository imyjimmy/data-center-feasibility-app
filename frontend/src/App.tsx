import { useEffect, useState } from "react";

type ApiHealth = {
  status: string;
  service: string;
  version: string;
};

const apiBaseUrl = import.meta.env.VITE_API_BASE_URL ?? "http://localhost:8000";

function App() {
  const [health, setHealth] = useState<ApiHealth | null>(null);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    const controller = new AbortController();

    fetch(`${apiBaseUrl}/health`, { signal: controller.signal })
      .then((response) => {
        if (!response.ok) {
          throw new Error(`Backend returned ${response.status}`);
        }

        return response.json() as Promise<ApiHealth>;
      })
      .then(setHealth)
      .catch((caughtError: unknown) => {
        if (caughtError instanceof DOMException && caughtError.name === "AbortError") {
          return;
        }

        setError(caughtError instanceof Error ? caughtError.message : "Unable to reach backend");
      });

    return () => controller.abort();
  }, []);

  return (
    <main className="app-shell">
      <section className="intro-panel">
        <h1>Data Center Feasibility</h1>
        <p className="lede">
          Is this parcel worth a first utility/fiber diligence call for a 25 MW edge data
          center?
        </p>
        <div className="status-row">
          <span className={health ? "status-dot online" : "status-dot"} />
          <span>
            Backend:{" "}
            {health ? `${health.status} (${health.version})` : error ? error : "checking..."}
          </span>
        </div>
      </section>
    </main>
  );
}

export default App;
