// Home screen: microphone, live transcript, command history and the control panel.
import { api } from './bridge.js';
import { logo } from './icons.js';
import { EXAMPLES, lang, t } from './i18n.js';
import { store, updateSettings, watch } from './state.js';
import { button, confirmDialog, h, ico, iconButton, segmented, slider, timeLabel, toast, toggle } from './ui.js';

const METER_CELLS = 28;

export function createHome({ onThemeToggle }) {
  const el = h('section', { class: 'layer home-layer', id: 'page-home' });

  // --- hero: greeting, microphone, live transcript -----------------------------------------
  const eyebrow = h('div', { class: 'eyebrow' });
  const hello = h('h1', { class: 'hello' });
  const sub = h('p', { class: 'hello-sub' });

  const micBtn = h('button', { class: 'mic-btn', type: 'button' },
    h('span', { class: 'mic-ring r1' }), h('span', { class: 'mic-ring r2' }),
    h('span', { class: 'mic-ico on' }, ico('mic', 30)), h('span', { class: 'mic-ico off' }, ico('micOff', 30)));
  micBtn.addEventListener('click', async () => {
    micBtn.disabled = true;
    try {
      const state = await api.set_mic(!store.state.mic);
      applyState(state);
    } catch (err) {
      toast(err.message, 'error');
    } finally {
      micBtn.disabled = false;
    }
  });

  const stateDot = h('span', { class: 'state-dot' });
  const stateText = h('span', { class: 'state-text' });
  const stopBtn = button({ label: '', iconName: 'stop', kind: 'ghost sm stop-btn', onclick: () => api.stop_speaking() });
  const meter = h('div', { class: 'meter', 'aria-hidden': 'true' });
  const cells = [];
  for (let i = 0; i < METER_CELLS; i += 1) {
    const c = h('span', { class: 'cell' });
    cells.push(c);
    meter.append(c);
  }
  const heardLabel = h('span', { class: 'heard-label mono' });
  const heardText = h('span', { class: 'heard-text' });
  const heardNote = h('span', { class: 'heard-note' });
  const heard = h('div', { class: 'heard' }, heardLabel, heardText, heardNote);

  const voice = h('div', { class: 'voice' },
    micBtn,
    h('div', { class: 'voice-info' },
      h('div', { class: 'voice-state' }, stateDot, stateText, stopBtn),
      meter,
      heard));

  const bigLogo = h('div', { class: 'home-logo', html: logo('logo-anim') });

  const hero = h('header', { class: 'home-hero' },
    h('div', { class: 'home-intro' }, eyebrow, hello, sub, voice),
    bigLogo);

  // --- history -------------------------------------------------------------------------------
  const histTitle = h('h2', { class: 'panel-title' });
  const histCount = h('span', { class: 'count mono' });
  const clearBtn = button({ label: '', kind: 'ghost sm', onclick: async () => {
    if (!store.history.length) return;
    if (await confirmDialog({ title: t('history.clear.confirm'), ok: t('history.clear'), danger: true })) {
      await api.clear_history();
    }
  } });
  const list = h('div', { class: 'history-list' });
  const empty = h('div', { class: 'history-empty' });
  const input = h('input', { class: 'composer-input', type: 'text', spellcheck: 'false', autocomplete: 'off' });
  const sendBtn = h('button', { class: 'btn primary icon composer-send', type: 'submit' }, ico('send', 16));
  const composer = h('form', { class: 'composer' }, h('span', { class: 'composer-prompt mono' }, '>'), input, sendBtn);
  composer.addEventListener('submit', async (ev) => {
    ev.preventDefault();
    const text = input.value.trim();
    if (!text) return;
    input.value = '';
    try {
      await api.send_text(text);
    } catch (err) {
      toast(err.message, 'error');
    }
  });
  const historyPanel = h('section', { class: 'panel history' },
    h('div', { class: 'panel-head' }, h('div', { class: 'panel-head-l' }, histTitle, histCount), clearBtn),
    h('div', { class: 'history-scroll' }, empty, list),
    composer);

  // --- control panel -------------------------------------------------------------------------
  const silentTitle = h('div', { class: 'ctl-title' });
  const silentDesc = h('div', { class: 'ctl-desc' });
  const silentSwitch = toggle(false, (v) => updateSettings({ silent: v }).catch((e) => toast(e.message, 'error')));
  const themeTitle = h('div', { class: 'ctl-title' });
  let themeSeg = null;
  const themeSlot = h('div', { class: 'ctl-control' });
  const volTitle = h('div', { class: 'ctl-title' });
  const volDesc = h('div', { class: 'ctl-desc' });
  const volSlider = slider(70, (v) => updateSettings({ volume: v }).catch((e) => toast(e.message, 'error')));
  const statusChips = h('div', { class: 'ctl-status' });
  const examplesTitle = h('div', { class: 'ctl-examples-title' });
  const examplesList = h('div', { class: 'ctl-examples-list' });
  const examples = h('div', { class: 'ctl-examples' }, examplesTitle, examplesList);
  const ctlTitle = h('h2', { class: 'panel-title' });
  const control = h('section', { class: 'panel control' },
    h('div', { class: 'panel-head' }, ctlTitle),
    h('div', { class: 'ctl-row' }, h('div', { class: 'ctl-text' }, silentTitle, silentDesc), silentSwitch),
    h('div', { class: 'ctl-row' }, h('div', { class: 'ctl-text' }, themeTitle), themeSlot),
    h('div', { class: 'ctl-row col' }, h('div', { class: 'ctl-line' },
      h('div', { class: 'ctl-text' }, volTitle, volDesc), ico('volume', 18, 'muted')), volSlider),
    examples,
    statusChips);

  el.append(hero, h('div', { class: 'home-grid' }, historyPanel, control));

  // --- rendering -----------------------------------------------------------------------------
  function greeting() {
    const hr = new Date().getHours();
    if (hr >= 5 && hr < 12) return t('home.morning');
    if (hr >= 12 && hr < 18) return t('home.day');
    if (hr >= 18 && hr < 23) return t('home.evening');
    return t('home.night');
  }

  function subtitle() {
    const s = store.settings;
    const phase = store.state.phase || 'off';
    return t(`home.sub.${phase}`, {
      wake: s.wake_word || 'джарвис',
      yes: (s.confirm_words || ['да'])[0] || 'да',
      no: (s.cancel_words || ['нет'])[0] || 'нет',
    });
  }

  function applyState(state) {
    if (state) store.state = { ...store.state, ...state };
    const st = store.state;
    const on = !!st.mic;
    micBtn.classList.toggle('on', on);
    micBtn.title = on ? t('home.mic.on') : t('home.mic.off');
    micBtn.setAttribute('aria-pressed', on ? 'true' : 'false');
    el.dataset.phase = st.phase || 'off';
    bigLogo.dataset.phase = st.phase || 'off';
    stateText.textContent = on ? t(`phase.${st.phase || 'listening'}`) : t('home.mic.label.off');
    stopBtn.hidden = st.phase !== 'speaking';
    stopBtn.title = t('home.stop');
    sub.textContent = subtitle();
    if (!on) setLevel(0);
  }

  function setLevel(v) {
    const lit = Math.round(Math.max(0, Math.min(1, v)) * METER_CELLS);
    for (let i = 0; i < METER_CELLS; i += 1) cells[i].classList.toggle('lit', i < lit);
  }

  function showHeard(data) {
    heardText.textContent = data?.text ? `«${data.text}»` : '';
    heardNote.textContent = data?.text && !data.addressed ? t('home.heard.skip') : '';
    heard.classList.toggle('dim', !!data?.text && !data.addressed);
    heard.classList.toggle('empty', !data?.text);
    if (!data?.text) heardText.textContent = t('home.heard.empty');
    heard.classList.remove('flash');
    void heard.offsetWidth;
    heard.classList.add('flash');
  }

  function stepChip(step) {
    let label = step.label;
    if (step.kind === 'ai') label = t('step.ai');
    if (step.kind === 'unknown') label = `${t('step.unknown')}: «${step.text}»`;
    return h('span', { class: `step s-${step.status}`, title: step.error || step.text },
      h('span', { class: 'step-dot' }), h('span', { class: 'step-label' }, label));
  }

  function entryNode(entry) {
    const status = entry.status || 'processing';
    const node = h('article', { class: `h-item st-${status}`, dataset: { id: entry.id } });
    const meta = h('div', { class: 'h-meta' },
      h('span', { class: 'h-time mono' }, timeLabel(entry.ts)),
      h('span', { class: 'h-src mono' }, t(`source.${entry.source}`) || entry.source),
      h('span', { class: 'h-status' }, h('span', { class: 'status-dot' }), t(`status.${status}`)),
      iconButton('repeat', t('history.repeat'), () => api.repeat(entry.id).catch((e) => toast(e.message, 'error')),
        'ghost xs h-repeat'));
    node.append(meta, h('div', { class: 'h-text' }, entry.heard && entry.heard !== entry.text ? entry.heard : entry.text));
    if (entry.steps?.length) node.append(h('div', { class: 'h-steps' }, entry.steps.map(stepChip)));
    if (entry.reply) {
      node.append(h('div', { class: 'h-reply' }, h('span', { class: 'h-reply-who mono' }, t('history.reply')),
        h('span', { class: 'h-reply-text' }, entry.reply)));
    }
    if (status === 'confirm') {
      node.append(h('div', { class: 'h-confirm' },
        button({ label: t('history.confirm'), iconName: 'check', kind: 'primary sm',
          onclick: () => api.confirm(entry.id, true) }),
        button({ label: t('history.cancel'), iconName: 'x', kind: 'ghost sm',
          onclick: () => api.confirm(entry.id, false) })));
    }
    return node;
  }

  function renderHistory() {
    list.replaceChildren(...store.history.map(entryNode));
    updateHistoryChrome();
    scrollToBottom();
  }

  function updateHistoryChrome() {
    histCount.textContent = store.history.length ? String(store.history.length) : '';
    empty.hidden = store.history.length > 0;
    clearBtn.disabled = store.history.length === 0;
  }

  function scrollToBottom() {
    const scroller = historyPanel.querySelector('.history-scroll');
    requestAnimationFrame(() => { scroller.scrollTop = scroller.scrollHeight; });
  }

  function addEntry(entry) {
    store.history.push(entry);
    const node = entryNode(entry);
    node.classList.add('enter');
    list.append(node);
    updateHistoryChrome();
    scrollToBottom();
  }

  function updateEntry(entry) {
    const idx = store.history.findIndex((e) => e.id === entry.id);
    if (idx >= 0) store.history[idx] = entry;
    else store.history.push(entry);
    const old = list.querySelector(`[data-id="${entry.id}"]`);
    const node = entryNode(entry);
    if (old) old.replaceWith(node);
    else list.append(node);
    updateHistoryChrome();
    scrollToBottom();
  }

  function renderStatus() {
    const s = store.settings;
    const sttKey = { auto: 'settings.stt.auto', ru: 'settings.stt.ru', en: 'settings.stt.en' }[s.stt_language] || 'settings.stt.auto';
    statusChips.replaceChildren(
      h('span', { class: `chip-status ${s.ai_api_key ? 'ok' : ''}` }, h('span', { class: 'status-dot' }),
        s.ai_api_key ? t('panel.ai.on') : t('panel.ai.off')),
      h('span', { class: 'chip-status', title: t('settings.stt') }, ico('globe', 13), t(sttKey)));
  }

  function renderTexts() {
    eyebrow.textContent = t('home.eyebrow');
    hello.textContent = greeting();
    heardLabel.textContent = t('home.heard');
    histTitle.textContent = t('history.title');
    clearBtn.querySelector('.btn-label')?.remove();
    clearBtn.append(h('span', { class: 'btn-label' }, t('history.clear')));
    empty.replaceChildren(h('div', { class: 'empty-art', html: logo('') }),
      h('div', { class: 'empty-title' }, t('history.empty.title')),
      h('div', { class: 'empty-text' }, t('history.empty.text', { wake: store.settings.wake_word || 'джарвис' })));
    input.placeholder = t('history.placeholder');
    sendBtn.title = t('history.send');
    ctlTitle.textContent = t('panel.title');
    silentTitle.textContent = t('panel.silent');
    silentDesc.textContent = t('panel.silent.desc');
    themeTitle.textContent = t('panel.theme');
    themeSeg = segmented([
      { value: 'light', label: t('theme.light'), icon: 'sun' },
      { value: 'dark', label: t('theme.dark'), icon: 'moon' },
    ], store.settings.theme, (v, ev) => onThemeToggle(v, ev));
    themeSlot.replaceChildren(themeSeg);
    volTitle.textContent = t('panel.volume');
    volDesc.textContent = t('panel.volume.desc');
    const wake = store.settings.wake_word || 'джарвис';
    examplesTitle.textContent = t('panel.examples', { wake: `${wake[0].toUpperCase()}${wake.slice(1)}` });
    examplesList.replaceChildren(...(EXAMPLES[lang()] || EXAMPLES.ru).map((text) => h('button', {
      type: 'button', class: 'example', title: t('history.send'),
      onclick: () => { input.value = text; input.focus(); },
    }, text)));
    renderStatus();
    applyState();
    if (!heardText.textContent || heard.classList.contains('empty')) showHeard(null);
  }

  function applySettings(s) {
    silentSwitch.set(s.silent);
    themeSeg?.set(s.theme);
    volSlider.set(s.volume);
    el.classList.toggle('silent', !!s.silent);
    renderStatus();
    sub.textContent = subtitle();
  }

  watch('settings', applySettings);
  setInterval(() => { hello.textContent = greeting(); }, 60_000);

  return {
    el,
    renderTexts,
    renderHistory,
    applyState,
    applySettings,
    setLevel,
    showHeard,
    addEntry,
    updateEntry,
    clearHistory() { store.history = []; renderHistory(); },
    focusInput() { input.focus(); },
  };
}
