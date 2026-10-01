// Small DOM helpers and reusable controls.
import { icon } from './icons.js';
import { t } from './i18n.js';

export function h(tag, attrs = {}, ...children) {
  const el = document.createElement(tag);
  for (const [key, value] of Object.entries(attrs || {})) {
    if (value === undefined || value === null || value === false) continue;
    if (key === 'class') el.className = value;
    else if (key === 'html') el.innerHTML = value;
    else if (key === 'text') el.textContent = value;
    else if (key === 'style' && typeof value === 'object') {
      for (const [prop, v] of Object.entries(value)) {
        if (prop.startsWith('--')) el.style.setProperty(prop, v);
        else el.style[prop] = v;
      }
    }
    else if (key.startsWith('on') && typeof value === 'function') el.addEventListener(key.slice(2), value);
    else if (key === 'dataset') Object.assign(el.dataset, value);
    else if (value === true) el.setAttribute(key, '');
    else el.setAttribute(key, value);
  }
  for (const child of children.flat(Infinity)) {
    if (child === null || child === undefined || child === false) continue;
    el.append(child instanceof Node ? child : document.createTextNode(String(child)));
  }
  return el;
}

export function ico(name, size = 18, cls = '') {
  const span = document.createElement('span');
  span.className = `i ${cls}`;
  span.innerHTML = icon(name, size);
  return span;
}

export function clear(el) {
  while (el.firstChild) el.removeChild(el.firstChild);
  return el;
}

export function debounce(fn, ms = 400) {
  let timer;
  return (...args) => {
    clearTimeout(timer);
    timer = setTimeout(() => fn(...args), ms);
  };
}

export function button({ label = '', iconName = null, kind = '', title = null, onclick = null, size = 16, attrs = {} } = {}) {
  return h('button', { class: `btn ${kind}`.trim(), type: 'button', title: title || (label ? null : null), onclick, ...attrs },
    iconName ? ico(iconName, size) : null,
    label ? h('span', { class: 'btn-label' }, label) : null);
}

export function iconButton(name, title, onclick, kind = 'ghost') {
  return h('button', { class: `btn icon ${kind}`, type: 'button', title, 'aria-label': title, onclick }, ico(name, 16));
}

// Pixel switch.
export function toggle(checked, onchange, label = '') {
  const input = h('input', { type: 'checkbox', role: 'switch', 'aria-label': label });
  input.checked = !!checked;
  input.addEventListener('change', () => onchange?.(input.checked));
  const el = h('label', { class: 'switch' }, input, h('span', { class: 'switch-track' }, h('span', { class: 'switch-knob' })));
  el.set = (v) => { input.checked = !!v; };
  el.input = input;
  return el;
}

// Segmented control: options = [{value, label, icon}]
export function segmented(options, value, onchange, cls = '') {
  const el = h('div', { class: `seg ${cls}`.trim(), role: 'radiogroup' });
  const buttons = options.map((opt) => {
    const b = h('button', { type: 'button', class: 'seg-btn', role: 'radio', dataset: { value: opt.value } },
      opt.icon ? ico(opt.icon, 15) : null, h('span', {}, opt.label));
    b.addEventListener('click', (ev) => {
      if (el.dataset.value === String(opt.value)) return;
      el.set(opt.value);
      onchange?.(opt.value, ev);
    });
    el.append(b);
    return b;
  });
  el.set = (v) => {
    el.dataset.value = String(v);
    for (const b of buttons) {
      const active = b.dataset.value === String(v);
      b.classList.toggle('active', active);
      b.setAttribute('aria-checked', active ? 'true' : 'false');
    }
  };
  el.set(value);
  return el;
}

// Range slider 1..100 with live value.
export function slider(value, onchange, { min = 1, max = 100, step = 1, label = '' } = {}) {
  const input = h('input', { type: 'range', min, max, step, class: 'range', 'aria-label': label });
  const out = h('span', { class: 'range-value mono' });
  const paint = () => {
    const pct = ((input.value - min) / (max - min)) * 100;
    input.style.setProperty('--pct', `${pct}%`);
    out.textContent = input.value;
  };
  input.value = value;
  paint();
  const commit = debounce(() => onchange?.(Number(input.value)), 250);
  input.addEventListener('input', () => { paint(); commit(); });
  const el = h('div', { class: 'range-wrap' }, input, out);
  el.set = (v) => {
    if (document.activeElement === input) return;
    input.value = v;
    paint();
  };
  return el;
}

// Editable list of words/phrases shown as chips.
export function chipsInput(values, onchange, { placeholder = '', mono = false } = {}) {
  let items = [...(values || [])];
  const input = h('input', { class: 'chips-input', placeholder, spellcheck: 'false' });
  const el = h('div', { class: `chips ${mono ? 'mono' : ''}`.trim() });
  const render = () => {
    el.querySelectorAll('.chip').forEach((c) => c.remove());
    items.forEach((value, idx) => {
      const chip = h('span', { class: 'chip' },
        h('span', { class: 'chip-text', title: value }, value),
        h('button', { type: 'button', class: 'chip-x', title: t('common.delete'), onclick: () => {
          items.splice(idx, 1);
          render();
          onchange?.([...items]);
        } }, ico('x', 12)));
      el.insertBefore(chip, input);
    });
  };
  const add = () => {
    const value = input.value.trim().replace(/\s+/g, ' ');
    if (!value) return false;
    if (!items.includes(value)) {
      items.push(value);
      render();
      onchange?.([...items]);
    }
    input.value = '';
    return true;
  };
  input.addEventListener('keydown', (ev) => {
    if (ev.key === 'Enter' || (ev.key === ',' && !ev.shiftKey)) {
      ev.preventDefault();
      add();
    } else if (ev.key === 'Backspace' && !input.value && items.length) {
      items.pop();
      render();
      onchange?.([...items]);
    }
  });
  input.addEventListener('blur', () => add());
  el.addEventListener('click', (ev) => { if (ev.target === el) input.focus(); });
  el.append(input);
  render();
  el.set = (v) => { items = [...(v || [])]; render(); };
  el.get = () => [...items];
  return el;
}

// --- toasts -------------------------------------------------------------------------------
export function toast(text, kind = 'info', ms = 3200) {
  const root = document.getElementById('toasts');
  const el = h('div', { class: `toast ${kind}`, role: 'status' },
    h('span', { class: 'toast-dot' }), h('span', { class: 'toast-text' }, text));
  root.append(el);
  requestAnimationFrame(() => el.classList.add('show'));
  setTimeout(() => {
    el.classList.remove('show');
    setTimeout(() => el.remove(), 400);
  }, ms);
}

// --- modal dialogs ------------------------------------------------------------------------
function openModal(build) {
  return new Promise((resolve) => {
    const root = document.getElementById('modal-root');
    const backdrop = h('div', { class: 'modal-backdrop' });
    const box = h('div', { class: 'modal', role: 'dialog', 'aria-modal': 'true' });
    backdrop.append(box);
    root.append(backdrop);
    document.body.classList.add('modal-open');
    const close = (value) => {
      backdrop.classList.remove('show');
      document.body.classList.remove('modal-open');
      document.removeEventListener('keydown', onKey, true);
      setTimeout(() => backdrop.remove(), 250);
      resolve(value);
    };
    const onKey = (ev) => {
      if (ev.key === 'Escape') { ev.stopPropagation(); close(null); }
    };
    document.addEventListener('keydown', onKey, true);
    backdrop.addEventListener('mousedown', (ev) => { if (ev.target === backdrop) close(null); });
    build(box, close);
    requestAnimationFrame(() => backdrop.classList.add('show'));
  });
}

export function confirmDialog({ title, text = '', ok = t('common.ok'), danger = false }) {
  return openModal((box, close) => {
    const okBtn = button({ label: ok, kind: danger ? 'danger' : 'primary', onclick: () => close(true) });
    box.append(
      h('h3', { class: 'modal-title' }, title),
      text ? h('p', { class: 'modal-text' }, text) : null,
      h('div', { class: 'modal-actions' },
        button({ label: t('common.cancel'), kind: 'ghost', onclick: () => close(false) }), okBtn),
    );
    setTimeout(() => okBtn.focus(), 30);
  }).then((v) => v === true);
}

export function promptDialog({ title, label = '', value = '', ok = t('common.ok') }) {
  return openModal((box, close) => {
    const input = h('input', { class: 'input', value, spellcheck: 'false' });
    input.value = value;
    const submit = () => {
      const v = input.value.trim();
      if (v) close(v);
      else input.focus();
    };
    input.addEventListener('keydown', (ev) => { if (ev.key === 'Enter') submit(); });
    box.append(
      h('h3', { class: 'modal-title' }, title),
      h('label', { class: 'field' }, label ? h('span', { class: 'field-label' }, label) : null, input),
      h('div', { class: 'modal-actions' },
        button({ label: t('common.cancel'), kind: 'ghost', onclick: () => close(null) }),
        button({ label: ok, kind: 'primary', onclick: submit })),
    );
    setTimeout(() => { input.focus(); input.select(); }, 30);
  });
}

export function selectDialog({ title, label = '', options, value = '' }) {
  return openModal((box, close) => {
    const select = h('select', { class: 'select' }, options.map((o) => h('option', { value: o.value }, o.label)));
    select.value = value;
    box.append(
      h('h3', { class: 'modal-title' }, title),
      h('label', { class: 'field' }, label ? h('span', { class: 'field-label' }, label) : null, select),
      h('div', { class: 'modal-actions' },
        button({ label: t('common.cancel'), kind: 'ghost', onclick: () => close(null) }),
        button({ label: t('common.ok'), kind: 'primary', onclick: () => close(select.value) })),
    );
    setTimeout(() => select.focus(), 30);
  });
}

// --- popup menu ---------------------------------------------------------------------------
export function popupMenu(anchor, items) {
  document.querySelectorAll('.menu').forEach((m) => m.remove());
  const menu = h('div', { class: 'menu', role: 'menu' });
  for (const item of items) {
    if (item === '-') { menu.append(h('div', { class: 'menu-sep' })); continue; }
    menu.append(h('button', { type: 'button', role: 'menuitem', class: `menu-item ${item.danger ? 'danger' : ''}`,
      onclick: () => { menu.remove(); item.action(); } }, item.icon ? ico(item.icon, 15) : null, h('span', {}, item.label)));
  }
  document.body.append(menu);
  const r = anchor.getBoundingClientRect();
  const mw = menu.offsetWidth;
  const mh = menu.offsetHeight;
  let left = Math.min(r.left, window.innerWidth - mw - 8);
  let top = r.bottom + 4;
  if (top + mh > window.innerHeight - 8) top = Math.max(8, r.top - mh - 4);
  menu.style.left = `${Math.max(8, left)}px`;
  menu.style.top = `${top}px`;
  requestAnimationFrame(() => menu.classList.add('show'));
  const away = (ev) => {
    if (!menu.contains(ev.target)) {
      menu.remove();
      document.removeEventListener('mousedown', away, true);
    }
  };
  setTimeout(() => document.addEventListener('mousedown', away, true), 0);
  return menu;
}

export function timeLabel(ts) {
  const d = new Date(ts * 1000);
  const now = new Date();
  const hm = d.toLocaleTimeString([], { hour: '2-digit', minute: '2-digit', hour12: false });
  if (d.toDateString() === now.toDateString()) return hm;
  return `${d.toLocaleDateString([], { day: '2-digit', month: '2-digit' })} ${hm}`;
}
