"use client";

import { ChevronsUpDown } from "lucide-react";
import { useRouter } from "next/navigation";

export type SelectOption = { value: string; label: string; href: string };
export type SelectGroup = { label: string; options: SelectOption[] };

/**
 * A select whose value is a URL. Choosing an option navigates, because the cut
 * is the query string and nothing about it is component state.
 *
 * Each option carries its own href: this runs in the browser and the hrefs are
 * built on the server, where the units the user can see were resolved.
 */
export function SelectNav({
  label,
  value,
  placeholder,
  placeholderHref,
  groups,
}: {
  label: string;
  value: string;
  placeholder: string;
  placeholderHref: string;
  groups: SelectGroup[];
}) {
  const router = useRouter();
  const hrefs = new Map<string, string>([
    ["", placeholderHref],
    ...groups.flatMap((group) =>
      group.options.map((option) => [option.value, option.href] as const),
    ),
  ]);

  return (
    <label className="flex min-w-[200px] flex-col gap-1.5">
      <span className="text-2xs text-ink-faint font-bold tracking-[0.08em] uppercase">
        {label}
      </span>
      <span className="relative">
        <select
          value={value}
          onChange={(event) =>
            router.push(hrefs.get(event.target.value) ?? placeholderHref)
          }
          className="border-control-line bg-control text-ink h-10 w-full appearance-none rounded-[10px] border px-3 pr-9 text-sm font-semibold"
        >
          <option value="">{placeholder}</option>
          {groups.map((group) => (
            <optgroup key={group.label} label={group.label}>
              {group.options.map((option) => (
                <option key={option.value} value={option.value}>
                  {option.label}
                </option>
              ))}
            </optgroup>
          ))}
        </select>
        <ChevronsUpDown
          size={15}
          aria-hidden
          className="text-ink-faint pointer-events-none absolute top-1/2 right-3 -translate-y-1/2"
        />
      </span>
    </label>
  );
}
