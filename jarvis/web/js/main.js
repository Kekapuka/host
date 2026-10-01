// Entry point: connects to the core, builds the layout and routes between pages.
import { createAppsPane } from './apps.js';
import { api, connect, on, startEvents } from './bridge.js';
import { createEditorPane } from './editor.js';
import { createHome } from './home.js';
import { logo } from './icons.js';
import { setLang, t } from './i18n.js';
import { createSettings } from './settings.js';
import { getCatalog, set, store, updateSettings, watch } from './state.js';
import { h, ico, segmented, toast } from './ui.js';

const PAGES = ['home', 'editor', 'settings'];
let page = 'home';
let editorTab = 'editor';

// --- theme & animations --------------------------------------------------------------------
function applyTheme(theme) {
  document.documentElement.dataset.theme = theme === 'dark' ? 'dark' : 'light';
}

function switchTheme(theme, ev) {
  const animate = store.settings.animations && document.startViewTransition && ev;
  if (animate) {
    const x = ev.clientX || window.innerWidth / 2;
    const y = ev.clientY || window.innerHeight / 2;
    document.documentElement.style.setProperty('--vt-x', `${x}px`);
    document.documentElement.style.setProperty('--vt-y', `${y}px`);
    document.startViewTransition(() => applyTheme(theme));
  } else {
    applyTheme(theme);
  }
  updateSettings({ theme }).catch((err) => toast(err.message, 'error'));
}

function applyAnimations(on) {
  document.documentElement.classList.toggle('no-anim', !on);
}

// --- layout --------------------------------------------------------------------------------
const navItems = {};
const sideMic = h('button', { class: 'side-mic', type: 'button' }, h('span', { class: 'side-mic-dot' }), h('span', { class: 'side-mic-text' }));
const sideVersion = h('div', { class: 'side-version mono' });
const offline = h('div', { class: 'offline', hidden: true });

function buildSidebar() {
  const nav = h('nav', { class: 'nav' });
  const icons = { home: 'home', editor: 'editor', settings: 'settings' };
  for (const id of PAGES) {
    const btn = h('button', { class: 'nav-item', type: 'button', dataset: { page: id }, onclick: () => navigate(id) },
      h('span', { class: 'nav-ico' }, ico(icons[id], 20)), h('span', { class: 'nav-label' }));
    navItems[id] = btn;
    nav.append(btn);
  }
  sideMic.addEventListener('click', () => api.set_mic(!store.state.mic).then(onState).catch((e) => toast(e.message, 'error')));
  return h('aside', { class: 'sidebar' },
    h('div', { class: 'brand' }, h('span', { class: 'brand-logo', html: logo('') }), h('span', { class: 'brand-name' }, 'JARVIS')),
    nav,
    h('div', { class: 'side-foot' }, sideMic, sideVersion));
}

const home = createHome({ onThemeToggle: switchTheme });
const editorPane = createEditorPane();
const appsPane = createAppsPane({ onOpenFolder: (path) => { setEditorTab('editor'); editorPane.open(path); } });
const settingsPage = createSettings({ onThemeToggle: switchTheme });

const editorEyebrow = h('div', { class: 'eyebrow' });
const editorTitle = h('h1', { class: 'page-title' });
const editorTabsSlot = h('div', { class: 'page-tabs' });
const editorPage = h('section', { class: 'layer page-layer', id: 'page-editor' },
  h('header', { class: 'page-head' }, h('div', {}, editorEyebrow, editorTitle), editorTabsSlot),
  h('div', { class: 'page-body editor-body', dataset: { tab: 'editor' } }, editorPane.el, appsPane.el));

function setEditorTab(tab) {
  editorTab = tab;
  editorPage.querySelector('.editor-body').dataset.tab = tab;
  editorTabsSlot.firstChild?.set?.(tab);
  if (tab === 'apps') appsPane.show();
  else editorPane.load();
}

const stage = h('main', { class: 'stage', dataset: { page: 'home' } },
  h('div', { class: 'backdrop' }), home.el, editorPage, settingsPage.el);

async function navigate(target) {
  if (!PAGES.includes(target) || target === page) return;
  if (page === 'editor' && editorPane.hasUnsaved()) {
    const { confirmDialog } = await import('./ui.js');
    if (!(await confirmDialog({ title: t('editor.unsaved'), text: t('editor.unsaved.leave') }))) return;
  }
  page = target;
  stage.dataset.page = target;
  stage.classList.toggle('overlay', target !== 'home');
  for (const id of PAGES) {
    navItems[id].classList.toggle('active', id === target);
    navItems[id].setAttribute('aria-current', id === target ? 'page' : 'false');
  }
  editorPage.classList.toggle('active', target === 'editor');
  settingsPage.el.classList.toggle('active', target === 'settings');
  if (target === 'editor') setEditorTab(editorTab);
  if (target === 'settings') settingsPage.render();
}

function renderTexts() {
  for (const id of PAGES) navItems[id].querySelector('.nav-label').textContent = t(`nav.${id}`);
  editorEyebrow.textContent = t('editor.eyebrow');
  editorTitle.textContent = t('editor.title');
  editorTabsSlot.replaceChildren(segmented([
    { value: 'editor', label: t('editor.tab.editor'), icon: 'list' },
    { value: 'apps', label: t('editor.tab.apps'), icon: 'grid' },
  ], editorTab, (v) => setEditorTab(v), 'tabs'));
  offline.textContent = t('common.lost');
  home.renderTexts();
  editorPane.renderTexts();
  appsPane.renderTexts();
  if (page === 'settings') settingsPage.render();
  renderSideMic();
  document.title = 'Jarvis';
}

function renderSideMic() {
  const st = store.state;
  sideMic.classList.toggle('on', !!st.mic);
  sideMic.dataset.phase = st.phase || 'off';
  sideMic.querySelector('.side-mic-text').textContent = st.mic ? t(`phase.${st.phase || 'listening'}`) : t('phase.off');
}

function onState(state) {
  store.state = { ...store.state, ...state };
  home.applyState(store.state);
  renderSideMic();
}

async function fillAppList() {
  try {
    const catalog = await getCatalog();
    let list = document.getElementById('jarvis-apps');
    if (!list) {
      list = h('datalist', { id: 'jarvis-apps' });
      document.body.append(list);
    }
    list.replaceChildren(h('option', { value: '{app}' }, t('field.app.spoken')), h('option', { value: '@browser' }, t('field.app.browser')),
      ...catalog.apps.filter((a) => a.kind !== 'pack').map((a) => h('option', { value: a.id }, a.name)));
  } catch { /* catalog is optional for the datalist */ }
}

// --- boot ----------------------------------------------------------------------------------
async function boot() {
  const root = document.getElementById('app');
  try {
    await connect();
  } catch {
    root.replaceChildren(h('div', { class: 'boot-error' }, h('div', { class: 'empty-art big', html: logo('') }), t('common.lost')));
    return;
  }
  const init = await api.ready();
  store.version = init.version;
  store.mode = init.mode;
  store.platform = init.platform;
  store.dataDir = init.data_dir;
  store.history = init.history || [];
  store.state = init.state;
  setLang(init.settings.language);
  applyTheme(init.settings.theme);
  applyAnimations(init.settings.animations);
  set('settings', init.settings);

  root.replaceChildren(buildSidebar(), stage, offline);
  sideVersion.textContent = `v${init.version}`;
  renderTexts();
  home.renderHistory();
  onState(init.state);
  navItems.home.classList.add('active');
  requestAnimationFrame(() => document.body.classList.add('ready'));
  fillAppList();

  let lang = init.settings.language;
  watch('settings', (s) => {
    applyTheme(s.theme);
    applyAnimations(s.animations);
    if (s.language !== lang) {
      lang = s.language;
      setLang(lang);
      getCatalog(true).then(fillAppList).catch(() => {});
      renderTexts();
      home.renderHistory();
    } else {
      home.applySettings(s);
    }
  });

  on('settings', (s) => set('settings', s));
  on('state', onState);
  on('level', (v) => home.setLevel(v));
  on('heard', (data) => home.showHeard(data));
  on('history_add', (entry) => home.addEntry(entry));
  on('history_update', (entry) => home.updateEntry(entry));
  on('history_clear', () => home.clearHistory());
  on('tree_changed', () => { if (page === 'editor' && editorTab === 'editor') editorPane.onTreeChanged(); });
  on('toast', (data) => toast(data.text, data.kind || 'info', 5000));
  on('navigate', (target) => navigate(target === 'editor' ? 'editor' : target));
  on('__online', (online) => { offline.hidden = !!online; });
  startEvents(init.last_event || 0);

  document.addEventListener('keydown', (ev) => {
    if (ev.ctrlKey && ev.key.toLowerCase() === 's' && page === 'editor') {
      ev.preventDefault();
      document.querySelector('#page-editor .save-btn:not([disabled])')?.click();
    }
    if (ev.altKey && ['1', '2', '3'].includes(ev.key)) {
      ev.preventDefault();
      navigate(PAGES[Number(ev.key) - 1]);
    }
    if (ev.key === 'Escape' && page !== 'home' && !document.querySelector('.modal-backdrop') && !document.querySelector('.menu')) {
      navigate('home');
    }
  });
}

boot().catch((err) => {
  console.error(err);
  toast(err.message || String(err), 'error', 8000);
});
