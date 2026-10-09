import { AuthForm } from "@/components/auth-form";

export const dynamic = "force-dynamic";
export default function SignUpPage() {
  return (
    <AuthForm
      mode="sign-up"
      configured={Boolean(process.env.NEON_AUTH_BASE_URL && process.env.NEON_AUTH_COOKIE_SECRET)}
    />
  );
}
