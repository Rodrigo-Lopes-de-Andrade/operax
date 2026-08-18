import { z } from "zod";

/**
 * Everything here is inlined into the browser bundle by Next, so nothing
 * secret belongs in this file. The Supabase service_role key exists only in
 * the FastAPI backend and must never reach the frontend (CLAUDE.md, contract
 * "Caminho 2").
 */
const publicEnvSchema = z.object({
  NEXT_PUBLIC_SUPABASE_URL: z.url(),
  NEXT_PUBLIC_SUPABASE_ANON_KEY: z.string().min(1),
  NEXT_PUBLIC_API_URL: z.url(),
  NEXT_PUBLIC_SENTRY_DSN: z.string().min(1).optional(),
});

export type PublicEnv = z.infer<typeof publicEnvSchema>;

let cached: PublicEnv | undefined;

/**
 * Reads and validates the public environment on first use. Validation is lazy
 * on purpose: a production build must not depend on a configured project, and
 * a missing variable has to fail loudly at the first request instead of
 * surfacing later as an obscure Supabase or fetch error.
 */
export function publicEnv(): PublicEnv {
  if (cached) {
    return cached;
  }

  // Literal member access: Next only inlines NEXT_PUBLIC_* when read this way.
  const parsed = publicEnvSchema.safeParse({
    NEXT_PUBLIC_SUPABASE_URL: process.env.NEXT_PUBLIC_SUPABASE_URL,
    NEXT_PUBLIC_SUPABASE_ANON_KEY: process.env.NEXT_PUBLIC_SUPABASE_ANON_KEY,
    NEXT_PUBLIC_API_URL: process.env.NEXT_PUBLIC_API_URL,
    NEXT_PUBLIC_SENTRY_DSN: process.env.NEXT_PUBLIC_SENTRY_DSN || undefined,
  });

  if (!parsed.success) {
    const problems = parsed.error.issues
      .map((issue) => `${issue.path.join(".")} (${issue.message})`)
      .join(", ");
    throw new Error(
      `Missing or invalid frontend environment: ${problems}. See frontend/.env.local.example.`,
    );
  }

  cached = parsed.data;
  return cached;
}
