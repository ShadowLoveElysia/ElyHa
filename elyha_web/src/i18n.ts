export type I18nDict = Record<string, string>;

export interface TranslationVars {
  [key: string]: string | number | boolean | null | undefined;
}

export interface LocaleOption {
  value: string;
  label: string;
}

const cache = new Map<string, I18nDict>();
const SUPPORTED = new Set(['zh', 'en', 'ja']);

function trimTrailingSlash(value: string): string {
  return value.replace(/\/+$/, '');
}

function resolveApiBase(): string {
  const raw = (import.meta as {env?: {VITE_API_BASE_URL?: string}}).env?.VITE_API_BASE_URL;
  if (!raw || !raw.trim()) {
    return '';
  }
  return trimTrailingSlash(raw.trim());
}

const API_BASE = resolveApiBase();

function withApiBase(path: string): string {
  if (/^https?:\/\//i.test(path) || !API_BASE) {
    return path;
  }
  return `${API_BASE}${path.startsWith('/') ? path : `/${path}`}`;
}

export const SUPPORTED_LOCALES: LocaleOption[] = [
  {value: 'zh', label: '简体中文'},
  {value: 'en', label: 'English'},
  {value: 'ja', label: '日本語'},
];

function normalizeLocale(rawLocale: string): string {
  const raw = (rawLocale || '').trim().toLowerCase();
  if (!raw) {
    return 'zh';
  }
  if (SUPPORTED.has(raw)) {
    return raw;
  }
  const primary = raw.split(/[-_]/)[0] || '';
  if (SUPPORTED.has(primary)) {
    return primary;
  }
  return 'zh';
}

async function tryFetchJson(path: string): Promise<I18nDict | null> {
  try {
    const response = await fetch(path, {
      cache: 'no-store',
      headers: {
        Accept: 'application/json',
      },
    });
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
  const raw = (locale || '').trim().toLowerCase();
  const normalized = normalizeLocale(raw);
  const cached = cache.get(normalized);
  if (cached) {
    return cached;
  }

  const rawCandidates: string[] = [];
  if (raw) {
    rawCandidates.push(raw);
    const primary = raw.split(/[-_]/)[0] || '';
    if (primary && primary !== raw) {
      rawCandidates.push(primary);
    }
  }
  rawCandidates.push(normalized);

  const candidates = [
    ...rawCandidates.flatMap((tag) => [
      `/i18n/${tag}.json`,
      `/web/i18n/${tag}.json`,
      `/api/i18n/${tag}`,
      withApiBase(`/i18n/${tag}.json`),
      withApiBase(`/web/i18n/${tag}.json`),
      withApiBase(`/api/i18n/${tag}`),
    ]),
  ];
  const dedup = Array.from(new Set(candidates));

  let dict: I18nDict = {};
  for (const path of dedup) {
    const loaded = await tryFetchJson(path);
    if (loaded) {
      dict = loaded;
      break;
    }
  }

  // Some environments may keep a stale locale JSON in cache/proxy;
  // if key markers are missing, force a one-shot cache-busting retry.
  if (!dict['web.modal.confirm'] || !dict['web.chat.boot_message']) {
    const bust = String(Date.now());
    for (const path of dedup) {
      const sep = path.includes('?') ? '&' : '?';
      const loaded = await tryFetchJson(`${path}${sep}v=${bust}`);
      if (loaded && loaded['web.modal.confirm']) {
        dict = loaded;
        break;
      }
    }
  }
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
