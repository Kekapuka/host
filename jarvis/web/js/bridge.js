// Connection to the Python core: pywebview's JS API inside the app window,
// or HTTP + long polling in browser mode (python main.py --browser).
const handlers = new Map();
let mode = null;
let lastEvent = 0;

function dispatch(events) {
  for (const evt of events) {
    if (evt.id && evt.id <= lastEvent && mode === 'http') continue;
    if (evt.id) lastEvent = Math.max(lastEvent, evt.id);
    for (const fn of handlers.get(evt.type) || []) {
      try { fn(evt.data, evt); } catch (err) { console.error(err); }
    }
    for (const fn of handlers.get('*') || []) {
      try { fn(evt.data, evt); } catch (err) { console.error(err); }
    }
  }
}

window.__jarvis = { dispatch };

export function on(type, fn) {
  if (!handlers.has(type)) handlers.set(type, []);
  handlers.get(type).push(fn);
}

async function callHttp(name, args) {
  const res = await fetch(`/api/${name}`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json', 'X-Jarvis-Token': window.__JARVIS_TOKEN__ },
    body: JSON.stringify({ args }),
  });
  const data = await res.json();
  if (!data.ok) throw new Error(data.error || 'error');
  return data.result;
}

async function callWebview(name, args) {
  const fn = window.pywebview?.api?.[name];
  if (!fn) throw new Error(`API ${name} unavailable`);
  try {
    return await fn(...args);
  } catch (err) {
    throw new Error(err?.message || String(err));
  }
}

export function call(name, ...args) {
  return mode === 'http' ? callHttp(name, args) : callWebview(name, args);
}

// api.someMethod(a, b) -> Promise
export const api = new Proxy({}, { get: (_, name) => (...args) => call(name, ...args) });

async function pollLoop() {
  let failures = 0;
  for (;;) {
    try {
      const url = `/api/events?after=${lastEvent}&token=${encodeURIComponent(window.__JARVIS_TOKEN__)}`;
      const res = await fetch(url, { cache: 'no-store' });
      const data = await res.json();
      if (data.ok) {
        if (data.last < lastEvent) lastEvent = 0; // core restarted
        dispatch(data.events || []);
        failures = 0;
        dispatch([{ type: '__online', data: true }]);
      }
    } catch (err) {
      failures += 1;
      if (failures === 3) dispatch([{ type: '__online', data: false }]);
      await new Promise((r) => setTimeout(r, Math.min(5000, 500 * failures)));
    }
  }
}

export function startEvents(fromId) {
  lastEvent = fromId || 0;
  if (mode === 'http') pollLoop();
}

export function connect(timeoutMs = 20000) {
  if (window.__JARVIS_TOKEN__) {
    mode = 'http';
    return Promise.resolve(mode);
  }
  return new Promise((resolve, reject) => {
    const done = () => { mode = 'webview'; resolve(mode); };
    if (window.pywebview?.api?.ready) return done();
    window.addEventListener('pywebviewready', done, { once: true });
    setTimeout(() => (mode ? null : reject(new Error('timeout'))), timeoutMs);
  });
}
