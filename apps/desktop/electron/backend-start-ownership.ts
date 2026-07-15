/**
 * Ownership checks for a desktop-spawned local backend child.
 *
 * Soft re-home / remote reconnect can null `connectionPromise` and start a new
 * boot while an OLD local `serve` child is still exiting. That child's exit
 * handler must NOT wipe the newer connection or paint "Desktop boot failed"
 * over a healthy remote session.
 */

export interface BackendStartOwnership {
  /** True when `hermesProcess` still points at this child. */
  ownsProcess: boolean
  /** True when `connectionPromise` is still this start's promise. */
  ownsConnection: boolean
}

export function backendStartOwnership(args: {
  hermesProcess: unknown
  child: unknown
  connectionPromise: unknown
  ownedPromise: unknown
}): BackendStartOwnership {
  return {
    ownsProcess: args.hermesProcess === args.child,
    ownsConnection: args.connectionPromise === args.ownedPromise
  }
}

/** True when a dying/superseded start should stay silent in the boot UI. */
export function shouldIgnoreAbandonedBackendStart(ownership: BackendStartOwnership): boolean {
  return !ownership.ownsConnection
}
