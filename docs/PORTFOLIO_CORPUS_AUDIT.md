# PORTFOLIO_CORPUS_AUDIT.md — аудит корпуса и технического долга

**Дата:** 2026-08-18  
**Статус:** Утверждено как baseline существующего технического долга  
**Кейс:** ai-portfolio  
**Цель:** зафиксировать текущее состояние 12 проектов, их технический долг, интеграционные требования AI Portfolio и обнаруженные NEW GAP. Документ служит основой для финализационной матрицы, включаемой в IMPLEMENTATION_PLAN.

---

## 1. Методика

- База: `reports/2026-08-18_rep-zerocoder-half-year-finalization.md` §6, §8.
- Проверены `PROJECT_STATE.md`, README, docs каждого из 12 проектов.
- Статус каждого пункта: ✅ выполнено / ⏳ актуально / ❌ NEW GAP.
- Deployment Validation откладывается по решению владельца, но отмечена как открытый пункт.

Каждый проект разобран по трём категориям:
1. **EXISTING DEBT** — существующий технический долг, который нужно закрыть/актуализировать перед запуском AI Portfolio.
2. **AIP INTEGRATION** — работы по включению проекта в AI Portfolio (карточка, страница, KB, ссылки).
3. **NEW GAP** — фактические проблемы, обнаруженные в ходе аудита и отсутствующие в исходном отчёте 18.08.

---

## 2. Финализационная матрица 12 проектов

| Проект | EXISTING DEBT (что закрываем перед запуском AIP) | Статус | AIP INTEGRATION | NEW GAP |
|--------|-----------------------------------------------------|--------|------------------|---------|
| **Review Auto Responder** | CA-bundle GigaChat; batch execution tracing | ⏳ | Карточка, страница, GitHub, demo, KB | Нет |
| **AI Curator** | Roadmap UI KB; GIF walkthrough | ⏳ | Карточка, страница, GitHub, demo, KB | Нет |
| **AI Data Assistant** | Вариант 4; runtime-реестры; auth чата; persistent storage | ⏳ | Карточка, страница, GitHub, KB | Нет |
| **Assistant Flow** | RAG UI polish; telemetry; multi-version docs; heavy RAG stability; RBAC/auth; async layer; production build | ⏳ | Карточка, страница, GitHub, KB | Нет |
| **Meeting Audit Bot** | Before/after пример; эвристика транскрибации; автотесты; webhook; версионирование промптов | ⏳ | Карточка, страница, GitHub, demo, KB | Нет |
| **Lead Qualification** | Event chaining; Bitrix24; multi-language; semantic fallback; чат-бот диалог | ⏳ | Карточка, страница, GitHub, demo, KB | Нет |
| **HR Assistant** | Hard-negative fix; production smoke set; score calibration; **KP-001 metadata**; env credentials | ⏳ | Карточка, страница, GitHub, landing, KB | Нет |
| **HRA-LoRA** | Hard-negative fix; production smoke set; stratified metrics; score calibration; latency; product positioning | ⏳ | Карточка, страница, landing, KB | Нет |
| **Telegram Intake Bot** | **Deployment Validation**; упростить промпты; scenario router; persistent storage; скриншоты v2 | ⏳ | Карточка, страница, GitHub, demo, KB | Нет |
| **Telegram Onboarding Bot** | **Deployment Validation**; retry/fallback; persistent FSM; RBAC `/topic`; `/edit_topic` | ⏳ | Карточка, страница, GitHub, demo, KB | Нет |
| **Review Flow** | **Повторная Deployment Validation**; Kommo; Bitrix24; n8n; упрощение Controlled Hybrid | ⏳ | Карточка, страница, GitHub, demo, KB | Нет |
| **Retail Group** | Сборка Case Story 32 слайда; проверка фактов; внутренний review | ⏳ | Карточка, страница, landing/presale, KB | Нет |


## 3. NEW GAP

### NEW GAP #1: Отсутствовало согласованное ТЗ AI Portfolio v1.0
- **Статус:** ✅ Устранено — создан `docs/TZ.md` v1.0 (черновик) от 2026-08-19, раздел 8.1 заполнен.
- **Источник:** задание + фактическая структура репозитория.
- **Влияние:** было невозможно корректно заполнить раздел 8.1.

### NEW GAP #2: Устаревший PROJECT_STATE.md AI Portfolio
- **Статус:** ✅ Устранено — `docs/PROJECT_STATE.md` актуализирован 2026-08-18, статус «Черновик / На согласовании».
- **Источник:** `docs/PROJECT_STATE.md` (последнее обновление 2026-07-19).
- **Влияние:** некорректная точка входа для агентов.

### NEW GAP #3: В публичном сайте 7–8 проектов вместо 12
- **Статус:** ⏳ Будет устранено в рамках P0–P2 IMPLEMENTATION_PLAN (19.08–26.08.2026).
- **Источник:** `docs/PROJECT_STATE.md` §Портфолио + текущий backend.
- **Влияние:** финальная витрина не содержит все 12 проектов.

### NEW GAP #4: Нет единого корпуса знаний для 12 проектов
- **Статус:** ⏳ Будет устранено в рамках P1 IMPLEMENTATION_PLAN (22.08.2026).
- **Источник:** `docs/PROJECT_STATE.md` §Архитектура Knowledge Base.
- **Влияние:** RAG отвечает по устаревшему/неполному набору документов.

### NEW GAP #5: Deployment Validation AI Portfolio не пройдена
- **Статус:** ⏳ Отложена по решению владельца.
- **Источник:** `docs/PROJECT_STATE.md`.
- **Влияние:** нет формального доказательства воспроизводимости развёртывания с нуля.

---

## 4. Интеграционные требования AI Portfolio по проектам

| Проект | Карточка в PostgreSQL | Страница в `src/` | GitHub-ссылка | Demo/landing | KB-источник |
|--------|----------------------|-------------------|---------------|--------------|-------------|
| Review Auto Responder | Да | Да | Да | Да | Да |
| AI Curator | Да | Да | Да | Да | Да |
| AI Data Assistant | Да | Да | Да | Нет live-demo | Да |
| Assistant Flow | Да | Да | Да | Нет live-demo | Да |
| Meeting Audit Bot | Да | Да | Да | Да | Да |
| Lead Qualification | Да | Да | Да | Да | Да |
| HR Assistant | Да | Да | Да | Нет live-demo | Да |
| HRA-LoRA | Да | Да | Да | `hra-lora.alex-n8n.site` | Да |
| Telegram Intake Bot | Да | Да | Да | После Deployment Validation | Да |
| Telegram Onboarding Bot | Да | Да | Да | После Deployment Validation | Да |
| Review Flow | Да | Да | Да | Текущий demo (Validation позже) | Да |
| Retail Group | Да | Да | Да | Презентация/Case Story | Да |

---

## 5. Порядок включения проектов в AI Portfolio

1. **Первыми запускаются готовые с live-demo:** Review Auto Responder, AI Curator, Meeting Audit Bot, Lead Qualification.
2. **Затем:** AI Data Assistant, Assistant Flow, HR Assistant, HRA-LoRA — с GitHub и landing/скриншотами.
3. **Затем:** Telegram Intake Bot, Telegram Onboarding Bot, Review Flow — с GitHub и текущими demo (Deployment Validation позже).
4. **Последним:** Retail Group — как пресейл-кейс/Case Story.

---

## 6. Рекомендации

- Полный EXISTING DEBT 12 проектов выполняется в рамках `docs/IMPLEMENTATION_PLAN.md` v3.1 до 04.09.2026.
- Для проектов без live-demo в портфеле отображать GitHub + landing/скриншоты/placeholder.
- Deployment Validation для 4 проектов и AI Portfolio переносится за пределы текущего release.
- Retail Group готовить как пресейл-страницу/Case Story.

---

## 7. Решения, зафиксированные владельцем

1. Список 12 проектов утверждён (см. `docs/IMPLEMENTATION_PLAN.md` §2).
2. Порядок включения 12 проектов утверждён (см. `docs/PORTFOLIO_CORPUS_AUDIT.md` §5).
3. Отсрочка Deployment Validation утверждена для: Telegram Intake Bot, Telegram Onboarding Bot, Review Flow, AI Portfolio.
4. Placeholder-страницы для проектов без live-demo утверждены.
5. На старте реализации DEFER CANDIDATE отсутствуют. Полный scope выполняется по `docs/IMPLEMENTATION_PLAN.md` v3.1.

---

## 8. История изменений

| Дата | Версия | Изменения |
|------|--------|-----------|
| 2026-08-18 | 1.0 | Базовый аудит корпуса, долга и NEW GAP |
| 2026-08-18 | 1.2 | Раздел 2 переименован в «Финализационная матрица 12 проектов»; добавлена колонка EXISTING DEBT; обновлены NEW GAP; убрано самостоятельное правило «только блокирующий долг»; статус «Утверждено как baseline» |
