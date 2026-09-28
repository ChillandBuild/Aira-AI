/** SIM clients get no telecaller evaluation anywhere: no scores, no winners,
 * no QA review. Evaluation UI shows only once the tenant's calling provider
 * is definitively known to be "telecmi" -- unknown (still loading) and
 * "sim_basic" both resolve to false, so nothing flashes in before the
 * provider is confirmed. */
export type CallingProvider = "telecmi" | "sim_basic" | null | undefined;

export function showsEvaluation(provider: CallingProvider): boolean {
  return provider === "telecmi";
}
