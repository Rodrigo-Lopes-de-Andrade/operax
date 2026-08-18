import type { ComponentPropsWithRef } from "react";

type TextFieldProps = Omit<ComponentPropsWithRef<"input">, "id"> & {
  id: string;
  label: string;
  error?: string;
};

export function TextField({ id, label, error, ...props }: TextFieldProps) {
  const errorId = `${id}-error`;

  return (
    <div className="flex flex-col gap-1.5">
      <label
        htmlFor={id}
        className="text-2xs text-ink-muted font-bold tracking-[0.08em] uppercase"
      >
        {label}
      </label>
      <input
        id={id}
        aria-invalid={error ? true : undefined}
        aria-describedby={error ? errorId : undefined}
        className="bg-control border-control-line text-ink placeholder:text-ink-faint h-10 rounded-[10px] border px-3 text-base outline-none focus-visible:border-transparent"
        {...props}
      />
      {error ? (
        <p id={errorId} className="text-bad text-xs font-medium">
          {error}
        </p>
      ) : null}
    </div>
  );
}
