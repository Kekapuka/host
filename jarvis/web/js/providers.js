// AI providers: what each one needs in the settings.
export const PROVIDER_ORDER = ['openrouter', 'ollama', 'deepseek', 'custom'];

export const PROVIDERS = {
  openrouter: {
    name: 'OpenRouter', key: 'openrouter_api_key', keyPlaceholder: 'sk-or-v1-…',
    links: [['provider.link.openrouter', 'https://openrouter.ai/settings/keys']],
  },
  ollama: {
    name: 'Ollama', url: 'ollama_url', urlPlaceholder: 'http://localhost:11434',
    links: [['provider.link.ollama', 'https://ollama.com/download']],
  },
  deepseek: {
    name: 'DeepSeek', key: 'ai_api_key', keyPlaceholder: 'sk-…',
    links: [['provider.link.deepseekTopUp', 'https://platform.deepseek.com/top_up'],
      ['provider.link.deepseekKeys', 'https://platform.deepseek.com/api_keys']],
  },
  custom: {
    name: null, key: 'custom_api_key', url: 'custom_url', keyPlaceholder: 'sk-…',
    urlPlaceholder: 'https://api.groq.com/openai/v1', links: [],
  },
};

export const PRIVACY_URL = 'https://openrouter.ai/settings/privacy';

// Is the selected provider filled in enough to be used?
export function aiReady(s) {
  const p = PROVIDERS[s.ai_provider];
  if (!p) return false;
  if (s.ai_provider === 'ollama') return true;
  if (s.ai_provider === 'custom') return Boolean((s.custom_url || '').trim());
  return Boolean((s[p.key] || '').trim());
}

export function aiName(s) {
  const p = PROVIDERS[s.ai_provider];
  if (!p) return '';
  if (p.name) return p.name;
  const url = (s.custom_url || '').trim();
  try {
    return new URL(url.includes('://') ? url : `https://${url}`).hostname || 'API';
  } catch {
    return 'API';
  }
}
