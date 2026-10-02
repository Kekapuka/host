// Settings page.
import { api } from './bridge.js';
import { t } from './i18n.js';
import { PRIVACY_URL, PROVIDER_ORDER, PROVIDERS } from './providers.js';
import { store, updateSettings, watch } from './state.js';
import { button, chipsInput, confirmDialog, debounce, h, ico, segmented, slider, toast, toggle } from './ui.js';

export function createSettings({ onThemeToggle }) {
  const el = h('section', { class: 'layer page-layer', id: 'page-settings' });
  const eyebrow = h('div', { class: 'eyebrow' });
  const title = h('h1', { class: 'page-title' });
  const body = h('div', { class: 'settings-body' });
  el.append(h('header', { class: 'page-head' }, h('div', {}, eyebrow, title)), h('div', { class: 'page-scroll' }, body));

  const controls = {};
  let micDevices = null;
  const aiBox = h('div', { class: 'ai-box' });
  const modelsBy = {}; // provider -> models it offers
  let aiStatus = null; // result of the last "Check"
  let ai = null; // controls of the rendered provider

  const save = async (patch) => {
    try {
      await updateSettings(patch);
      flashSaved();
    } catch (err) {
      toast(err.message, 'error');
    }
  };
  const flashSaved = debounce(() => toast(t('settings.saved'), 'ok', 1200), 350);

  function row(titleKey, descKey, control, extra = null) {
    return h('div', { class: 'set-row' },
      h('div', { class: 'set-text' }, h('div', { class: 'set-title' }, t(titleKey)),
        descKey ? h('div', { class: 'set-desc' }, t(descKey)) : null, extra),
      h('div', { class: 'set-control' }, control));
  }

  function card(num, titleKey, iconName, ...rows) {
    return h('section', { class: 'set-card' },
      h('div', { class: 'set-card-head' }, h('span', { class: 'set-num mono' }, num), ico(iconName, 18), h('h2', {}, t(titleKey))),
      ...rows);
  }

  async function loadMics(select) {
    try {
      micDevices = micDevices || await api.list_microphones();
    } catch {
      micDevices = [];
    }
    const current = store.settings.mic_device || '';
    select.replaceChildren(h('option', { value: '' }, t('settings.mic.default')),
      ...micDevices.map((d) => h('option', { value: d.id }, d.name)));
    if (current && !micDevices.some((d) => d.id === current)) select.append(h('option', { value: current }, current));
    select.value = current;
  }

  function colRow(titleKey, descKey, ...content) {
    return h('div', { class: 'set-row col' }, h('div', { class: 'set-text' }, h('div', { class: 'set-title' }, t(titleKey)),
      descKey ? h('div', { class: 'set-desc' }, t(descKey)) : null), ...content);
  }

  // "ollama pull qwen2.5:7b" in a text -> a monospace command
  function withCommands(text) {
    return String(text).split(/(ollama pull [\w.:/-]*\w)/).map((part, i) => (i % 2 ? h('code', { class: 'cmd mono' }, part) : part));
  }

  function linkButton(label, url) {
    return button({ label, iconName: 'external', kind: 'sm', onclick: () => api.open_link(url).catch((e) => toast(e.message, 'error')) });
  }

  async function switchProvider(id) {
    aiStatus = null;
    await save({ ai_provider: id });
    renderAI();
  }

  function paintStatus() {
    const el = ai?.status;
    if (!el) return;
    const st = aiStatus && aiStatus.provider === ai.provider ? aiStatus : null;
    el.className = `key-status ${st ? st.kind : ''}`.trim();
    el.replaceChildren();
    if (!st) return;
    el.append(h('div', { class: 'key-status-text' }, st.text));
    if (st.hint) el.append(h('div', { class: 'key-status-hint' }, withCommands(st.hint)));
    const actions = [];
    if (st.code === 'no_balance' && st.provider === 'deepseek') {
      actions.push(button({ label: t('settings.key.toOpenRouter'), iconName: 'spark', kind: 'sm', onclick: () => switchProvider('openrouter') }));
    }
    if (st.code === 'privacy') actions.push(linkButton(t('provider.link.privacy'), PRIVACY_URL));
    if (st.code === 'daily_limit') {
      actions.push(button({ label: t('settings.key.toOllama'), iconName: 'spark', kind: 'sm', onclick: () => switchProvider('ollama') }));
    }
    if (actions.length) el.append(h('div', { class: 'key-status-actions' }, ...actions));
  }

  async function loadModels(provider) {
    if (modelsBy[provider]) return;
    modelsBy[provider] = [];
    try {
      const list = await api.ai_models(provider);
      if (list?.length && !modelsBy[provider].length) modelsBy[provider] = list;
    } catch { /* the list is optional */ }
    if (ai?.provider === provider) ai.fillModels();
  }

  async function runCheck(p, keyInput, urlInput, check) {
    const meta = PROVIDERS[p];
    const key = keyInput ? keyInput.value.trim() : null;
    const url = urlInput ? urlInput.value.trim() : null;
    check.disabled = true;
    aiStatus = { provider: p, kind: 'busy', text: t('settings.key.checking') };
    paintStatus();
    try {
      const patch = {};
      if (keyInput) patch[meta.key] = key;
      if (urlInput) patch[meta.url] = url;
      await updateSettings(patch);
      const res = await api.ai_test(p, key, url);
      if (res.models?.length) modelsBy[p] = res.models;
      if (res.ok) {
        const parts = [t('settings.key.ok', { model: res.model })];
        if (res.balance) parts.push(t('settings.key.balance', { balance: res.balance }));
        if (res.free_per_day) parts.push(t('settings.key.free', { n: res.free_per_day }));
        aiStatus = { provider: p, kind: 'ok', text: parts.join(' · ') };
      } else {
        const warn = res.code === 'no_balance';
        aiStatus = { provider: p, kind: warn ? 'warn' : 'err', code: res.code, hint: res.hint,
          text: warn ? res.error : t('settings.key.fail', { error: res.error }) };
      }
    } catch (err) {
      aiStatus = { provider: p, kind: 'err', text: t('settings.key.fail', { error: err.message }) };
    } finally {
      check.disabled = false;
    }
    if (ai?.provider === p) {
      ai.fillModels();
      paintStatus();
    }
  }

  function renderAI() {
    const s = store.settings;
    const p = PROVIDERS[s.ai_provider] ? s.ai_provider : 'openrouter';
    const meta = PROVIDERS[p];

    const provider = h('select', { class: 'select provider-select' },
      ...PROVIDER_ORDER.map((id) => h('option', { value: id }, t(`provider.${id}`))));
    provider.value = p;
    provider.addEventListener('change', () => switchProvider(provider.value));
    const about = h('div', { class: 'provider-about' }, h('div', {}, withCommands(t(`provider.${p}.about`))),
      meta.links.length ? h('div', { class: 'provider-links' }, ...meta.links.map(([key, url]) => linkButton(t(key), url))) : null);
    const rows = [row('settings.provider', 'settings.provider.desc', provider, about)];

    const status = h('div', { class: 'key-status' });
    const check = button({ label: t('settings.key.check'), iconName: 'key', kind: 'sm' });
    let urlInput = null;
    let keyInput = null;
    if (meta.url) {
      urlInput = h('input', { class: 'input mono', spellcheck: 'false', autocomplete: 'off', placeholder: meta.urlPlaceholder });
      urlInput.value = s[meta.url] || '';
      urlInput.addEventListener('input', debounce(() => save({ [meta.url]: urlInput.value.trim() }), 700));
      rows.push(colRow('settings.url', `settings.url.desc.${p}`, h('div', { class: 'input-row' }, urlInput, meta.key ? null : check)));
    }
    if (meta.key) {
      keyInput = h('input', { class: 'input mono key-input', type: 'password', spellcheck: 'false', autocomplete: 'off', placeholder: meta.keyPlaceholder });
      keyInput.value = s[meta.key] || '';
      keyInput.addEventListener('input', debounce(() => save({ [meta.key]: keyInput.value.trim() }), 700));
      const eye = h('button', { type: 'button', class: 'btn icon ghost sm', title: t('settings.key.show') }, ico('eye', 16));
      eye.addEventListener('click', () => {
        keyInput.type = keyInput.type === 'password' ? 'text' : 'password';
        eye.replaceChildren(ico(keyInput.type === 'password' ? 'eye' : 'eyeOff', 16));
      });
      rows.push(colRow('settings.key', `settings.key.desc.${p}`, h('div', { class: 'input-row' }, keyInput, eye, check)));
    }
    rows[rows.length - 1].append(status);
    check.addEventListener('click', () => runCheck(p, keyInput, urlInput, check));

    let modelControl;
    let fillModels;
    if (p === 'custom') {
      const list = h('datalist', { id: 'ai-models' });
      const input = h('input', { class: 'input mono model-input', spellcheck: 'false', autocomplete: 'off', list: 'ai-models', placeholder: t('settings.model.auto') });
      input.value = s.ai_model && s.ai_model !== 'auto' ? s.ai_model : '';
      input.addEventListener('input', debounce(() => save({ ai_model: input.value.trim() || 'auto' }), 700));
      fillModels = () => list.replaceChildren(...(modelsBy[p] || []).map((m) => h('option', { value: m })));
      modelControl = h('div', { class: 'model-wrap' }, input, list);
    } else {
      const select = h('select', { class: 'select' });
      fillModels = () => {
        const current = store.settings.ai_model || 'auto';
        const opts = ['auto', ...(modelsBy[p] || []).filter((m) => m !== 'auto')];
        if (!opts.includes(current)) opts.push(current);
        select.replaceChildren(...opts.map((m) => h('option', { value: m }, m === 'auto' ? t('settings.model.auto') : m)));
        select.value = current;
      };
      select.addEventListener('change', () => save({ ai_model: select.value }));
      modelControl = select;
    }
    rows.push(row('settings.model', `settings.model.desc.${p}`, modelControl));
    aiBox.replaceChildren(...rows);
    ai = { provider: p, status, fillModels };
    fillModels();
    paintStatus();
    loadModels(p);
  }

  function render() {
    const s = store.settings;
    eyebrow.textContent = t('settings.eyebrow');
    title.textContent = t('settings.title');

    // 1. Sound
    controls.volume = slider(s.volume, (v) => save({ volume: v }), { label: t('settings.volume') });
    controls.voice = segmented([
      { value: 'neural', label: t('settings.voice.neural') },
      { value: 'system', label: t('settings.voice.system') },
    ], s.voice_engine, (v) => save({ voice_engine: v }));
    const testVoice = button({ label: t('settings.voice.test'), iconName: 'play', kind: 'sm', onclick: () => api.test_voice().catch((e) => toast(e.message, 'error')) });

    // 2. Interface
    controls.language = segmented([
      { value: 'ru', label: 'Русский' },
      { value: 'en', label: 'English' },
    ], s.language, (v) => save({ language: v }));
    controls.theme = segmented([
      { value: 'light', label: t('theme.light'), icon: 'sun' },
      { value: 'dark', label: t('theme.dark'), icon: 'moon' },
    ], s.theme, (v, ev) => onThemeToggle(v, ev));
    controls.animations = toggle(s.animations, (v) => save({ animations: v }));

    // 3. Voice input
    controls.stt = segmented([
      { value: 'auto', label: t('settings.stt.auto') },
      { value: 'ru', label: t('settings.stt.ru') },
      { value: 'en', label: t('settings.stt.en') },
    ], s.stt_language, (v) => save({ stt_language: v }));
    const wake = h('input', { class: 'input mono wake-input', spellcheck: 'false', maxlength: '40' });
    wake.value = s.wake_word;
    const saveWake = debounce(() => { if (wake.value.trim()) save({ wake_word: wake.value.trim() }); }, 600);
    wake.addEventListener('input', saveWake);
    controls.wake = wake;
    controls.autostart = toggle(s.mic_autostart, (v) => save({ mic_autostart: v }));
    const micSelect = h('select', { class: 'select' }, h('option', { value: '' }, t('settings.mic.default')));
    micSelect.addEventListener('change', () => save({ mic_device: micSelect.value || null }));
    loadMics(micSelect);
    controls.mic = micSelect;

    // 4. Execution
    const wordList = (key) => chipsInput(s[key], (v) => save({ [key]: v }), { placeholder: t('settings.word.add') });
    controls.confirm_words = wordList('confirm_words');
    controls.cancel_words = wordList('cancel_words');
    controls.chain_words = wordList('chain_words');

    // 5. AI provider
    renderAI();

    // 6. Data
    const openData = button({ label: t('settings.open'), iconName: 'external', kind: 'sm', onclick: () => api.open_data_folder().catch((e) => toast(e.message, 'error')) });
    const reset = button({ label: t('settings.reset.do'), iconName: 'refresh', kind: 'sm', onclick: async () => {
      if (await confirmDialog({ title: t('settings.reset'), text: t('settings.reset.confirm'), ok: t('settings.reset.do') })) {
        try { await api.reset_defaults(); toast(t('common.done'), 'ok'); } catch (e) { toast(e.message, 'error'); }
      }
    } });

    body.replaceChildren(
      card('01', 'settings.sound', 'volume',
        row('settings.volume', 'settings.volume.desc', controls.volume),
        row('settings.voiceEngine', 'settings.voiceEngine.desc', h('div', { class: 'stack' }, controls.voice, testVoice))),
      card('02', 'settings.interface', 'window',
        row('settings.language', 'settings.language.desc', controls.language),
        row('panel.theme', 'settings.theme.desc', controls.theme),
        row('settings.animations', 'settings.animations.desc', controls.animations)),
      card('03', 'settings.voice', 'mic',
        row('settings.stt', 'settings.stt.desc', controls.stt),
        row('settings.wake', 'settings.wake.desc', controls.wake),
        row('settings.autostart', 'settings.autostart.desc', controls.autostart),
        row('settings.mic', 'settings.mic.desc', controls.mic)),
      card('04', 'settings.exec', 'bolt',
        h('div', { class: 'set-row col' }, h('div', { class: 'set-text' }, h('div', { class: 'set-title' }, t('settings.confirm')),
          h('div', { class: 'set-desc' }, t('settings.confirm.desc'))), controls.confirm_words),
        h('div', { class: 'set-row col' }, h('div', { class: 'set-text' }, h('div', { class: 'set-title' }, t('settings.cancel')),
          h('div', { class: 'set-desc' }, t('settings.cancel.desc'))), controls.cancel_words),
        h('div', { class: 'set-row col' }, h('div', { class: 'set-text' }, h('div', { class: 'set-title' }, t('settings.chain')),
          h('div', { class: 'set-desc' }, t('settings.chain.desc'))), controls.chain_words)),
      card('05', 'settings.ai', 'spark', aiBox),
      card('06', 'settings.data', 'data',
        row('settings.dataFolder', null, openData, h('div', { class: 'set-desc mono path' }, store.dataDir)),
        row('settings.reset', 'settings.reset.desc', reset)),
      h('div', { class: 'settings-foot mono' }, t('settings.version', { v: store.version })),
    );
  }

  function apply(s) {
    controls.volume?.set(s.volume);
    controls.voice?.set(s.voice_engine);
    controls.language?.set(s.language);
    controls.theme?.set(s.theme);
    controls.animations?.set(s.animations);
    controls.stt?.set(s.stt_language);
    controls.autostart?.set(s.mic_autostart);
    if (controls.wake && document.activeElement !== controls.wake) controls.wake.value = s.wake_word;
    if (ai && (PROVIDERS[s.ai_provider] ? s.ai_provider : 'openrouter') !== ai.provider) renderAI();
  }

  watch('settings', apply);

  return { el, render, renderTexts: render };
}
