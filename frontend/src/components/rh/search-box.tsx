"use client";

import { Search } from "lucide-react";
import { useRouter } from "next/navigation";
import { useState } from "react";

import { rhHref, type RhFilters } from "@/lib/rh/url";

/**
 * Busca por nome, matrícula ou ID RH.
 *
 * Submete em vez de buscar a cada tecla: cada navegação é uma consulta ao
 * backend, e uma consulta por caractere digitado é um jeito caro de escrever
 * "silva". Do jeito que está, o Enter é o que aplica — e o resultado continua
 * sendo uma URL que se manda para alguém.
 */
export function SearchBox({ filters }: { filters: RhFilters }) {
  const router = useRouter();
  const [value, setValue] = useState(filters.busca ?? "");

  return (
    <form
      role="search"
      className="flex min-w-[240px] flex-col gap-1.5"
      onSubmit={(event) => {
        event.preventDefault();
        router.push(rhHref(filters, { busca: value.trim() || null }));
      }}
    >
      <label
        htmlFor="rh-busca"
        className="text-2xs text-ink-faint font-bold tracking-[0.08em] uppercase"
      >
        Buscar
      </label>
      <span className="relative">
        <Search
          size={15}
          aria-hidden
          className="text-ink-faint absolute top-1/2 left-3 -translate-y-1/2"
        />
        <input
          id="rh-busca"
          type="search"
          value={value}
          onChange={(event) => setValue(event.target.value)}
          placeholder="Nome, matrícula ou ID RH"
          className="bg-control border-control-line text-ink placeholder:text-ink-faint h-10 w-full rounded-[10px] border pr-3 pl-9 text-sm outline-none focus-visible:border-transparent"
        />
      </span>
    </form>
  );
}
