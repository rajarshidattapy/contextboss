import { api } from "@/lib/api";
import { redirect } from "next/navigation";

export async function POST(
  request: Request,
  { params }: { params: { id: string } },
) {
  const form = await request.formData();
  const target = Number(form.get("target_tokens"));
  if (Number.isFinite(target) && target > 0) {
    await api.compact(params.id, target);
  }
  redirect(`/entries/${params.id}`);
}
