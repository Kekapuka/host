// Command editor: folder tree (one folder = one app) and the command / folder forms.
import { api } from './bridge.js';
import { logo } from './icons.js';
import { t } from './i18n.js';
import { getCatalog, store } from './state.js';
import {
  button, chipsInput, clear, confirmDialog, h, ico, iconButton, popupMenu, promptDialog, selectDialog, toast, toggle,
} from './ui.js';

const BROWSERS = ['auto', 'default', 'chrome', 'yandex', 'edge', 'firefox', 'opera', 'operagx', 'brave'];
const ENGINES = ['google', 'yandex', 'youtube', 'bing', 'duckduckgo', 'vk'];
const MEDIA = ['play_pause', 'next', 'prev', 'stop', 'volume_up', 'volume_down', 'mute'];
const SYSTEM = ['lock', 'shutdown', 'restart', 'sleep', 'logoff', 'screenshot', 'show_desktop', 'empty_recycle_bin', 'task_manager'];
const JARVIS = ['silent_on', 'silent_off', 'theme_dark', 'theme_light', 'mic_off', 'volume', 'stop', 'open_settings', 'open_editor', 'open_home'];

export const ACTIONS = {
  open_app: { icon: 'window', fields: [['app', 'app'], ['args', 'text']], defaults: { app: '' } },
  close_app: { icon: 'x', fields: [['app', 'app'], ['force', 'switch']], defaults: { app: '' } },
  focus_app: { icon: 'cursor', fields: [['app', 'app']], defaults: { app: '' } },
  open_url: { icon: 'globe', fields: [['url', 'text'], ['browser', 'browser']], defaults: { url: 'https://', browser: 'auto' } },
  search_web: { icon: 'search', fields: [['query', 'text'], ['engine', 'engine'], ['browser', 'browser']], defaults: { query: '{query}', engine: 'google', browser: 'auto' } },
  hotkey: { icon: 'keyboard', fields: [['keys', 'hotkey']], defaults: { keys: '' } },
  type_text: { icon: 'edit', fields: [['text', 'textarea']], defaults: { text: '{text}' } },
  media: { icon: 'music', fields: [['key', 'media'], ['times', 'number']], defaults: { key: 'play_pause' } },
  system_volume: { icon: 'volume', fields: [['level', 'text']], defaults: { level: '{level}' } },
  system: { icon: 'power', fields: [['op', 'system']], defaults: { op: 'lock' } },
  wait: { icon: 'wait', fields: [['seconds', 'number']], defaults: { seconds: 1 } },
  say: { icon: 'message', fields: [['text', 'text']], defaults: { text: '' } },
  click_element: { icon: 'cursor', fields: [['names', 'chips'], ['timeout', 'number']], defaults: { names: [], timeout: 6 } },
  ask_ai: { icon: 'spark', fields: [['prompt', 'text']], defaults: { prompt: '{_text}' } },
  run_command: { icon: 'command', fields: [['path', 'command']], defaults: { path: '' } },
  run: { icon: 'terminal', fields: [['command', 'text'], ['hidden', 'switch']], defaults: { command: '', hidden: true } },
  jarvis: { icon: 'bolt', fields: [['op', 'jarvis'], ['value', 'text', (a) => a.op === 'volume']], defaults: { op: 'silent_on' } },
};

const EXPANDED_KEY = 'jarvis.editor.expanded';

function loadExpanded() {
  try { return new Set(JSON.parse(localStorage.getItem(EXPANDED_KEY) || '[]')); } catch { return new Set(); }
}

function saveExpanded(set) {
  try { localStorage.setItem(EXPANDED_KEY, JSON.stringify([...set])); } catch { /* storage unavailable */ }
}

function clone(v) {
  return JSON.parse(JSON.stringify(v));
}

function parentOf(path) {
  const idx = path.lastIndexOf('/');
  return idx < 0 ? '' : path.slice(0, idx);
}

function crumbs(path) {
  return path.replace(/\.json$/, '').split('/');
}

export function createEditorPane() {
  let tree = [];
  let selected = null; // path
  let item = null; // read_item result
  let draft = null; // editable copy
  let dirty = false;
  let query = '';
  const expanded = loadExpanded();

  const el = h('div', { class: 'editor-pane' });

  // --- left column: toolbar, tree, phrase tester --------------------------------------------
  const newFolderBtn = button({ label: '', iconName: 'folderPlus', kind: 'sm', onclick: () => createFolder('') });
  const newCmdBtn = button({ label: '', iconName: 'filePlus', kind: 'sm', onclick: () => createCommand(currentFolder()) });
  const search = h('input', { class: 'input sm search-input', type: 'search', spellcheck: 'false' });
  search.addEventListener('input', () => { query = search.value.trim().toLowerCase(); renderTree(); });
  const treeEl = h('div', { class: 'tree', role: 'tree' });
  const testerInput = h('input', { class: 'input sm', spellcheck: 'false' });
  const testerOut = h('div', { class: 'tester-out' });
  const testerTitle = h('div', { class: 'tester-title mono' });
  const testerBtn = iconButton('play', '', () => runTester(), 'sm');
  testerInput.addEventListener('keydown', (ev) => { if (ev.key === 'Enter') runTester(); });

  const treeCol = h('aside', { class: 'tree-col' },
    h('div', { class: 'tree-tools' }, newFolderBtn, newCmdBtn),
    h('div', { class: 'search-wrap' }, ico('search', 15, 'search-ico'), search),
    h('div', { class: 'tree-scroll' }, treeEl),
    h('div', { class: 'tester' }, testerTitle, h('div', { class: 'tester-row' }, testerInput, testerBtn), testerOut));

  const detail = h('section', { class: 'detail' });
  el.append(treeCol, detail);

  // --- tree ----------------------------------------------------------------------------------
  function matches(node) {
    if (!query) return true;
    if (node.name.toLowerCase().includes(query)) return true;
    if (node.type === 'command' && (node.trigger || '').toLowerCase().includes(query)) return true;
    if (node.type === 'folder') return node.children.some(matches);
    return false;
  }

  function renderTree() {
    clear(treeEl);
    if (!tree.length) {
      treeEl.append(h('div', { class: 'tree-empty' }, t('editor.tree.empty')));
      return;
    }
    const walk = (nodes, depth) => {
      for (const node of nodes) {
        if (!matches(node)) continue;
        treeEl.append(treeRow(node, depth));
        if (node.type === 'folder' && (expanded.has(node.path) || query)) walk(node.children, depth + 1);
      }
    };
    walk(tree, 0);
  }

  function treeRow(node, depth) {
    const isFolder = node.type === 'folder';
    const open = isFolder && (expanded.has(node.path) || !!query);
    const row = h('div', {
      class: `tree-row ${isFolder ? 'is-folder' : 'is-cmd'} ${selected === node.path ? 'selected' : ''}
        ${(isFolder ? node.meta?.enabled === false : node.enabled === false) ? 'disabled' : ''}`,
      role: 'treeitem', tabindex: '0', style: { '--depth': depth }, title: node.path,
    });
    const chev = h('span', { class: `tree-chev ${open ? 'open' : ''}` }, isFolder ? ico('chevron', 14) : null);
    const label = h('span', { class: 'tree-name' }, node.name);
    const badges = h('span', { class: 'tree-badges' });
    if (isFolder && node.children?.length) badges.append(h('span', { class: 'tree-count mono' }, String(countCommands(node))));
    if (!isFolder && node.confirm) badges.append(h('span', { class: 'tree-badge', title: t('editor.confirm') }, '?'));
    const more = iconButton('more', '', (ev) => { ev.stopPropagation(); rowMenu(more, node); }, 'ghost xs tree-more');
    row.append(chev, ico(isFolder ? (open ? 'folderOpen' : 'folder') : 'command', 16, 'tree-ico'), label, badges, more);
    row.addEventListener('click', () => {
      if (isFolder) toggleFolder(node.path, selected === node.path || !open);
      select(node.path);
    });
    row.addEventListener('keydown', (ev) => {
      if (ev.key === 'Enter') row.click();
      if (ev.key === 'Delete') removeItem(node);
      if (ev.key === 'F2') renameItem(node);
    });
    row.addEventListener('contextmenu', (ev) => { ev.preventDefault(); rowMenu(row, node); });
    return row;
  }

  function countCommands(node) {
    return node.children.reduce((n, c) => n + (c.type === 'folder' ? countCommands(c) : 1), 0);
  }

  function toggleFolder(path, open) {
    if (open) expanded.add(path); else expanded.delete(path);
    saveExpanded(expanded);
    renderTree();
  }

  function rowMenu(anchor, node) {
    const items = [];
    if (node.type === 'folder') {
      items.push({ label: t('editor.menu.newCmd'), icon: 'filePlus', action: () => createCommand(node.path) });
      items.push({ label: t('editor.menu.newSub'), icon: 'folderPlus', action: () => createFolder(node.path) });
      items.push('-');
    }
    items.push({ label: t('editor.menu.rename'), icon: 'edit', action: () => renameItem(node) });
    items.push({ label: t('editor.menu.duplicate'), icon: 'copy', action: () => duplicateItem(node) });
    items.push({ label: t('editor.menu.move'), icon: 'folderOpen', action: () => moveItem(node) });
    items.push('-');
    items.push({ label: t('editor.menu.delete'), icon: 'trash', danger: true, action: () => removeItem(node) });
    popupMenu(anchor, items);
  }

  function findNode(path, nodes = tree) {
    for (const n of nodes) {
      if (n.path === path) return n;
      if (n.type === 'folder') {
        const f = findNode(path, n.children);
        if (f) return f;
      }
    }
    return null;
  }

  function allFolders(nodes = tree, out = []) {
    for (const n of nodes) {
      if (n.type === 'folder') { out.push(n.path); allFolders(n.children, out); }
    }
    return out;
  }

  function allCommands(nodes = tree, out = []) {
    for (const n of nodes) {
      if (n.type === 'folder') allCommands(n.children, out);
      else out.push(n.path);
    }
    return out;
  }

  function currentFolder() {
    if (!selected) return '';
    const node = findNode(selected);
    if (!node) return '';
    return node.type === 'folder' ? node.path : parentOf(node.path);
  }

  function expandTo(path) {
    const parts = path.split('/');
    for (let i = 1; i < parts.length; i += 1) expanded.add(parts.slice(0, i).join('/'));
    saveExpanded(expanded);
  }

  async function loadTree() {
    try {
      tree = await api.tree();
    } catch (err) {
      toast(err.message, 'error');
      tree = [];
    }
    renderTree();
  }

  // --- tree operations ---------------------------------------------------------------------
  async function guardUnsaved() {
    if (!dirty) return true;
    const leave = await confirmDialog({ title: t('editor.unsaved'), text: t('editor.unsaved.leave'), ok: t('common.ok') });
    if (leave) dirty = false;
    return leave;
  }

  async function createFolder(parent) {
    if (!(await guardUnsaved())) return;
    const name = await promptDialog({ title: t('editor.prompt.folder'), label: t('editor.prompt.folder.label'), ok: t('common.create') });
    if (!name) return;
    try {
      const path = await api.create_folder(parent, name);
      if (parent) expanded.add(parent);
      expanded.add(path);
      saveExpanded(expanded);
      await loadTree();
      await select(path, true);
    } catch (err) { toast(err.message, 'error'); }
  }

  async function createCommand(parent) {
    if (!(await guardUnsaved())) return;
    const name = await promptDialog({ title: t('editor.prompt.command'), label: t('editor.prompt.command.label'), ok: t('common.create') });
    if (!name) return;
    try {
      const path = await api.create_command(parent, name);
      if (parent) { expandTo(path); }
      await loadTree();
      await select(path, true);
    } catch (err) { toast(err.message, 'error'); }
  }

  async function renameItem(node) {
    const name = await promptDialog({ title: t('editor.prompt.rename'), label: t('editor.prompt.rename.label'), value: node.name });
    if (!name || name === node.name) return;
    try {
      const path = await api.rename_item(node.path, name);
      if (expanded.has(node.path)) { expanded.delete(node.path); expanded.add(path); saveExpanded(expanded); }
      const wasSelected = selected && (selected === node.path || selected.startsWith(`${node.path}/`));
      await loadTree();
      if (wasSelected) { dirty = false; await select(selected.replace(node.path, path), true); }
    } catch (err) { toast(err.message, 'error'); }
  }

  async function duplicateItem(node) {
    try {
      const path = await api.duplicate_item(node.path);
      await loadTree();
      if (await guardUnsaved()) await select(path, true);
    } catch (err) { toast(err.message, 'error'); }
  }

  async function moveItem(node) {
    const folders = allFolders().filter((p) => p !== node.path && !p.startsWith(`${node.path}/`));
    const options = [{ value: '', label: `/ ${t('editor.menu.moveRoot')}` }, ...folders.map((p) => ({ value: p, label: p.split('/').join(' › ') }))];
    const dest = await selectDialog({ title: t('editor.prompt.move'), label: t('editor.prompt.move.label'), options, value: parentOf(node.path) });
    if (dest === null || dest === parentOf(node.path)) return;
    try {
      const path = await api.move_item(node.path, dest);
      if (dest) expandTo(`${dest}/x`);
      await loadTree();
      if (selected === node.path) { dirty = false; await select(path, true); }
    } catch (err) { toast(err.message, 'error'); }
  }

  async function removeItem(node) {
    const isFolder = node.type === 'folder';
    const ok = await confirmDialog({
      title: t('editor.delete.title', { name: node.name }),
      text: isFolder ? t('editor.delete.folder') : t('editor.delete.command'),
      ok: t('common.delete'),
      danger: true,
    });
    if (!ok) return;
    try {
      await api.delete_item(node.path);
      if (selected && (selected === node.path || selected.startsWith(`${node.path}/`))) {
        selected = null; item = null; draft = null; dirty = false;
        renderDetail();
      }
      await loadTree();
    } catch (err) { toast(err.message, 'error'); }
  }

  // --- selection / detail --------------------------------------------------------------------
  async function select(path, force = false) {
    if (!force && path === selected) return;
    if (!force && !(await guardUnsaved())) return;
    selected = path;
    renderTree();
    try {
      item = await api.read_item(path);
      draft = item.type === 'command' ? clone(item.data) : clone(item.meta || {});
      dirty = false;
    } catch (err) {
      item = null;
      toast(err.message, 'error');
    }
    renderDetail();
  }

  function setDirty(v = true) {
    dirty = v;
    detail.querySelector('.save-btn')?.toggleAttribute('disabled', !dirty);
    detail.querySelector('.dirty-note')?.classList.toggle('show', dirty);
  }

  function renderDetail() {
    clear(detail);
    if (!item) {
      detail.append(h('div', { class: 'detail-empty' },
        h('div', { class: 'empty-art big', html: logo('') }),
        h('div', { class: 'empty-title' }, t('editor.empty.title')),
        h('div', { class: 'empty-text' }, t('editor.empty.text'))));
      return;
    }
    if (item.type === 'folder') renderFolder();
    else renderCommand();
  }

  function detailHead(kindLabel, node) {
    const path = item.path;
    const parts = crumbs(path);
    const name = parts[parts.length - 1];
    const crumbEl = h('div', { class: 'crumbs mono' }, parts.slice(0, -1).map((p, i) => [
      i ? h('span', { class: 'crumb-sep' }, '/') : null,
      h('button', { type: 'button', class: 'crumb', onclick: () => select(parts.slice(0, i + 1).join('/')) }, p),
    ]));
    return h('div', { class: 'detail-head' },
      h('div', { class: 'detail-titles' },
        h('div', { class: 'eyebrow' }, kindLabel),
        h('h2', { class: 'detail-title' }, name),
        parts.length > 1 ? crumbEl : null),
      h('div', { class: 'detail-tools' },
        iconButton('edit', t('editor.menu.rename'), () => renameItem(node)),
        iconButton('copy', t('editor.menu.duplicate'), () => duplicateItem(node)),
        iconButton('trash', t('editor.menu.delete'), () => removeItem(node), 'ghost danger')));
  }

  function section(title, desc, ...body) {
    return h('div', { class: 'form-section' },
      h('div', { class: 'form-head' }, h('div', { class: 'form-title' }, title), desc ? h('div', { class: 'form-desc' }, desc) : null),
      ...body);
  }

  function switchRow(title, desc, checked, onchange) {
    return h('div', { class: 'switch-row' },
      h('div', { class: 'ctl-text' }, h('div', { class: 'ctl-title' }, title), desc ? h('div', { class: 'ctl-desc' }, desc) : null),
      toggle(checked, onchange));
  }

  // --- folder form ---------------------------------------------------------------------------
  async function renderFolder() {
    const node = findNode(item.path) || { path: item.path, name: item.name, type: 'folder', children: [] };
    const catalog = await getCatalog().catch(() => null);
    const meta = draft;
    const appSelect = h('select', { class: 'select' },
      h('option', { value: '' }, t('editor.folder.app.none')),
      (catalog?.categories || []).filter((c) => c.id !== 'defaults').map((cat) => h('optgroup', { label: cat.name },
        catalog.apps.filter((a) => a.categories[0] === cat.id).map((a) => h('option', { value: a.id }, a.name)))));
    appSelect.value = meta.app || '';
    appSelect.addEventListener('change', () => { meta.app = appSelect.value || undefined; setDirty(); });

    const pathInput = h('input', { class: 'input mono', spellcheck: 'false', placeholder: 'C:\\Program Files\\…\\app.exe' });
    pathInput.value = meta.path || '';
    pathInput.addEventListener('input', () => { meta.path = pathInput.value; setDirty(); });
    const browseBtn = button({ label: t('editor.folder.browse'), kind: 'sm', onclick: async () => {
      try {
        const file = await api.pick_file();
        if (file) { pathInput.value = file; meta.path = file; setDirty(); }
      } catch (err) { toast(err.message, 'error'); }
    } });
    const procInput = h('input', { class: 'input mono', spellcheck: 'false', placeholder: 'app.exe' });
    procInput.value = meta.process || '';
    procInput.addEventListener('input', () => { meta.process = procInput.value; setDirty(); });
    const aliases = chipsInput(meta.aliases || [], (v) => { meta.aliases = v; setDirty(); }, { placeholder: t('editor.triggers.add') });

    const saveBtn = button({ label: t('editor.save'), iconName: 'check', kind: 'primary save-btn', onclick: saveFolder });
    saveBtn.disabled = true;

    const children = (node.children || []).map((c) => h('button', { type: 'button', class: 'child-row', onclick: () => {
      if (c.type === 'folder') { expanded.add(c.path); saveExpanded(expanded); }
      select(c.path);
    } }, ico(c.type === 'folder' ? 'folder' : 'command', 16), h('span', { class: 'child-name' }, c.name),
      c.type === 'command' && c.trigger ? h('span', { class: 'child-trigger mono' }, `«${c.trigger}»`) : null,
      ico('chevron', 14, 'muted')));

    const appBlock = section(t('editor.folder.app'), t('editor.folder.app.desc'), appSelect);
    detail.append(
      detailHead(t('editor.folder'), node),
      h('div', { class: 'detail-body' },
        h('div', { class: 'quick-row' },
          button({ label: t('editor.menu.newCmd'), iconName: 'filePlus', kind: 'sm', onclick: () => createCommand(item.path) }),
          button({ label: t('editor.menu.newSub'), iconName: 'folderPlus', kind: 'sm', onclick: () => createFolder(item.path) })),
        appBlock,
        section(t('editor.folder.path'), t('editor.folder.path.desc'), h('div', { class: 'input-row' }, pathInput, browseBtn)),
        section(t('editor.folder.process'), t('editor.folder.process.desc'), procInput),
        section(t('editor.folder.aliases'), t('editor.folder.aliases.desc'), aliases),
        switchRow(t('editor.folder.enabled'), t('editor.folder.enabled.desc'), meta.enabled !== false,
          (v) => { meta.enabled = v; setDirty(); }),
        section(t('editor.folder.content'), t('editor.folder.items', { n: children.length }),
          h('div', { class: 'child-list' }, children))),
      h('div', { class: 'detail-foot' }, h('span', { class: 'dirty-note' }, t('editor.unsaved')), h('span', { class: 'grow' }), saveBtn));
  }

  async function saveFolder() {
    try {
      const meta = { ...draft };
      for (const k of ['path', 'process']) if (typeof meta[k] === 'string') meta[k] = meta[k].trim();
      item = await api.save_folder(item.path, meta);
      draft = clone(item.meta || {});
      setDirty(false);
      toast(t('editor.saved'), 'ok', 1600);
      await loadTree();
    } catch (err) { toast(err.message, 'error'); }
  }

  // --- command form ----------------------------------------------------------------------------
  function renderCommand() {
    const node = findNode(item.path) || { path: item.path, name: item.name, type: 'command' };
    const data = draft;
    const triggers = chipsInput(data.triggers, (v) => { data.triggers = v; setDirty(); },
      { placeholder: t('editor.triggers.add') });
    const actionsList = h('div', { class: 'actions-list' });
    const renderActions = () => {
      clear(actionsList);
      if (!data.actions.length) actionsList.append(h('div', { class: 'actions-empty' }, t('editor.actions.empty')));
      data.actions.forEach((action, idx) => actionsList.append(actionCard(action, idx, data, renderActions)));
    };
    renderActions();
    const addBtn = button({ label: t('editor.actions.add'), iconName: 'plus', kind: 'sm dashed', onclick: () => {
      popupMenu(addBtn, Object.keys(ACTIONS).map((type) => ({
        label: t(`action.${type}`), icon: ACTIONS[type].icon,
        action: () => { data.actions.push({ type, ...clone(ACTIONS[type].defaults) }); setDirty(); renderActions(); },
      })));
    } });
    const response = h('input', { class: 'input', spellcheck: 'false', placeholder: t('editor.response.placeholder') });
    response.value = data.response || '';
    response.addEventListener('input', () => { data.response = response.value; setDirty(); });

    const saveBtn = button({ label: t('editor.save'), iconName: 'check', kind: 'primary save-btn', onclick: saveCommand });
    saveBtn.disabled = true;
    const testBtn = button({ label: t('editor.test'), iconName: 'play', kind: '', onclick: async () => {
      testBtn.disabled = true;
      try {
        const res = await api.test_command(item.path, data);
        if (res.ok) toast(res.reply || t('editor.test.ok'), 'ok');
        else toast(res.error, 'error', 5000);
      } catch (err) { toast(err.message, 'error'); } finally { testBtn.disabled = false; }
    } });

    detail.append(
      detailHead(t('editor.command'), node),
      h('div', { class: 'detail-body' },
        section(t('editor.triggers'), t('editor.triggers.desc'), triggers),
        section(t('editor.actions'), t('editor.actions.desc'), actionsList, addBtn),
        section(t('editor.response'), t('editor.response.desc'), response),
        switchRow(t('editor.confirm'), t('editor.confirm.desc'), data.confirm, (v) => { data.confirm = v; setDirty(); }),
        switchRow(t('editor.enabled'), t('editor.enabled.desc'), data.enabled !== false, (v) => { data.enabled = v; setDirty(); })),
      h('div', { class: 'detail-foot' }, testBtn, h('span', { class: 'dirty-note' }, t('editor.unsaved')), h('span', { class: 'grow' }), saveBtn));
  }

  async function saveCommand() {
    try {
      item = await api.save_command(item.path, draft);
      draft = clone(item.data);
      setDirty(false);
      toast(t('editor.saved'), 'ok', 1600);
      await loadTree();
    } catch (err) { toast(err.message, 'error'); }
  }

  function actionCard(action, idx, data, rerender) {
    const def = ACTIONS[action.type] || { icon: 'info', fields: [] };
    const typeSelect = h('select', { class: 'select sm type-select' },
      Object.keys(ACTIONS).map((type) => h('option', { value: type }, t(`action.${type}`))));
    typeSelect.value = action.type;
    typeSelect.addEventListener('change', () => {
      data.actions[idx] = { type: typeSelect.value, ...clone(ACTIONS[typeSelect.value].defaults) };
      setDirty();
      rerender();
    });
    const move = (delta) => {
      const j = idx + delta;
      if (j < 0 || j >= data.actions.length) return;
      [data.actions[idx], data.actions[j]] = [data.actions[j], data.actions[idx]];
      setDirty();
      rerender();
    };
    const fields = h('div', { class: 'action-fields' });
    const renderFields = () => {
      clear(fields);
      for (const [key, kind, visible] of def.fields) {
        if (visible && !visible(action)) continue;
        fields.append(fieldControl(action, key, kind, renderFields));
      }
      fields.append(h('label', { class: 'opt-line' },
        toggle(!!action.optional, (v) => { if (v) action.optional = true; else delete action.optional; setDirty(); }),
        h('span', {}, t('editor.optional'))));
    };
    renderFields();
    return h('div', { class: 'action-card' },
      h('div', { class: 'action-head' },
        h('span', { class: 'action-num mono' }, String(idx + 1).padStart(2, '0')),
        ico(def.icon, 16, 'action-ico'),
        typeSelect,
        h('span', { class: 'grow' }),
        iconButton('arrowUp', t('editor.up'), () => move(-1), 'ghost xs'),
        iconButton('arrowDown', t('editor.down'), () => move(1), 'ghost xs'),
        iconButton('trash', t('common.delete'), () => { data.actions.splice(idx, 1); setDirty(); rerender(); }, 'ghost xs danger')),
      fields);
  }

  function fieldControl(action, key, kind, rerender) {
    const label = h('span', { class: 'field-label' }, t(`field.${key === 'key' ? 'key' : key}`));
    const wrap = h('label', { class: `field f-${kind}` }, label);
    const setValue = (v) => {
      if (v === '' || v === undefined || v === null) delete action[key];
      else action[key] = v;
      setDirty();
    };
    const select = (options, labelFn) => {
      const s = h('select', { class: 'select sm' }, options.map((o) => h('option', { value: o }, labelFn(o))));
      s.value = action[key] ?? options[0];
      s.addEventListener('change', () => { setValue(s.value); if (key === 'op') rerender(); });
      return s;
    };
    switch (kind) {
      case 'text': {
        const input = h('input', { class: 'input sm', spellcheck: 'false' });
        input.value = action[key] ?? '';
        input.addEventListener('input', () => setValue(input.value));
        wrap.append(input);
        break;
      }
      case 'textarea': {
        const ta = h('textarea', { class: 'input sm', rows: '2', spellcheck: 'false' });
        ta.value = action[key] ?? '';
        ta.addEventListener('input', () => setValue(ta.value));
        wrap.append(ta);
        break;
      }
      case 'number': {
        const input = h('input', { class: 'input sm', type: 'number', min: '0', step: key === 'seconds' ? '0.5' : '1' });
        input.value = action[key] ?? '';
        input.addEventListener('input', () => setValue(input.value === '' ? '' : Number(input.value)));
        wrap.append(input);
        break;
      }
      case 'switch':
        wrap.classList.add('inline');
        wrap.append(toggle(!!action[key], (v) => setValue(v ? true : '')));
        break;
      case 'browser':
        wrap.append(select(BROWSERS, (o) => (o === 'auto' || o === 'default' ? t(`browser.${o}`) : (store.catalog?.apps?.find((a) => a.id === o)?.name || o))));
        break;
      case 'engine':
        wrap.append(select(ENGINES, (o) => ({ google: 'Google', yandex: 'Яндекс', youtube: 'YouTube', bing: 'Bing', duckduckgo: 'DuckDuckGo', vk: 'VK' })[o]));
        break;
      case 'media':
        wrap.append(select(MEDIA, (o) => t(`media.${o}`)));
        break;
      case 'system':
        wrap.append(select(SYSTEM, (o) => t(`system.${o}`)));
        break;
      case 'jarvis':
        wrap.append(select(JARVIS, (o) => t(`jarvis.${o}`)));
        break;
      case 'app': {
        const input = h('input', { class: 'input sm mono', spellcheck: 'false', list: 'jarvis-apps', placeholder: t('field.app.folder') });
        input.value = action[key] ?? '';
        const hint = h('span', { class: 'field-hint' });
        const paint = () => {
          const v = input.value.trim();
          const app = store.catalog?.apps?.find((a) => a.id === v);
          hint.textContent = !v ? `→ ${t('field.app.folder')}` : v === '@browser' ? `→ ${t('field.app.browser')}`
            : /^\{.+\}$/.test(v) ? `→ ${t('field.app.spoken')}` : app ? `→ ${app.name}` : '';
        };
        paint();
        input.addEventListener('input', () => { setValue(input.value.trim()); paint(); });
        wrap.append(input, hint);
        break;
      }
      case 'hotkey': {
        const input = h('input', { class: 'input sm mono', spellcheck: 'false', placeholder: 'ctrl+t' });
        input.value = action[key] ?? '';
        input.addEventListener('input', () => setValue(input.value.trim()));
        const rec = button({ label: t('field.record'), iconName: 'keyboard', kind: 'sm' });
        rec.addEventListener('click', () => recordHotkey(input, rec, (v) => setValue(v)));
        wrap.append(h('div', { class: 'input-row' }, input, rec));
        break;
      }
      case 'chips':
        wrap.append(chipsInput(action[key] || [], (v) => setValue(v.length ? v : ''), { placeholder: t('field.names.add') }),
          h('span', { class: 'field-hint' }, t('field.names.desc')));
        break;
      case 'command': {
        const s = h('select', { class: 'select sm' }, h('option', { value: '' }, '—'),
          allCommands().map((p) => h('option', { value: p }, p.replace(/\.json$/, '').split('/').join(' › '))));
        s.value = action[key] ?? '';
        s.addEventListener('change', () => setValue(s.value));
        wrap.append(s);
        break;
      }
      default:
        break;
    }
    return wrap;
  }

  function recordHotkey(input, btn, done) {
    const original = input.value;
    btn.classList.add('recording');
    input.value = '';
    input.placeholder = t('field.recording');
    const names = { ' ': 'space', arrowleft: 'left', arrowright: 'right', arrowup: 'up', arrowdown: 'down', escape: 'esc',
      pageup: 'pageup', pagedown: 'pagedown', '+': 'plus', '-': 'minus', '=': 'plus', meta: 'win', os: 'win' };
    const onKey = (ev) => {
      ev.preventDefault();
      ev.stopPropagation();
      const key = ev.key.toLowerCase();
      if (['control', 'shift', 'alt', 'meta', 'os'].includes(key)) return;
      let main = names[key] || key;
      if (/^Key[A-Z]$/.test(ev.code)) main = ev.code.slice(3).toLowerCase();
      else if (/^Digit\d$/.test(ev.code)) main = ev.code.slice(5);
      else if (/^Numpad\d$/.test(ev.code)) main = `num${ev.code.slice(6)}`;
      const combo = [ev.ctrlKey && 'ctrl', ev.shiftKey && 'shift', ev.altKey && 'alt', ev.metaKey && 'win', main].filter(Boolean).join('+');
      input.value = combo;
      done(combo);
      stop();
    };
    const stop = () => {
      window.removeEventListener('keydown', onKey, true);
      btn.classList.remove('recording');
      input.placeholder = 'ctrl+t';
      if (!input.value) input.value = original;
    };
    window.addEventListener('keydown', onKey, true);
    setTimeout(() => { if (btn.classList.contains('recording')) stop(); }, 8000);
  }

  // --- tester ----------------------------------------------------------------------------------
  async function runTester() {
    const text = testerInput.value.trim();
    if (!text) return;
    try {
      const res = await api.match_phrase(text);
      testerOut.replaceChildren(...res.steps.map((s) => h('button', {
        type: 'button', class: `tester-step ${s.path ? 'ok' : 'none'}`,
        onclick: () => s.path && (expandTo(s.path), select(s.path)),
      }, h('span', { class: 'mono tester-text' }, `«${s.text}»`), ico('chevron', 12, 'muted'),
      h('span', {}, s.path ? s.path.replace(/\.json$/, '').split('/').join(' › ') : t('editor.tester.none')),
      Object.keys(s.captures || {}).length ? h('span', { class: 'mono tester-caps' },
        Object.entries(s.captures).map(([k, v]) => `${k}=${v}`).join(', ')) : null)));
    } catch (err) { toast(err.message, 'error'); }
  }

  // --- texts -------------------------------------------------------------------------------
  function renderTexts() {
    newFolderBtn.querySelector('.btn-label')?.remove();
    newFolderBtn.append(h('span', { class: 'btn-label' }, t('editor.newFolder')));
    newCmdBtn.querySelector('.btn-label')?.remove();
    newCmdBtn.append(h('span', { class: 'btn-label' }, t('editor.newCommand')));
    search.placeholder = t('editor.search');
    testerTitle.textContent = t('editor.tester');
    testerInput.placeholder = t('editor.tester.placeholder');
    testerBtn.title = t('editor.tester.run');
    renderTree();
    if (item && !dirty) select(item.path, true);
    else if (!item) renderDetail();
  }

  return {
    el,
    renderTexts,
    load: loadTree,
    hasUnsaved: () => dirty,
    async open(path) {
      if (!(await guardUnsaved())) return;
      expandTo(`${path}/x`);
      expanded.add(path);
      saveExpanded(expanded);
      await loadTree();
      await select(path, true);
    },
    async onTreeChanged() {
      await loadTree();
      if (item && !dirty && !findNode(item.path)) { item = null; selected = null; renderDetail(); }
    },
  };
}
