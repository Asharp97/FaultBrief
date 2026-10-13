import { redirect } from "next/navigation";
import { getSignedInUser } from "@/lib/auth/server";
import { AuthForm } from "@/components/auth-form";

export const dynamic = "force-dynamic";
export default async function SignInPage() {
  if (await getSignedInUser()) redirect("/dashboard");
  return (
    <AuthForm
      mode="sign-in"
      configured={Boolean(process.env.NEON_AUTH_BASE_URL && process.env.NEON_AUTH_COOKIE_SECRET)}
    />
  );
}
