/**
 * LTR isolation island (PROMPT.md 14.4).
 *
 * Any technical value that appears inside a Persian sentence must be wrapped so
 * that the bidi algorithm cannot reorder the words around it:
 *
 *     <p>کلید API: <Ltr>{key}</Ltr></p>
 *
 * `unicode-bidi: isolate` keeps surrounding Persian in place; `lang="en"` helps
 * screen readers and spell checkers treat the run as English.
 */
import { cn } from "@/lib/utils";

export interface LtrProps extends React.HTMLAttributes<HTMLElement> {
  /** Renders a monospace run — use for keys, ids, code, JSON and logs. */
  mono?: boolean;
  /** Use on `<span>` (default), `<code>`, `<kbd>` or any inline element. */
  as?: "span" | "code" | "kbd" | "samp" | "bdi" | "div";
}

export function Ltr({ as: Tag = "span", mono = false, className, children, ...props }: LtrProps) {
  return (
    <Tag
      dir="ltr"
      lang="en"
      className={cn("ltr-isolate", mono && "font-mono text-[0.8125rem]", className)}
      {...props}
    >
      {children}
    </Tag>
  );
}

export default Ltr;
