import { api } from "@/lib/api";

export const dynamic = "force-dynamic";

export default async function Entries({
  searchParams,
}: {
  searchParams: { q?: string; namespace?: string };
}) {
  const q = searchParams.q ?? "";
  const entries = await api.search(q, searchParams.namespace || undefined);
  return (
    <>
      <h1>Entries</h1>
      <form className="inline" method="get">
        <input name="q" placeholder="search..." defaultValue={q} />
        <input name="namespace" placeholder="namespace"
          defaultValue={searchParams.namespace ?? ""} />
        <button type="submit">Search</button>
      </form>
      <div className="card">
        <table>
          <thead>
            <tr><th>content</th><th>namespace</th><th>tags</th><th>tier</th>
              <th>pinned</th><th>v</th></tr>
          </thead>
          <tbody>
            {entries.map((e) => (
              <tr key={e.id}>
                <td><a href={`/entries/${e.id}`}>{e.content.slice(0, 70)}</a></td>
                <td>{e.namespace}</td>
                <td>{e.tags.map((t) => <span className="tag" key={t}>{t}</span>)}</td>
                <td>{e.tier}</td>
                <td>{e.pinned ? "yes" : ""}</td>
                <td>{e.version}</td>
              </tr>
            ))}
          </tbody>
        </table>
        {entries.length === 0 && <p className="muted">No entries match.</p>}
      </div>
    </>
  );
}
