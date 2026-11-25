import { api } from "@/lib/api";
import Link from "next/link";

export const dynamic = "force-dynamic";

export default async function EntryDetail({ params }: { params: { id: string } }) {
  const data = await api.inspect(params.id);
  const { entry, tensions, versions, similar } = data;
  return (
    <>
      <h1>Entry {entry.id.slice(0, 8)}</h1>
      <p className="muted">
        <Link href="/entries">back to entries</Link>
      </p>
      <div className="card">
        <pre>{entry.content}</pre>
        <p className="muted">
          namespace {entry.namespace} | tier {entry.tier} | v{entry.version} |
          importance {entry.importance} {entry.pinned ? "| pinned" : ""}
        </p>
        <p>{entry.tags.map((t) => <span className="tag" key={t}>{t}</span>)}</p>
      </div>
      <h2>Tensions</h2>
      <div className="card">
        {tensions.length === 0 && <p className="muted">No tensions detected.</p>}
        {tensions.map((t, i) => (
          <div className="tension" key={i}>
            <strong>{t.kind}</strong> ({t.severity}): {t.detail}
          </div>
        ))}
      </div>
      <h2>Version history</h2>
      <div className="card">
        <table>
          <thead><tr><th>version</th><th>tokens</th><th>updated</th></tr></thead>
          <tbody>
            {versions.map((v) => (
              <tr key={v.version}>
                <td>v{v.version}</td><td>{v.tokens}</td>
                <td>{new Date(v.updated_at * 1000).toLocaleString()}</td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
      <h2>Similar entries</h2>
      <div className="card">
        {similar.length === 0 && <p className="muted">None found.</p>}
        {similar.map((s) => (
          <p key={s.id}>
            <a href={`/entries/${s.id}`}>{s.content.slice(0, 80)}</a>{" "}
            <span className="muted">score {s.score.toFixed(2)}</span>
          </p>
        ))}
      </div>
      <h2>Compact</h2>
      <form className="inline" action={`/entries/${entry.id}/compact`} method="post">
        <input name="target_tokens" type="number" placeholder="target tokens" required />
        <button type="submit">Compact</button>
      </form>
    </>
  );
}
