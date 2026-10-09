import type { Metadata } from "next";
import { PasswordRecoveryForm } from "@/components/password-recovery-form";

export const dynamic = "force-dynamic";
export const metadata: Metadata = {
  referrer: "no-referrer",
  robots: { index: false, follow: false },
};
export default function ResetPasswordPage() {
  return (
    <PasswordRecoveryForm
      mode="reset"
      configured={Boolean(process.env.NEON_AUTH_BASE_URL && process.env.NEON_AUTH_COOKIE_SECRET)}
    />
  );
}
