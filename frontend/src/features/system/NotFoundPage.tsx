import { Link } from "react-router-dom";
import { useTranslation } from "react-i18next";

import { buttonVariants } from "@/components/ui/button";
import { EmptyState } from "@/components/common/DataState";

export function NotFoundPage() {
  const { t } = useTranslation("notFound");

  return (
    <EmptyState
      title={t("title")}
      hint={t("description")}
      action={
        <Link to="/" className={buttonVariants({ variant: "secondary", size: "sm" })}>
          {t("action")}
        </Link>
      }
    />
  );
}

export default NotFoundPage;
