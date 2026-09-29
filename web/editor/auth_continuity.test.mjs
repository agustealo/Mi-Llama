import assert from 'node:assert/strict'
import test from 'node:test'

import { AuthClient, AuthError } from '../../src/mi_llama/workspace_assets/auth.js'

const SESSION_KEY = 'mi-llama.supabase.session.v1'
const CONFIG = {
  supabase_url: 'https://example.supabase.co',
  supabase_publishable_key: 'publishable-test-key',
}

class MemoryStorage {
  constructor() {
    this.values = new Map()
  }

  getItem(key) {
    return this.values.has(key) ? this.values.get(key) : null
  }

  setItem(key, value) {
    this.values.set(key, String(value))
  }

  removeItem(key) {
    this.values.delete(key)
  }
}

function session({ accessToken = 'access-1', refreshToken = 'refresh-1', expiresAt } = {}) {
  return {
    access_token: accessToken,
    refresh_token: refreshToken,
    expires_at: expiresAt ?? Math.floor(Date.now() / 1000) + 3600,
    token_type: 'bearer',
    user: { id: 'user-1' },
  }
}

function installWindow(storedSession = null) {
  const storage = new MemoryStorage()
  if (storedSession) storage.setItem(SESSION_KEY, JSON.stringify(storedSession))
  globalThis.window = { sessionStorage: storage }
  return storage
}

function jsonResponse(payload, status = 200) {
  return new Response(JSON.stringify(payload), {
    status,
    headers: { 'Content-Type': 'application/json' },
  })
}

test('expired access token refreshes and persists rotated session for reload', async () => {
  const storage = installWindow(
    session({ accessToken: 'expired-access', refreshToken: 'refresh-old', expiresAt: 1 }),
  )
  const requests = []
  globalThis.fetch = async (url, options = {}) => {
    requests.push({ url: String(url), options })
    if (String(url).includes('grant_type=refresh_token')) {
      assert.deepEqual(JSON.parse(options.body), { refresh_token: 'refresh-old' })
      return jsonResponse(
        session({ accessToken: 'fresh-access', refreshToken: 'refresh-rotated' }),
      )
    }
    throw new Error(`unexpected fetch ${url}`)
  }

  const client = new AuthClient(CONFIG)
  assert.equal(await client.accessToken(), 'fresh-access')
  assert.equal(requests.length, 1)

  const persisted = JSON.parse(storage.getItem(SESSION_KEY))
  assert.equal(persisted.access_token, 'fresh-access')
  assert.equal(persisted.refresh_token, 'refresh-rotated')

  const reloaded = new AuthClient(CONFIG)
  assert.equal(reloaded.signedIn, true)
  assert.equal(reloaded.user.id, 'user-1')
  assert.equal(await reloaded.accessToken(), 'fresh-access')
  assert.equal(requests.length, 1)
})

test('API 401 refreshes once and replays the original request once', async () => {
  installWindow(session())
  const apiAuthorizations = []
  let refreshes = 0
  globalThis.fetch = async (url, options = {}) => {
    const target = String(url)
    if (target.includes('grant_type=refresh_token')) {
      refreshes += 1
      return jsonResponse(session({ accessToken: 'access-2', refreshToken: 'refresh-2' }))
    }
    if (target === '/api/projects') {
      apiAuthorizations.push(options.headers.get('Authorization'))
      return apiAuthorizations.length === 1
        ? new Response('', { status: 401 })
        : jsonResponse([{ id: 'project-1' }])
    }
    throw new Error(`unexpected fetch ${url}`)
  }

  const client = new AuthClient(CONFIG)
  const response = await client.apiFetch('/api/projects')

  assert.equal(response.status, 200)
  assert.equal(refreshes, 1)
  assert.deepEqual(apiAuthorizations, ['Bearer access-1', 'Bearer access-2'])
})

test('failed refresh clears stored authentication', async () => {
  const storage = installWindow(
    session({ accessToken: 'expired-access', refreshToken: 'invalid-refresh', expiresAt: 1 }),
  )
  globalThis.fetch = async (url) => {
    assert.match(String(url), /grant_type=refresh_token/)
    return jsonResponse({ error: 'invalid_grant' }, 400)
  }

  const client = new AuthClient(CONFIG)
  await assert.rejects(client.accessToken(), (error) => {
    assert.ok(error instanceof AuthError)
    assert.equal(error.status, 400)
    return true
  })
  assert.equal(client.signedIn, false)
  assert.equal(storage.getItem(SESSION_KEY), null)
})

test('sign out cannot be undone by an in-flight refresh', async () => {
  const storage = installWindow(session({ accessToken: 'access-old', refreshToken: 'refresh-old' }))
  let releaseRefresh
  const refreshResponse = new Promise((resolve) => {
    releaseRefresh = resolve
  })

  globalThis.fetch = async (url) => {
    const target = String(url)
    if (target.includes('grant_type=refresh_token')) return refreshResponse
    if (target.includes('/auth/v1/logout')) return new Response(null, { status: 204 })
    throw new Error(`unexpected fetch ${url}`)
  }

  const client = new AuthClient(CONFIG)
  const refreshing = client.refresh()
  await Promise.resolve()
  await client.signOut()

  releaseRefresh(
    jsonResponse(session({ accessToken: 'resurrected-access', refreshToken: 'resurrected-refresh' })),
  )

  await assert.rejects(refreshing, (error) => {
    assert.ok(error instanceof AuthError)
    assert.equal(error.status, 401)
    return true
  })
  assert.equal(client.signedIn, false)
  assert.equal(storage.getItem(SESSION_KEY), null)
})
