// "Apps" tab: catalog of known applications grouped by category; connecting one creates a folder.
import { api, on } from './bridge.js';
import { t } from './i18n.js';
import { getCatalog, store } from './state.js';
import { button, confirmDialog, h, ico, toast } from './ui.js';

export function createAppsPane({ onOpenFolder }) {
  let category = 'all';
  let query = '';
  let scanning = false;
  const el = h('div', { class: 'apps-pane' });
  const search = h('input', { class: 'input sm search-input', type: 'search', spellcheck: 'false' });
  search.addEventListener('input', () => { query = search.value.trim().toLowerCase(); render(); });
  const cats = h('div', { class: 'cat-chips' });
  const rescanBtn = button({ label: '', iconName: 'refresh', kind: 'sm', onclick: () => scan(true) });
  const grid = h('div', { class: 'apps-scroll' });
  el.append(
    h('div', { class: 'apps-toolbar' },
      h('div', { class: 'search-wrap' }, ico('search', 15, 'search-ico'), search),
      rescanBtn),
    cats,
    grid);

  on('apps_status', (statuses) => {
    if (store.catalog) store.catalog.status = statuses;
    scanning = false;
    rescanBtn.classList.remove('spinning');
    render();
  });

  function scan() {
    if (scanning) return;
    scanning = true;
    rescanBtn.classList.add('spinning');
    api.detect_apps().catch((err) => {
      scanning = false;
      rescanBtn.classList.remove('spinning');
      toast(err.message, 'error');
    });
    render();
  }

  function statusOf(app) {
    const status = store.catalog?.status?.[app.id];
    if (app.kind === 'pack') return 'builtin';
    if (!status) return scanning ? 'unknown' : (app.web ? 'web' : 'unknown');
    return status;
  }

  function card(app) {
    const connected = store.catalog.connected?.[app.id];
    const status = statusOf(app);
    const tile = h('div', { class: `app-tile ${app.kind === 'pack' ? 'pack' : ''}`, style: { '--brand': app.color } },
      h('span', { class: 'app-abbr' }, app.abbr), h('span', { class: 'app-brand' }));
    const action = connected
      ? h('div', { class: 'app-actions' },
        button({ label: t('apps.connected'), iconName: 'check', kind: 'sm connected', title: t('apps.open'),
          onclick: () => onOpenFolder(connected) }),
        h('span', { class: 'grow' }),
        h('button', { type: 'button', class: 'btn icon ghost sm', title: t('apps.disconnect'), onclick: () => disconnect(app) }, ico('unlink', 15)))
      : h('div', { class: 'app-actions' }, button({ label: t('apps.connect'), iconName: 'plus', kind: 'sm', onclick: () => connect(app) }));
    return h('div', { class: `app-card ${connected ? 'is-connected' : ''}` },
      h('div', { class: 'app-top' },
        tile,
        h('div', { class: 'app-info' },
          h('div', { class: 'app-name', title: app.name }, app.name),
          h('div', { class: `app-status st-${status}`, title: app.desc || '' }, h('span', { class: 'status-dot' }),
            h('span', { class: 'app-status-text' }, app.desc && app.kind === 'pack' ? app.desc : t(`apps.status.${status}`))))),
      h('div', { class: 'app-bottom' }, action));
  }

  async function connect(app) {
    try {
      const path = await api.connect_app(app.id);
      store.catalog.connected = { ...store.catalog.connected, [app.id]: path };
      toast(t('apps.connected.toast', { name: app.name }), 'ok');
      render();
    } catch (err) { toast(err.message, 'error'); }
  }

  async function disconnect(app) {
    const ok = await confirmDialog({ title: t('apps.disconnect.title', { name: app.name }), text: t('apps.disconnect.text'),
      ok: t('apps.disconnect'), danger: true });
    if (!ok) return;
    try {
      await api.disconnect_app(app.id);
      const next = { ...store.catalog.connected };
      delete next[app.id];
      store.catalog.connected = next;
      render();
    } catch (err) { toast(err.message, 'error'); }
  }

  function filtered(apps) {
    if (!query) return apps;
    return apps.filter((a) => a.name.toLowerCase().includes(query) || a.id.includes(query));
  }

  function render() {
    const catalog = store.catalog;
    if (!catalog) return;
    cats.replaceChildren(
      h('button', { type: 'button', class: `cat ${category === 'all' ? 'active' : ''}`, onclick: () => { category = 'all'; render(); } }, t('apps.all')),
      ...catalog.categories.map((c) => h('button', { type: 'button', class: `cat ${category === c.id ? 'active' : ''}`,
        onclick: () => { category = c.id; render(); } }, c.name)));
    const sections = [];
    const cats_ = category === 'all' ? catalog.categories : catalog.categories.filter((c) => c.id === category);
    for (const cat of cats_) {
      let apps = catalog.apps.filter((a) => (category === 'all' && cat.id !== 'popular'
        ? a.categories[0] === cat.id : a.categories.includes(cat.id)));
      apps = filtered(apps);
      if (!apps.length) continue;
      sections.push(h('section', { class: 'apps-section' },
        h('div', { class: 'apps-section-head' }, h('h3', {}, cat.name), h('span', { class: 'count mono' }, String(apps.length))),
        h('div', { class: 'apps-grid' }, apps.map(card))));
    }
    if (!sections.length) sections.push(h('div', { class: 'apps-empty' }, t('apps.empty')));
    grid.replaceChildren(...sections);
  }

  function renderTexts() {
    search.placeholder = t('apps.search');
    rescanBtn.title = t('apps.rescan');
    rescanBtn.querySelector('.btn-label')?.remove();
    rescanBtn.append(h('span', { class: 'btn-label' }, t('apps.rescan')));
    render();
  }

  return {
    el,
    renderTexts,
    async show() {
      try {
        await getCatalog(true);
        render();
        if (!store.catalog.status || !Object.keys(store.catalog.status).length) scan();
      } catch (err) { toast(err.message, 'error'); }
    },
    render,
  };
}
