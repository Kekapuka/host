// Settings page.
import { api } from './bridge.js';
import { t } from './i18n.js';
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
  let models = [];

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
    const provider = h('select', { class: 'select' }, h('option', { value: 'deepseek' }, 'DeepSeek'));
    provider.value = s.ai_provider;
    provider.addEventListener('change', () => save({ ai_provider: provider.value }));
    const key = h('input', { class: 'input mono key-input', type: 'password', spellcheck: 'false', autocomplete: 'off', placeholder: 'sk-…' });
    key.value = s.ai_api_key || '';
    const saveKey = debounce(() => save({ ai_api_key: key.value.trim() }), 700);
    key.addEventListener('input', saveKey);
    const eye = h('button', { type: 'button', class: 'btn icon ghost sm', title: t('settings.key.show') }, ico('eye', 16));
    eye.addEventListener('click', () => {
      key.type = key.type === 'password' ? 'text' : 'password';
      eye.replaceChildren(ico(key.type === 'password' ? 'eye' : 'eyeOff', 16));
    });
    const keyStatus = h('div', { class: 'key-status' });
    const model = h('select', { class: 'select' });
    const fillModels = () => {
      const current = store.settings.ai_model || 'auto';
      const opts = ['auto', ...models.filter((m) => m !== 'auto')];
      if (!opts.includes(current)) opts.push(current);
      model.replaceChildren(...opts.map((m) => h('option', { value: m }, m === 'auto' ? t('settings.model.auto') : m)));
      model.value = current;
    };
    fillModels();
    model.addEventListener('change', () => save({ ai_model: model.value }));
    const check = button({ label: t('settings.key.check'), iconName: 'key', kind: 'sm', onclick: async () => {
      check.disabled = true;
      keyStatus.className = 'key-status';
      keyStatus.textContent = t('settings.key.checking');
      try {
        await updateSettings({ ai_api_key: key.value.trim() });
        const res = await api.ai_test(key.value.trim());
        if (res.ok) {
          models = res.models || [];
          fillModels();
          keyStatus.className = 'key-status ok';
          keyStatus.textContent = t('settings.key.ok', { model: res.model });
        } else {
          keyStatus.className = 'key-status err';
          keyStatus.textContent = t('settings.key.fail', { error: res.error });
        }
      } catch (err) {
        keyStatus.className = 'key-status err';
        keyStatus.textContent = t('settings.key.fail', { error: err.message });
      } finally {
        check.disabled = false;
      }
    } });

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
      card('05', 'settings.ai', 'spark',
        row('settings.provider', 'settings.provider.desc', provider),
        h('div', { class: 'set-row col' }, h('div', { class: 'set-text' }, h('div', { class: 'set-title' }, t('settings.key')),
          h('div', { class: 'set-desc' }, t('settings.key.desc'))),
        h('div', { class: 'input-row' }, key, eye, check), keyStatus),
        row('settings.model', 'settings.model.desc', model)),
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
  }

  watch('settings', apply);

  return { el, render, renderTexts: render };
}
