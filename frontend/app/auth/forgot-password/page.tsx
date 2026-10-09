import { PasswordRecoveryForm } from "@/components/password-recovery-form";

export const dynamic = "force-dynamic";
export default function ForgotPasswordPage() {
  return (
    <PasswordRecoveryForm
      mode="request"
      configured={Boolean(process.env.NEON_AUTH_BASE_URL && process.env.NEON_AUTH_COOKIE_SECRET)}
    />
  );
}
