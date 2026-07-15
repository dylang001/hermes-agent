/**
 * Tests for electron/backend-start-ownership.ts.
 *
 * Soft re-home must not let a dying local serve child wipe a newer remote
 * connectionPromise or paint "Desktop boot failed (SIGKILL)".
 */

import assert from 'node:assert/strict'

import { describe, it } from 'vitest'

import { backendStartOwnership, shouldIgnoreAbandonedBackendStart } from './backend-start-ownership'

describe('backendStartOwnership', () => {
  it('owns both process and connection for the live start', () => {
    const child = { pid: 1 }
    const promise = Promise.resolve('local')
    const ownership = backendStartOwnership({
      hermesProcess: child,
      child,
      connectionPromise: promise,
      ownedPromise: promise
    })

    assert.equal(ownership.ownsProcess, true)
    assert.equal(ownership.ownsConnection, true)
    assert.equal(shouldIgnoreAbandonedBackendStart(ownership), false)
  })

  it('ignores a dying local child after soft re-home replaced the connection', () => {
    const dyingChild = { pid: 1 }
    const localPromise = Promise.resolve('local')
    const remotePromise = Promise.resolve('remote')

    const ownership = backendStartOwnership({
      hermesProcess: null,
      child: dyingChild,
      connectionPromise: remotePromise,
      ownedPromise: localPromise
    })

    assert.equal(ownership.ownsProcess, false)
    assert.equal(ownership.ownsConnection, false)
    assert.equal(shouldIgnoreAbandonedBackendStart(ownership), true)
  })

  it('still owns process cleanup when only the connection was superseded', () => {
    const child = { pid: 2 }
    const localPromise = Promise.resolve('local')
    const remotePromise = Promise.resolve('remote')

    const ownership = backendStartOwnership({
      hermesProcess: child,
      child,
      connectionPromise: remotePromise,
      ownedPromise: localPromise
    })

    assert.equal(ownership.ownsProcess, true)
    assert.equal(ownership.ownsConnection, false)
    assert.equal(shouldIgnoreAbandonedBackendStart(ownership), true)
  })
})
