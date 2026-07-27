import i18n from 'i18next';
import { initReactI18next } from 'react-i18next';
import LanguageDetector from 'i18next-browser-languagedetector';
import HttpBackend from 'i18next-http-backend';
import ICU from 'i18next-icu';

const resources = {
  en: {
    translation: {
      itemCount: '{count, plural, =0 {No items} one {# item} other {# items}}'
    }
  },
  ko: {
    translation: {
      itemCount: '{count, plural, =0 {항목 없음} other {#개 항목}}'
    }
  }
};

i18n
  .use(HttpBackend)
  .use(LanguageDetector)
  .use(ICU)
  .use(initReactI18next)
  .init({
    fallbackLng: 'en',
    supportedLngs: ['ko', 'en'],
    resources,
    backend: {
      loadPath: '/src/i18n/locales/{{lng}}.json'
    },
    detection: {
      order: ['querystring', 'cookie', 'localStorage', 'navigator', 'htmlTag'],
      caches: ['localStorage', 'cookie']
    },
    interpolation: {
      escapeValue: false
    }
  });

const mediaQuery = window.matchMedia('(prefers-color-scheme: dark)');

const applyTheme = (isDark: boolean) => {
  document.documentElement.classList.toggle('dark-theme', isDark);
  if (isDark) {
    document.documentElement.setAttribute('data-theme', 'dark');
  } else {
    document.documentElement.removeAttribute('data-theme');
  }
};

const updateTheme = () => {
  const override = localStorage.getItem('theme');
  if (override === 'dark') {
    applyTheme(true);
  } else if (override === 'light') {
    applyTheme(false);
  } else {
    applyTheme(mediaQuery.matches);
  }
};

updateTheme();

if (typeof mediaQuery.addEventListener === 'function') {
  mediaQuery.addEventListener('change', (e) => {
    if (!localStorage.getItem('theme')) {
      applyTheme(e.matches);
    }
  });
} else {
  mediaQuery.addListener((e) => {
    if (!localStorage.getItem('theme')) {
      applyTheme(e.matches);
    }
  });
}

window.addEventListener('storage', (e) => {
  if (e.key === 'theme') {
    updateTheme();
  }
});

export const setTheme = (theme: 'dark' | 'light' | 'system') => {
  if (theme === 'system') {
    localStorage.removeItem('theme');
  } else {
    localStorage.setItem('theme', theme);
  }
  updateTheme();
};

export default i18n;
