/* ─────────────────────────────────────────────
   The Lot Legends — frontend API client
   Stores the JWT in localStorage and exposes a
   tiny fetch wrapper used by all pages.
   ───────────────────────────────────────────── */
(() => {
  const TOKEN_KEY = 'lotlegends_token';

  const api = {
    base: (window.LOTLEGENDS_API || '') + '/api',

    /** Turn FastAPI / Pydantic `detail` into a user-visible string. */
    _formatDetail(detail) {
      if (detail == null) return null;
      if (typeof detail === 'string') return detail;
      if (Array.isArray(detail)) {
        return detail
          .map((e) => {
            if (typeof e === 'string') return e;
            if (e && typeof e.msg === 'string') return e.msg;
            if (e && typeof e.message === 'string') return e.message;
            return JSON.stringify(e);
          })
          .filter(Boolean)
          .join(' — ');
      }
      if (typeof detail === 'object' && detail.message) {
        return typeof detail.message === 'string' ? detail.message : JSON.stringify(detail.message);
      }
      return null;
    },

    getToken() {
      try { return localStorage.getItem(TOKEN_KEY); }
      catch { return null; }
    },
    setToken(t) {
      try { t ? localStorage.setItem(TOKEN_KEY, t) : localStorage.removeItem(TOKEN_KEY); }
      catch {}
    },
    isAuthed() { return !!this.getToken(); },
    logout() {
      this.setToken(null);
      window.location.href = 'login.html';
    },

    async request(path, { method = 'GET', body, auth = true, headers = {} } = {}) {
      const h = { 'Content-Type': 'application/json', ...headers };
      if (auth) {
        const token = this.getToken();
        if (token) h['Authorization'] = `Bearer ${token}`;
      }

      const res = await fetch(this.base + path, {
        method,
        headers: h,
        body: body ? JSON.stringify(body) : undefined,
      });

      let data = null;
      const text = await res.text();
      try { data = text ? JSON.parse(text) : null; } catch { data = text; }

      if (!res.ok) {
        const fromDetail = this._formatDetail(data && data.detail);
        const msg = fromDetail || (typeof data === 'string' && data) || res.statusText
          || (res.status ? `HTTP ${res.status}` : 'Request failed');
        const err = new Error(msg);
        err.status = res.status;
        err.data = data;
        if (res.status === 401 && auth) {
          api.setToken(null);
        }
        throw err;
      }
      return data;
    },

    register(payload)        { return this.request('/auth/register', { method: 'POST', body: payload, auth: false }); },
    previewClaim(mt_id)      { return this.request(`/auth/preview-claim/${encodeURIComponent(mt_id)}`, { auth: false }); },
    login(email, password)   { return this.request('/auth/login',    { method: 'POST', body: { email, password }, auth: false }); },
    me()                     { return this.request('/me'); },
    progress()               { return this.request('/me/progress'); },
    lots(limit = 20)         { return this.request(`/me/lots?limit=${limit}`); },
    addLot(payload)          { return this.request('/me/lots',  { method: 'POST', body: payload }); },
    claims()                 { return this.request('/me/claims'); },
    claim(tier_key)          { return this.request('/me/claims', { method: 'POST', body: { tier_key } }); },
    leaderboard(limit = 10)  { return this.request(`/leaderboard?limit=${limit}`, { auth: false }); },
    tiers()                  { return this.request('/tiers', { auth: false }); },

    async _uploadCsv(path, file) {
      const fd = new FormData();
      fd.append('file', file);
      const headers = {};
      const token = this.getToken();
      if (token) headers['Authorization'] = `Bearer ${token}`;
      const res = await fetch(this.base + path, { method: 'POST', headers, body: fd });
      const text = await res.text();
      let data = null;
      try { data = text ? JSON.parse(text) : null; } catch { data = text; }
      if (!res.ok) {
        const msg = (data && data.detail) || res.statusText || 'Upload failed';
        const err = new Error(typeof msg === 'string' ? msg : 'Upload failed');
        err.status = res.status;
        err.data = data;
        throw err;
      }
      return data;
    },
    adminPreviewCsv(file)    { return this._uploadCsv('/admin/csv/preview', file); },
    adminImportCsv(file)     { return this._uploadCsv('/admin/csv/import', file); },
    adminImports()           { return this.request('/admin/csv/imports'); },
    adminUsers()             { return this.request('/admin/users'); },
    adminUpdateUser(id, body){ return this.request(`/admin/users/${id}`, { method: 'PATCH', body }); },
    adminCreatePlaceholders(mt_ids, name_prefix = 'Client') {
      return this.request('/admin/users/placeholder', { method: 'POST', body: { mt_ids, name_prefix } });
    },
  };

  /**
   * Redirect to login.html if the page requires auth and there is no token.
   * Pages call requireAuth() near the top of their inline script.
   */
  api.requireAuth = function () {
    if (!api.isAuthed()) {
      const here = encodeURIComponent(window.location.pathname.replace(/^\//, ''));
      window.location.href = `login.html?next=${here}`;
      return false;
    }
    return true;
  };

  window.LotLegends = api;
})();
