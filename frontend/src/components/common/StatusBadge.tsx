/**
 * Status badges always combine colour *and* Persian text — never colour alone
 * (PROMPT.md 14.8). The English enum value from the API is translated through the
 * `enums` namespace.
 */
import { Badge, type BadgeProps } from "@/components/ui/badge";
import { Ltr } from "@/components/common/Ltr";
import { useDynamicTranslation } from "@/i18n/dynamic";

type StatusDomain = "healthStatus" | "credentialStatus" | "userStatus" | "capabilityState";

const TONES: Record<string, NonNullable<BadgeProps["tone"]>> = {
  healthy: "success",
  active: "success",
  implemented: "success",
  degraded: "warning",
  unverified: "warning",
  invited: "info",
  placeholder: "info",
  down: "danger",
  invalid: "danger",
  suspended: "danger",
  revoked: "neutral",
  unknown: "neutral",
  planned: "neutral",
};

export interface StatusBadgeProps {
  domain: StatusDomain;
  value: string;
  /** Adds a dot before the label for quick scanning. */
  withDot?: boolean;
  className?: string;
  /** Shows the raw English enum in a tooltip-friendly LTR span. */
  showRawValue?: boolean;
}

export function StatusBadge({
  domain,
  value,
  withDot = true,
  className,
  showRawValue = false,
}: StatusBadgeProps) {
  const enums = useDynamicTranslation("enums");
  const label = enums.t(`${domain}.${value}`, { defaultValue: value });
  const tone = TONES[value] ?? "neutral";

  return (
    <Badge tone={tone} className={className} title={showRawValue ? value : undefined}>
      {withDot ? (
        <span
          aria-hidden="true"
          className="inline-block size-1.5 rounded-full bg-current opacity-70"
        />
      ) : null}
      <span>{label}</span>
      {showRawValue ? (
        <Ltr mono className="opacity-60">
          {value}
        </Ltr>
      ) : null}
    </Badge>
  );
}

export default StatusBadge;
