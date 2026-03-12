export type I18nDict = Record<string, string>;

export interface TranslationVars {
  [key: string]: string | number | boolean | null | undefined;
}

export interface LocaleOption {
  value: string;
  label: string;
}

const cache = new Map<string, I18nDict>();

export const SUPPORTED_LOCALES: LocaleOption[] = [
  {value: 'zh', label: '简体中文'},
  {value: 'en', label: 'English'},
  {value: 'ja', label: '日本語'},
];

async function tryFetchJson(path: string): Promise<I18nDict | null> {
  try {
    const response = await fetch(path);
    if (!response.ok) {
      return null;
    }
    const payload = (await response.json()) as unknown;
    if (!payload || typeof payload !== 'object' || Array.isArray(payload)) {
      return null;
    }
    return payload as I18nDict;
  } catch {
    return null;
  }
}

export async function loadLocaleDict(locale: string): Promise<I18nDict> {
  const normalized = (locale || '').trim() || 'zh';
  const cached = cache.get(normalized);
  if (cached) {
    return cached;
  }

  const fromRoot = await tryFetchJson(`/i18n/${normalized}.json`);
  const fromWebRoot = fromRoot || (await tryFetchJson(`/web/i18n/${normalized}.json`));
  const dict = fromWebRoot || {};
  cache.set(normalized, dict);
  return dict;
}

export function tFrom(dict: I18nDict, key: string, vars?: TranslationVars): string {
  const template = dict[key] || key;
  if (!vars) {
    return template;
  }
  return template.replace(/\{([a-zA-Z0-9_]+)\}/g, (_, token: string) => {
    const value = vars[token];
    if (value === undefined || value === null) {
      return '';
    }
    return String(value);
  });
}
