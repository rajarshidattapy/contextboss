import { api } from "@/lib/api";

export const dynamic = "force-dynamic";

export default async function Overview() {
  let stats, entries;
  let error: string | null = null;
  try {
    [stats, entries] = await Promise.all([api.stats(), api.search("")]);
  } catch (e) {
    error = e instanceof Error ? e.message : String(e);
  }
  if (error || !stats || !entries) {
    return (
      <div className="card">
        <h1>Cannot reach the ContextBoss API</h1>
        <p className="muted">{error}</p>
        <p>Start it with <code>contextboss-api</code> and set
        <code> CONTEXTBOSS_API_URL</code>/<code> CONTEXTBOSS_API_KEY</code>.</p>
      </div>
    );
  }
  const namespaces = Object.keys(stats.namespaces ?? {});
  return (
    <>
      <h1>Overview</h1>
      <div className="grid">
        <div className="card"><div className="stat">{stats.entries}</div>
          <div className="muted">entries</div></div>
        <div className="card"><div className="stat">{stats.total_tokens}</div>
          <div className="muted">tokens tracked</div></div>
        <div className="card"><div className="stat">{namespaces.length}</div>
          <div className="muted">namespaces</div></div>
        <div className="card"><div className="stat">{stats.tiers?.hot ?? 0}</div>
          <div className="muted">hot tier</div></div>
      </div>
      <h2>Namespaces</h2>
      <div className="card">
        <table>
          <thead><tr><th>namespace</th><th>entries</th></tr></thead>
          <tbody>
            {namespaces.map((n) => (
              <tr key={n}><td>{n}</td><td>{stats.namespaces[n]}</td></tr>
            ))}
          </tbody>
        </table>
      </div>
      <h2>Recent entries</h2>
      <div className="card">
        <table>
          <thead><tr><th>content</th><th>tier</th><th>version</th></tr></thead>
          <tbody>
            {entries.slice(0, 10).map((e) => (
              <tr key={e.id}>
                <td><a href={`/entries/${e.id}`}>{e.content.slice(0, 80)}</a></td>
                <td>{e.tier}</td><td>v{e.version}</td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
    </>
  );
}
