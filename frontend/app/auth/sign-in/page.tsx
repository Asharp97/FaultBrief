import { AuthForm } from "@/components/auth-form";

export const dynamic = "force-dynamic";
export default function SignInPage() {
  return (
    <AuthForm
      mode="sign-in"
      configured={Boolean(process.env.NEON_AUTH_BASE_URL && process.env.NEON_AUTH_COOKIE_SECRET)}
    />
  );
}
