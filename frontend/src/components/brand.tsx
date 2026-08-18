import { Timer } from "lucide-react";

/**
 * Chrome mark: the `timer` glyph over --brand plus the OperaX wordmark, as in
 * the handoff, until there is a mark of its own.
 */
export function Brand({ className = "" }: { className?: string }) {
  return (
    <span className={`flex items-center gap-3 ${className}`}>
      <span className="bg-brand text-on-brand flex size-8 items-center justify-center rounded-[10px]">
        <Timer aria-hidden="true" className="size-[19px]" strokeWidth={2} />
      </span>
      <span className="text-on-chrome text-xl font-extrabold tracking-[-0.5px]">
        OperaX
      </span>
    </span>
  );
}
