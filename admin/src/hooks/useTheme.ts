/**
 * Хук темы админ-консоли (канон: admin-console-dual-theme-mirror-inversion).
 *
 * - Хранилище: localStorage-ключ `ai-theme` (значения `light` | `dark`);
 *   тёмная — дефолт (в т.ч. при недоступном storage).
 * - `data-theme` на <html> выставляется синхронно в теле рендера — до
 *   отрисовки компонентов (бутстрап до краски дополнительно в index.html).
 */
import { useState } from 'react';

const STORAGE_KEY = 'ai-theme';

function readInitialTheme(): 'light' | 'dark' {
  try {
    return localStorage.getItem(STORAGE_KEY) === 'light' ? 'light' : 'dark';
  } catch {
    return 'dark';
  }
}

export function useTheme() {
  // Инициализация синхронна: data-theme выставляется ещё до первого render-эффекта.
  const [theme, setTheme] = useState<'light' | 'dark'>(readInitialTheme);

  // Синхронно в теле рендера (не в useEffect) — тема применяется к <html>
  // до покраски DOM, без вспышки неправильной темы.
  document.documentElement.dataset.theme = theme;

  const toggleTheme = () => {
    setTheme((prev) => {
      const next = prev === 'dark' ? 'light' : 'dark';
      try {
        localStorage.setItem(STORAGE_KEY, next);
      } catch {
        /* приватный режим — тема живёт до перезагрузки */
      }
      return next;
    });
  };

  // Подпись переключателя показывает тему, в которую переключаемся.
  const toggleLabel = theme === 'dark' ? '☀️ Светлая тема' : '🌙 Тёмная тема';

  return { theme, toggleTheme, toggleLabel };
}