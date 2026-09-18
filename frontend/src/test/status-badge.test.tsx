/**
 * Status badges must always carry Persian text, never colour alone
 * (PROMPT.md 14.8).
 */
import { render, screen } from "@testing-library/react";
import { describe, expect, it } from "vitest";

import { StatusBadge } from "@/components/common/StatusBadge";

describe("StatusBadge", () => {
  it("renders the Persian label for a health status", () => {
    render(<StatusBadge domain="healthStatus" value="degraded" />);
    expect(screen.getByText("کاهش‌یافته")).toBeInTheDocument();
  });

  it("renders the Persian label for an account status", () => {
    render(<StatusBadge domain="userStatus" value="suspended" />);
    expect(screen.getByText("غیرفعال")).toBeInTheDocument();
  });

  it("can expose the raw English enum in an LTR island", () => {
    const { container } = render(
      <StatusBadge domain="healthStatus" value="down" showRawValue />,
    );
    const raw = container.querySelector('[dir="ltr"]');
    expect(raw?.textContent).toBe("down");
    expect(screen.getByText("قطع")).toBeInTheDocument();
  });
});
