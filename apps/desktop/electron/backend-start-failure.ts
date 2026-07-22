/**
 * backend-start-failure.ts
 *
 * Decides whether a failed primary-backend boot should *latch* into
 * `backendStartFailure`. A latched failure makes every subsequent
 * startHermes() re-throw the cached error without re-attempting the connect —
 * the right behavior for a LOCAL backend so the renderer's retry loop can't
 * restart a broken install over and over.
 *
 * It is usually the WRONG behavior for a REMOTE backend. A remote connect can
 * fail for transient reasons — a lapsed OAuth access-token cookie (the gateway
 * rotates a fresh one from the live refresh-token cookie on the next request),
 * a ws-ticket mint that timed out mid sleep/wake, or a host that was briefly
 * unreachable across a laptop sleep. There is no child process whose 'exit'
 * handler would clear the cache, so a latched remote failure sticks until the
 * whole app is quit and relaunched: reconnect, "Sign out & sign in" (which only
 * reloads the renderer), and the wake-recovery revalidate path all keep hitting
 * the same stale error. Not latching lets the very next connect re-mint a
 * ticket against the (now refreshed) session and self-heal.
 *
 * Exception: when the remote failure is an auth-required signal
 * (`needsOauthLogin` / no session cookies at all), retrying is pointless and
 * burns a hot loop of resolve → fail → resolve against a condition only the
 * user can fix (Sign in / switch to Local). Latch those so the recovery overlay
 * stays quiet until apply/oauth-login/reset clears the latch.
 *
 * Extracted as a dependency-free pure predicate so the invariant is testable
 * without booting Electron or reading main.ts source text.
 */

export interface BackendStartFailureContext {
  /**
   * True when the boot that just failed was resolving/dialing a REMOTE (or
   * cloud) primary backend rather than spawning a local child.
   */
  attemptedRemote: boolean
  /**
   * True when the failure is an auth gate the user must clear (no OAuth
   * session cookies / explicit needsOauthLogin), not a transient network or
   * mint blip. Optional so older call sites stay valid.
   */
  needsAuth?: boolean
}

/**
 * Whether a startHermes() failure should latch into `backendStartFailure`.
 * Latch local failures (prevent install-restart loops). Latch remote
 * auth-required failures (prevent hot resolve loops). Leave other remote
 * failures unlatched so recovery paths can re-attempt without an app restart.
 */
export function shouldLatchBackendStartFailure(context: BackendStartFailureContext): boolean {
  if (!context.attemptedRemote) {
    return true
  }

  return Boolean(context.needsAuth)
}
