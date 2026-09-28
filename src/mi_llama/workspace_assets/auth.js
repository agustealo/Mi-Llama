const SESSION_KEY = 'mi-llama.supabase.session.v1'
const REFRESH_SKEW_SECONDS = 60
export const SIGN_IN_UNAVAILABLE = 'Sign-in is unavailable in this workspace.'
let sharedClientPromise = null
let apiFetchInterceptor = null

export class AuthError extends Error {
  constructor(message, status = 0) {
    super(message)
    this.name = 'AuthError'
    this.status = status
  }
}

export function installApiFetchInterceptor(interceptor) {
  if (interceptor !== null && typeof interceptor !== 'function') {
    throw new TypeError('API fetch interceptor must be a function or null')
  }
  if (apiFetchInterceptor && interceptor && apiFetchInterceptor !== interceptor) {
    throw new Error('An API fetch interceptor is already installed')
  }
  apiFetchInterceptor = interceptor
}

function readStoredSession() {
  try {
    const raw = window.sessionStorage.getItem(SESSION_KEY)
    if (!raw) return null
    const parsed = JSON.parse(raw)
    if (!parsed?.access_token || !parsed?.refresh_token) return null
    return parsed
  } catch (_error) {
    return null
  }
}

function storeSession(session) {
  if (!session) {
    window.sessionStorage.removeItem(SESSION_KEY)
    return
  }
  const expiresAt = session.expires_at || Math.floor(Date.now() / 1000) + (session.expires_in || 3600)
  const safeSession = {
    access_token: session.access_token,
    refresh_token: session.refresh_token,
    expires_at: expiresAt,
    token_type: session.token_type || 'bearer',
    user: session.user || null,
  }
  window.sessionStorage.setItem(SESSION_KEY, JSON.stringify(safeSession))
}

async function responseError(response, fallback) {
  try {
    const payload = await response.json()
    return payload?.msg || payload?.message || payload?.error_description || payload?.error || payload?.detail || fallback
  } catch (_error) {
    return fallback
  }
}

function authMessage(message, status, fallback) {
  const normalized = String(message || '').toLowerCase()
  if (status === 429) return 'Too many sign-in attempts. Try again shortly.'
  if (status >= 500) return 'Sign-in service is temporarily unavailable. Try again shortly.'
  if (normalized.includes('email not confirmed')) return 'Confirm your email before signing in.'
  if (
    status === 400 ||
    status === 401 ||
    normalized.includes('invalid login') ||
    normalized.includes('invalid credentials') ||
    normalized.includes('invalid password')
  ) {
    return 'Email or password is incorrect.'
  }
  return fallback
}

export function apiErrorMessage(status) {
  if (status === 401) return 'Your session has ended. Sign in again.'
  if (status === 403) return 'You do not have access to do that in this project.'
  if (status === 404) return 'That item is no longer available. Refresh and try again.'
  if (status === 409) return 'This changed since you opened it. Review the latest version and try again.'
  if (status === 413) return 'That item is too large to process here.'
  if (status === 422) return 'Some of the information needs attention before this can continue.'
  if (status === 429) return 'Too many requests right now. Try again shortly.'
  if (status >= 500) return 'Mi-Llama could not complete that right now. Try again shortly.'
  return 'Mi-Llama could not complete that request. Check your work and try again.'
}

export class AuthClient {
  constructor(config) {
    this.supabaseUrl = config.supabase_url
    this.publishableKey = config.supabase_publishable_key
    this.session = readStoredSession()
    this.refreshPromise = null
  }

  static async create() {
    if (!sharedClientPromise) {
      sharedClientPromise = (async () => {
        const response = await fetch('/api/client-config', {
          headers: { Accept: 'application/json' },
          cache: 'no-store',
        })
        if (!response.ok) {
          throw new AuthError('Sign-in is unavailable in this workspace.', response.status)
        }
        return new AuthClient(await response.json())
      })()
    }
    try {
      return await sharedClientPromise
    } catch (error) {
      sharedClientPromise = null
      throw error
    }
  }

  get user() {
    return this.session?.user || null
  }

  get signedIn() {
    return Boolean(this.session?.access_token && this.session?.refresh_token)
  }

  async signIn(email, password) {
    const response = await fetch(`${this.supabaseUrl}/auth/v1/token?grant_type=password`, {
      method: 'POST',
      headers: {
        apikey: this.publishableKey,
        'Content-Type': 'application/json',
        Accept: 'application/json',
      },
      body: JSON.stringify({ email, password }),
    })
    if (!response.ok) {
      const message = await responseError(response, 'Sign in failed')
      throw new AuthError(authMessage(message, response.status, 'Could not sign in. Check your details and try again.'), response.status)
    }
    this.session = await response.json()
    storeSession(this.session)
    return this.session
  }

  async signOut() {
    const accessToken = this.session?.access_token
    try {
      if (accessToken) {
        await fetch(`${this.supabaseUrl}/auth/v1/logout?scope=local`, {
          method: 'POST',
          headers: {
            apikey: this.publishableKey,
            Authorization: `Bearer ${accessToken}`,
          },
        })
      }
    } finally {
      this.session = null
      storeSession(null)
    }
  }

  async refresh() {
    if (!this.session?.refresh_token) {
      throw new AuthError('Your session has ended. Sign in again.', 401)
    }
    if (this.refreshPromise) return this.refreshPromise

    this.refreshPromise = (async () => {
      const response = await fetch(`${this.supabaseUrl}/auth/v1/token?grant_type=refresh_token`, {
        method: 'POST',
        headers: {
          apikey: this.publishableKey,
          'Content-Type': 'application/json',
          Accept: 'application/json',
        },
        body: JSON.stringify({ refresh_token: this.session.refresh_token }),
      })
      if (!response.ok) {
        this.session = null
        storeSession(null)
        throw new AuthError('Your session has ended. Sign in again.', response.status)
      }
      this.session = await response.json()
      storeSession(this.session)
      return this.session
    })()

    try {
      return await this.refreshPromise
    } finally {
      this.refreshPromise = null
    }
  }

  async accessToken() {
    if (!this.session?.access_token) {
      throw new AuthError('Sign in to continue.', 401)
    }
    const now = Math.floor(Date.now() / 1000)
    if (!this.session.expires_at || this.session.expires_at - now <= REFRESH_SKEW_SECONDS) {
      await this.refresh()
    }
    return this.session.access_token
  }

  async apiFetch(path, options = {}, retry = true) {
    if (apiFetchInterceptor) {
      return apiFetchInterceptor({
        client: this,
        path,
        options,
        retry,
        next: (nextPath = path, nextOptions = options, nextRetry = retry) =>
          this._apiFetchDirect(nextPath, nextOptions, nextRetry),
      })
    }
    return this._apiFetchDirect(path, options, retry)
  }

  async _apiFetchDirect(path, options = {}, retry = true) {
    const token = await this.accessToken()
    const headers = new Headers(options.headers || {})
    headers.set('Authorization', `Bearer ${token}`)
    headers.set('Accept', 'application/json')
    if (options.body && !headers.has('Content-Type')) headers.set('Content-Type', 'application/json')

    let response = await fetch(path, { ...options, headers })
    if (response.status === 401 && retry) {
      await this.refresh()
      response = await this._apiFetchDirect(path, options, false)
    }
    return response
  }

  async apiJson(path, options = {}) {
    const response = await this.apiFetch(path, options)
    if (!response.ok) {
      await response.text()
      throw new AuthError(apiErrorMessage(response.status), response.status)
    }
    if (response.status === 204) return null
    return response.json()
  }
}
