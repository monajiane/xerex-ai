/**
 * Error rendering pipeline (PROMPT.md 14.5):
 * the API returns an English code → the panel shows Persian text and keeps the
 * raw code visible in an LTR island so it can be quoted in a report.
 */
import { render, screen } from "@testing-library/react";
import { describe, expect, it } from "vitest";

import { ErrorState, useErrorCopy } from "@/components/common/DataState";
import { ApiError } from "@/lib/api/client";

function HookProbe({ error }: { error: unknown }) {
  const { message, code } = useErrorCopy(error);
  return (
    <>
      <span data-testid="message">{message}</span>
      <span data-testid="code">{code ?? ""}</span>
    </>
  );
}

describe("error copy", () => {
  it("translates a known API error code into Persian", () => {
    const error = new ApiError({
      code: "invalid_credentials",
      message: "Invalid email or password.",
      status: 401,
    });
    render(<HookProbe error={error} />);
    expect(screen.getByTestId("message")).toHaveTextContent("ایمیل یا گذرواژه نادرست است.");
  });

  it("falls back to a generic Persian message for unknown codes", () => {
    const error = new ApiError({ code: "totally_new_code", message: "?", status: 500 });
    render(<HookProbe error={error} />);
    expect(screen.getByTestId("message")).toHaveTextContent(
      "انجام عملیات ممکن نشد. لطفاً دوباره تلاش کنید.",
    );
    expect(screen.getByTestId("code")).toHaveTextContent("totally_new_code");
  });

  it("interpolates server details into the Persian message", () => {
    const error = new ApiError({
      code: "password_too_short",
      message: "Too short.",
      status: 422,
      details: { min_length: 12 },
    });
    render(<HookProbe error={error} />);
    expect(screen.getByTestId("message")).toHaveTextContent("12");
  });

  it("renders the raw code and request id in LTR islands", () => {
    const error = new ApiError({
      code: "rate_limit_exceeded",
      message: "Too many requests.",
      status: 429,
      requestId: "req_abc123",
    });
    render(<ErrorState error={error} />);
    expect(screen.getByText("تعداد درخواست‌ها بیش از حد مجاز است. کمی بعد تلاش کنید.")).toBeInTheDocument();
    const ltrValues = Array.from(document.querySelectorAll('[dir="ltr"]')).map((node) => node.textContent);
    expect(ltrValues).toContain("rate_limit_exceeded");
    expect(ltrValues).toContain("req_abc123");
  });
});
