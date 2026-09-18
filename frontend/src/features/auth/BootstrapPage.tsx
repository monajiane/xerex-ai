/**
 * First-run screen: creates the initial owner account.
 * Shown only while the API reports `requires_bootstrap: true`.
 */
import { ShieldCheck, UserPlus } from "lucide-react";
import { useState, type FormEvent } from "react";
import { useTranslation } from "react-i18next";

import { Button } from "@/components/ui/button";
import { Field, Input } from "@/components/ui/input";
import { useErrorCopy } from "@/components/common/DataState";
import { Ltr } from "@/components/common/Ltr";
import { AuthLayout, LoginPage } from "@/features/auth/LoginPage";
import { useAuth } from "@/features/auth/AuthProvider";

export function BootstrapPage() {
  const { t } = useTranslation(["auth", "errors"]);
  const { bootstrap } = useAuth();
  const [fullName, setFullName] = useState("");
  const [email, setEmail] = useState("");
  const [password, setPassword] = useState("");
  const [submitting, setSubmitting] = useState(false);
  const [error, setError] = useState<unknown>(null);
  const { message, code } = useErrorCopy(error);

  const onSubmit = async (event: FormEvent) => {
    event.preventDefault();
    setSubmitting(true);
    setError(null);
    try {
      await bootstrap(email, password, fullName || undefined);
    } catch (caught) {
      setError(caught);
    } finally {
      setSubmitting(false);
    }
  };

  return (
    <AuthLayout title={t("auth:bootstrapTitle")} subtitle={t("auth:bootstrapSubtitle")}>
      <form className="flex flex-col gap-4" onSubmit={onSubmit} noValidate>
        <Field label={t("auth:fullName")} htmlFor="fullName">
          <Input
            id="fullName"
            autoComplete="name"
            placeholder={t("auth:fullNamePlaceholder")}
            value={fullName}
            onChange={(event) => setFullName(event.target.value)}
          />
        </Field>

        <Field label={t("auth:email")} htmlFor="bootstrap-email" required>
          <Input
            id="bootstrap-email"
            type="email"
            technical
            required
            autoComplete="username"
            placeholder={t("auth:emailPlaceholder")}
            value={email}
            onChange={(event) => setEmail(event.target.value)}
          />
        </Field>

        <Field
          label={t("auth:password")}
          htmlFor="bootstrap-password"
          hint={t("auth:passwordHint")}
          required
        >
          <Input
            id="bootstrap-password"
            type="password"
            required
            minLength={10}
            autoComplete="new-password"
            placeholder={t("auth:passwordPlaceholder")}
            value={password}
            onChange={(event) => setPassword(event.target.value)}
          />
        </Field>

        {error ? (
          <p
            role="alert"
            className="rounded-lg border border-rose-200 bg-rose-50 px-3 py-2 text-xs text-rose-800 dark:border-rose-900 dark:bg-rose-950/50 dark:text-rose-100"
          >
            {message}
            {code ? (
              <>
                {" — "}
                <Ltr mono className="opacity-80">
                  {code}
                </Ltr>
              </>
            ) : null}
          </p>
        ) : null}

        <Button type="submit" loading={submitting} size="lg" className="w-full">
          {!submitting ? <UserPlus aria-hidden="true" /> : null}
          {submitting ? t("auth:bootstrapping") : t("auth:bootstrapSubmit")}
        </Button>

        <p className="app-muted flex items-center justify-center gap-1.5 text-center text-[0.6875rem] leading-relaxed">
          <ShieldCheck className="size-3.5" aria-hidden="true" />
          {t("auth:securityNote")}
        </p>
      </form>
    </AuthLayout>
  );
}

/** Chooses between first-run setup and the normal sign-in screen. */
export function AuthGate() {
  const { requiresBootstrap } = useAuth();
  return requiresBootstrap ? <BootstrapPage /> : <LoginPage />;
}

export default BootstrapPage;
