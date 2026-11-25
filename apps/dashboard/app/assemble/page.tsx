import { api } from "@/lib/api";

export const dynamic = "force-dynamic";

export default async function Assemble({
  searchParams,
}: {
  searchParams: { query?: string; budget?: string; system?: string; task?: string };
}) {
  let result = null;
  let error: string | null = null;
  if (searchParams.query) {
    try {
      result = await api.assemble({
        query: searchParams.query,
        budget: searchParams.budget ? Number(searchParams.budget) : undefined,
        system: searchParams.system || undefined,
        task: searchParams.task || undefined,
      });
    } catch (e) {
      error = e instanceof Error ? e.message : String(e);
    }
  }
  return (
    <>
      <h1>Assemble playground</h1>
      <form className="inline" method="get">
        <input name="query" placeholder="query" defaultValue={searchParams.query ?? ""}
          required style={{ minWidth: "260px" }} />
        <input name="budget" type="number" placeholder="budget tokens"
          defaultValue={searchParams.budget ?? ""} />
        <input name="system" placeholder="system prompt"
          defaultValue={searchParams.system ?? ""} />
        <input name="task" placeholder="task"
          defaultValue={searchParams.task ?? ""} />
        <button type="submit">Assemble</button>
      </form>
      {error && <div className="card"><p className="tension">{error}</p></div>}
      {result && (
        <>
          <p className="muted">
            {result.tokens} tokens from {result.entries.length} entries
          </p>
          <pre>{result.text}</pre>
        </>
      )}
    </>
  );
}
