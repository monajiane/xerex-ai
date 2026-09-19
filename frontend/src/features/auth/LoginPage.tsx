/**
 * Sign-in screen (Persian, RTL).
 *
 * Inputs are laid out with logical properties, so in Persian the field text starts
 * on the right while the email address itself stays in an LTR run.
 */
import { Languages, Lock, LogIn, Mail } from "lucide-react";
import { useState, type FormEvent } from "react";
import { useTranslation } from "react-i18next";

import { Button } from "@/components/ui/button";
import { Field, Input } from "@/components/ui/input";
import { useErrorCopy } from "@/components/common/DataState";
import { Ltr } from "@/components/common/Ltr";
import { useAuth } from "@/features/auth/AuthProvider";
import { useLocale } from "@/lib/locale/LocaleProvider";

export function AuthLayout({
  title,
  subtitle,
  children,
}: {
  title: string;
  subtitle: string;
  children: React.ReactNode;
}) {
  const { t } = useTranslation("common");
  const { locale, setLocale } = useLocale();
  const { milestone } = useAuth();

  return (
    <div className="flex min-h-screen flex-col bg-surface-muted" style={{ backgroundColor: "var(--app-surface-muted)" }}>
      <header className="flex items-center justify-between px-6 py-4">
        <div className="flex items-center gap-2">
          <span className="grid size-9 place-items-center rounded-xl bg-brand-600 text-sm font-bold text-white">
            XR
          </span>
          <div className="text-start">
            <p className="text-sm font-bold">{t("appName")}</p>
            <p className="app-muted text-[0.6875rem]">{t("panel")}</p>
          </div>
        </div>
        <Button
          variant="ghost"
          size="sm"
          onClick={() => setLocale(locale === "fa" ? "en" : "fa")}
          aria-label={t("language.switchTo", {
              language: locale === "fa" ? t("language.en") : t("language.fa"),
            })}
        >
          <Languages aria-hidden="true" />
          <Ltr>{locale === "fa" ? t("language.en") : t("language.fa")}</Ltr>
        </Button>
      </header>

      <main className="flex flex-1 items-center justify-center px-4 py-10">
        <div className="w-full max-w-md">
          <div className="app-card p-6 shadow-sm">
            <div className="text-start">
              <h1 className="text-lg font-bold">{title}</h1>
              <p className="app-muted mt-1 text-xs leading-relaxed">{subtitle}</p>
            </div>
            <div className="mt-6">{children}</div>
          </div>
          <p className="app-muted mt-4 text-center text-[0.6875rem] leading-relaxed">
            {t("build.milestoneValue", { milestone: milestone || "—" })}
          </p>
        </div>
      </main>
    </div>
  );
}

export function LoginPage() {
  const { t } = useTranslation(["auth", "validation"]);
  const { login, requiresBootstrap, bootstrapAllowed } = useAuth();
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
      await login(email, password);
    } catch (caught) {
      setError(caught);
    } finally {
      setSubmitting(false);
    }
  };

  return (
    <AuthLayout title={t("auth:signInTitle")} subtitle={t("auth:signInSubtitle")}>
      {requiresBootstrap && !bootstrapAllowed ? (
        <p className="mb-4 rounded-lg border border-amber-300/60 bg-amber-50 p-3 text-xs leading-relaxed text-amber-900 dark:border-amber-500/40 dark:bg-amber-500/10 dark:text-amber-200">
          {t("auth:bootstrapDisabledNotice")}
        </p>
      ) : null}
      <form className="flex flex-col gap-4" onSubmit={onSubmit} noValidate>
        <Field label={t("auth:email")} htmlFor="email" required>
          <div className="relative">
            <Mail
              className="pointer-events-none absolute inset-y-0 start-3 my-auto size-4 app-muted"
              aria-hidden="true"
            />
            <Input
              id="email"
              type="email"
              technical
              autoComplete="username"
              required
              className="ps-9"
              placeholder={t("auth:emailPlaceholder")}
              value={email}
              onChange={(event) => setEmail(event.target.value)}
            />
          </div>
        </Field>

        <Field label={t("auth:password")} htmlFor="password" hint={t("auth:passwordHint")} required>
          <div className="relative">
            <Lock
              className="pointer-events-none absolute inset-y-0 start-3 my-auto size-4 app-muted"
              aria-hidden="true"
            />
            <Input
              id="password"
              type="password"
              autoComplete="current-password"
              required
              className="ps-9"
              placeholder={t("auth:passwordPlaceholder")}
              value={password}
              onChange={(event) => setPassword(event.target.value)}
            />
          </div>
        </Field>

        {error ? (
          <p role="alert" className="rounded-lg border border-rose-200 bg-rose-50 px-3 py-2 text-xs text-rose-800 dark:border-rose-900 dark:bg-rose-950/50 dark:text-rose-100">
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
          {!submitting ? <LogIn aria-hidden="true" /> : null}
          {submitting ? t("auth:signingIn") : t("auth:signIn")}
        </Button>

        <p className="app-muted text-center text-[0.6875rem] leading-relaxed">
          {t("auth:securityNote")}
        </p>
      </form>
    </AuthLayout>
  );
}

export default LoginPage;
