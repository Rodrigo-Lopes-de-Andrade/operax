import { SquareParking } from "lucide-react";

import { currentBrand } from "@/lib/brand";

/**
 * The tenant's mark on the chrome. The glyph sits on a fill of --brand and the
 * wordmark is --text-on-dark, because the chrome is dark — the orange is never
 * the text and never carries white on it.
 *
 * The glyph stands in until the client ships a logo asset; the brand manual is
 * in design/uploads/.
 */
export function Brand({ className = "" }: { className?: string }) {
  const brand = currentBrand();

  return (
    <span className={`flex items-center gap-3 ${className}`}>
      <span className="bg-brand text-on-brand flex size-8 items-center justify-center rounded-[10px]">
        <SquareParking
          aria-hidden="true"
          className="size-[19px]"
          strokeWidth={2.2}
        />
      </span>
      <span className="text-on-chrome text-xl font-extrabold tracking-[-0.5px]">
        {brand.name}
      </span>
    </span>
  );
}
