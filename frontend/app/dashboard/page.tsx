import { redirect } from "next/navigation";
import { getAuth } from "@/lib/auth/server";
import { WorkspaceHome } from "@/components/workspace-home";

export const dynamic = "force-dynamic";
export default async function DashboardPage() {
  const auth = getAuth();
  if (!auth) redirect("/auth/sign-in");
  const session = await auth.getSession();
  if (!session.data?.user) redirect("/auth/sign-in");
  return <WorkspaceHome name={session.data.user.name} email={session.data.user.email} />;
}
