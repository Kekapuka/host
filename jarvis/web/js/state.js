// Shared client-side state with tiny subscriptions.
import { api } from './bridge.js';

export const store = {
  settings: {},
  state: { mic: false, phase: 'off', error: '' },
  history: [],
  version: '',
  mode: '',
  platform: '',
  dataDir: '',
  catalog: null,
};

const watchers = new Map();

export function watch(key, fn) {
  if (!watchers.has(key)) watchers.set(key, []);
  watchers.get(key).push(fn);
}

export function set(key, value) {
  store[key] = value;
  for (const fn of watchers.get(key) || []) {
    try { fn(value); } catch (err) { console.error(err); }
  }
}

export async function updateSettings(patch) {
  const settings = await api.update_settings(patch);
  set('settings', settings);
  return settings;
}

let catalogPromise = null;

export function getCatalog(force = false) {
  if (!catalogPromise || force) {
    catalogPromise = api.catalog().then((data) => {
      store.catalog = data;
      return data;
    }).catch((err) => {
      catalogPromise = null;
      throw err;
    });
  }
  return catalogPromise;
}

export function appName(id) {
  const app = store.catalog?.apps?.find((a) => a.id === id);
  return app ? app.name : id;
}
