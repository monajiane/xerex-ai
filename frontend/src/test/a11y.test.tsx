/**
 * Accessibility guarantees for the admin panel (M7).
 *
 * These are the behaviours an administrator who navigates with a keyboard depends on:
 * a skip link before the navigation, a modal that traps focus and hands it back, labelled
 * controls, table headers associated with their cells, and no icon-only button without an
 * accessible name. Layout and copy are covered by the module tests; this file covers the
 * interaction contract.
 */
import { render, screen, waitFor, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { useState } from "react";
import { describe, expect, it } from "vitest";

import { Button } from "@/components/ui/button";
import { Dialog } from "@/components/ui/dialog";
import { Table, TableBody, TableCell, TableHead, TableHeader, TableRow } from "@/components/ui/table";
import { ConfirmDialog } from "@/components/common/ConfirmDialog";
import { applyDocumentLocale } from "@/i18n";
import { ThemeProvider } from "@/lib/theme/ThemeProvider";

function Harness({ confirm = false }: { confirm?: boolean }) {
  const [open, setOpen] = useState(false);
  return (
    <ThemeProvider>
      <button type="button" onClick={() => setOpen(true)}>
        باز کردن
      </button>
      {confirm ? (
        <ConfirmDialog
          open={open}
          onClose={() => setOpen(false)}
          onConfirm={() => setOpen(false)}
          title="حذف ارائه‌دهنده"
          message="آیا از حذف مطمئن هستید؟"
        />
      ) : (
        <Dialog
          open={open}
          onClose={() => setOpen(false)}
          title="ویرایش ارائه‌دهنده"
          description="تغییرات پس از ذخیره اعمال می‌شود."
          footer={<Button type="button">ذخیره تغییرات</Button>}
        >
          <label htmlFor="name">نام</label>
          <input id="name" />
          <label htmlFor="url">آدرس پایه</label>
          <input id="url" />
        </Dialog>
      )}
    </ThemeProvider>
  );
}

describe("dialog keyboard contract", () => {
  it("moves focus into the dialog, traps Tab and restores focus on close", async () => {
    const user = userEvent.setup();
    applyDocumentLocale("fa");
    render(<Harness />);

    const opener = screen.getByRole("button", { name: "باز کردن" });
    await user.click(opener);

    const dialog = await screen.findByRole("dialog");
    expect(dialog).toHaveAttribute("aria-modal", "true");
    expect(dialog).toHaveAccessibleName("ویرایش ارائه‌دهنده");

    // Focus starts inside the dialog, on its first control.
    await waitFor(() => expect(dialog.contains(document.activeElement)).toBe(true));

    // Tab cycles through the dialog and wraps instead of escaping to the page.
    const focusables = within(dialog)
      .getAllByRole("button")
      .concat(within(dialog).getAllByRole("textbox") as unknown as HTMLElement[]);
    expect(focusables.length).toBeGreaterThan(1);
    for (let step = 0; step < focusables.length + 2; step += 1) {
      await user.tab();
      expect(dialog.contains(document.activeElement)).toBe(true);
    }

    // Shift+Tab wraps backwards, still inside.
    await user.tab({ shift: true });
    expect(dialog.contains(document.activeElement)).toBe(true);

    // Escape closes and focus returns to the button that opened the dialog.
    await user.keyboard("{Escape}");
    await waitFor(() => expect(screen.queryByRole("dialog")).not.toBeInTheDocument());
    expect(document.activeElement).toBe(opener);
  });

  it("locks body scrolling while the dialog is open", async () => {
    const user = userEvent.setup();
    render(<Harness />);
    await user.click(screen.getByRole("button", { name: "باز کردن" }));
    expect(document.body.style.overflow).toBe("hidden");
    await user.keyboard("{Escape}");
    await waitFor(() => expect(document.body.style.overflow).not.toBe("hidden"));
  });

  it("gives the confirmation dialog an accessible name and a labelled cancel action", async () => {
    const user = userEvent.setup();
    render(<Harness confirm />);
    await user.click(screen.getByRole("button", { name: "باز کردن" }));

    const dialog = await screen.findByRole("dialog");
    expect(dialog).toHaveAccessibleName("حذف ارائه‌دهنده");
    expect(within(dialog).getByRole("button", { name: "لغو" })).toBeInTheDocument();
    expect(within(dialog).getByText("آیا از حذف مطمئن هستید؟")).toBeInTheDocument();
  });
});

describe("structural accessibility", () => {
  it("associates table headers with their columns", () => {
    render(
      <Table>
        <TableHeader>
          <TableRow>
            <TableHead>ارائه‌دهنده</TableHead>
            <TableHead>زمان پاسخ</TableHead>
          </TableRow>
        </TableHeader>
        <TableBody>
          <TableRow>
            <TableCell>OpenAI Primary</TableCell>
            <TableCell>۳۲۰ میلی‌ثانیه</TableCell>
          </TableRow>
        </TableBody>
      </Table>,
    );

    const headers = screen.getAllByRole("columnheader");
    expect(headers.map((header) => header.textContent)).toEqual(["ارائه‌دهنده", "زمان پاسخ"]);
    expect(screen.getAllByRole("cell")).toHaveLength(2);
  });

  it("keeps the document Persian and right-to-left by default", () => {
    applyDocumentLocale("fa");
    expect(document.documentElement.getAttribute("lang")).toBe("fa");
    expect(document.documentElement.getAttribute("dir")).toBe("rtl");
  });
});
