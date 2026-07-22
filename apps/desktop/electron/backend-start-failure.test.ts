import assert from 'node:assert/strict'

import { test } from 'vitest'

import { shouldLatchBackendStartFailure } from './backend-start-failure'

test('latches a LOCAL backend failure so the install-retry loop is broken', () => {
  assert.equal(shouldLatchBackendStartFailure({ attemptedRemote: false }), true)
})

test('never latches a transient REMOTE failure so recovery stays retryable without a restart', () => {
  // A lapsed OAuth access-token / mint timeout / host briefly unreachable across
  // a laptop sleep must not wedge the app: the next connect has to re-attempt
  // and re-mint against the refreshed session.
  assert.equal(shouldLatchBackendStartFailure({ attemptedRemote: true }), false)
  assert.equal(shouldLatchBackendStartFailure({ attemptedRemote: true, needsAuth: false }), false)
})

test('latches a REMOTE auth-required failure so resolve cannot hot-loop', () => {
  // No session cookies / needsOauthLogin: retrying startHermes() forever only
  // floods desktop.log and burns CPU — the user has to Sign in or switch Local.
  assert.equal(shouldLatchBackendStartFailure({ attemptedRemote: true, needsAuth: true }), true)
})

test('local failures latch even when needsAuth is set (install loop still wins)', () => {
  assert.equal(shouldLatchBackendStartFailure({ attemptedRemote: false, needsAuth: true }), true)
  assert.equal(shouldLatchBackendStartFailure({ attemptedRemote: false, needsAuth: false }), true)
})
