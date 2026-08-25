import type { ComponentPropsWithRef } from "react";

/** `chrome` is the variant for actions sitting on the navy chrome. */
type ButtonVariant = "primary" | "chrome";

type ButtonProps = ComponentPropsWithRef<"button"> & {
  variant?: ButtonVariant;
};

const VARIANT_CLASS: Record<ButtonVariant, string> = {
  // The brand orange is a fill and never a text colour, so the label on it is
  // dark (#262626 on #FF8C00, 5.42:1). On hover the fill darkens to
  // --brand-strong and the label has to flip: dark on that would be 3.1:1,
  // white on it is 4.88:1.
  //
  // The disabled state of this button is "Entrando…" — the moment the user most
  // wants to read it, so the fill only softens, it does not wash out.
  primary:
    "bg-brand text-on-brand hover:bg-brand-strong hover:text-white disabled:bg-brand/90 disabled:text-on-brand",
  chrome:
    "border border-white/20 text-on-chrome hover:bg-white/10 disabled:opacity-60",
};

export function Button({
  variant = "primary",
  className = "",
  type = "button",
  ...props
}: ButtonProps) {
  return (
    <button
      type={type}
      className={`inline-flex h-10 items-center justify-center gap-2 rounded-full px-5 text-sm font-bold transition disabled:cursor-not-allowed ${VARIANT_CLASS[variant]} ${className}`}
      {...props}
    />
  );
}
