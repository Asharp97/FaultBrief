import { redirect } from "next/navigation";
import MarketingHome from "@/components/marketing-home";
import { getSignedInUser } from "@/lib/auth/server";

export const dynamic = "force-dynamic";

export default async function HomePage() {
  if (await getSignedInUser()) redirect("/dashboard");
  return <MarketingHome />;
}
