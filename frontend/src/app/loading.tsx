import { Spinner } from "@/components/ui/spinner";

export default function Loading() {
  return (
    <div
      role="status"
      className="text-ink-muted flex min-h-dvh items-center justify-center gap-3 text-sm"
    >
      <Spinner />
      Carregando…
    </div>
  );
}
