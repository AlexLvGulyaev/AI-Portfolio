import { useCallback, useEffect, useState } from "react";
import {
  getPresaleFunnel,
  getPresaleVisitorJourney,
  getPresaleVisitors,
  type PresaleFunnel,
  type GeoCountry,
  type PresaleFunnelStep,
  type PresaleVisitorSort,
  type PresaleJourney,
  type PresaleStepVisitors,
} from "../api/client";
import { EmptyState } from "../components/EmptyState";
import { Loading } from "../components/Loading";
import { formatTimestampLocal } from "../utils/operationalLabels";

// §4.5 Presale-аналитика — аналитический дашборд одного вопроса:
// «продаёт ли витрина и где путь встречает человека». Уровни:
// KPI + сводка конверсий → посетители шага (уровень 2) → путь гостя
// (уровень 3). Хранилище — operational_logs + execution_sessions
// (решение владельца 30.08.2026, ARCHITECTURE.md §8.4).

type PeriodOption = { label: string; days: number };

const PERIOD_OPTIONS: PeriodOption[] = [
  { label: "7 дней", days: 7 },
  { label: "30 дней", days: 30 },
  { label: "90 дней", days: 90 },
  { label: "Всё время", days: 0 },
];

const CHANNEL_LABELS: Record<string, string> = {
  telegram: "Telegram",
  email: "Email",
  other: "Другое",
};

interface Drill {
  step: PresaleFunnelStep["key"];
  lost: boolean;
  cardSlug?: string;
  channel?: string;
}

function percent(part: number, total: number): string {
  if (!total) return "—";
  const value = (part / total) * 100;
  return `${value < 10 ? value.toFixed(1) : Math.round(value)}%`;
}

function deltaPercent(current: number, previous: number): string | null {
  if (!previous) return null;
  const delta = ((current - previous) / previous) * 100;
  const sign = delta > 0 ? "+" : "";
  return `${sign}${Math.abs(delta) >= 10 ? Math.round(delta) : delta.toFixed(1)}%`;
}

// Русская плюрализация: 1 касание / 2 касания / 5 касаний
function plural(n: number, forms: [string, string, string]): string {
  const mod10 = n % 10;
  const mod100 = n % 100;
  if (mod10 === 1 && mod100 !== 11) return forms[0];
  if (mod10 >= 2 && mod10 <= 4 && (mod100 < 10 || mod100 >= 20)) return forms[1];
  return forms[2];
}

const STEP_PLURALS = {
  visitors: ["посетитель", "посетителя", "посетителей"] as [string, string, string],
  touches: ["касание", "касания", "касаний"] as [string, string, string],
  views: ["просмотр", "просмотра", "просмотров"] as [string, string, string],
  inquiries: ["обращение", "обращения", "обращений"] as [string, string, string],
};

const TOUCH_LABELS: Record<string, string> = {
  visit: "Визит на сайт",
  case_view: "Просмотр кейса",
  chat: "Диалог с ассистентом",
  inquiry: "Обращение",
};

function stepTitle(key: string): string {
  return (
    {
      visit: "Посетители сайта",
      case_view: "Интерес к кейсам",
      chat: "Диалоги с ассистентом",
      inquiry: "Обращения",
    }[key] ?? String(key)
  );
}

// Человекочитаемый номер гостя: стабильный детерминированный номер из
// хвоста UUID (задача 02.09). Полный id — в title строки.
function guestNumber(visitorId: string | null | undefined): string {
  if (!visitorId) return "—";
  const tail = visitorId.replace(/-/g, "").slice(-8);
  const n = parseInt(tail, 16) % 1_000_000;
  return `№${String(n).padStart(6, "0")}`;
}

// Флаг страны из ISO-кода (regional indicator symbols).
function countryFlag(code: string | null | undefined): string {
  if (!code || !/^[A-Z]{2}$/.test(code)) return "🏳️";
  return String.fromCodePoint(
    ...[...code].map((c) => 0x1f1e6 + c.charCodeAt(0) - 65),
  );
}

// Итоговая строка geo_countries от бэкенда (без code/country).
interface GeoTotalsRow {
  total_visitors: number;
  total_visits: number;
}

export function PresalePage() {
  const [funnel, setFunnel] = useState<PresaleFunnel | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [days, setDays] = useState(30);

  const [drill, setDrill] = useState<Drill | null>(null);
  const [cluster, setCluster] = useState<PresaleStepVisitors | null>(null);
  const [clusterLoading, setClusterLoading] = useState(false);
  const [clusterError, setClusterError] = useState<string | null>(null);
  // Порядок списка гостей (задача 02.09, вариант 2): ценность — дефолт
  const [sortMode, setSortMode] = useState<PresaleVisitorSort>("value");

  const [visitorId, setVisitorId] = useState<string | null>(null);
  const [journey, setJourney] = useState<PresaleJourney | null>(null);
  const [journeyLoading, setJourneyLoading] = useState(false);

  // Гео-агрегаты. Бэкенд в конце geo_countries присылает итоговую строку
  // {total_visitors, total_visits} — отделяем её от списка стран.
  const geoRaw = (funnel?.geo_countries ?? []) as (GeoCountry | GeoTotalsRow)[];
  const geoCountries = geoRaw.filter(
    (c): c is GeoCountry => !("total_visitors" in c),
  );
  const geoTotals = geoRaw.find(
    (c): c is GeoTotalsRow => "total_visitors" in c,
  );
  const geoInquiries = funnel?.geo_inquiries ?? [];

  const load = useCallback(async (period: number) => {
    setLoading(true);
    setError(null);
    try {
      const data = await getPresaleFunnel(period);
      setFunnel(data);
    } catch (e) {
      setError(e instanceof Error ? e.message : "Ошибка загрузки воронки");
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => {
    load(days);
  }, [load, days]);

  useEffect(() => {
    if (!drill) {
      setCluster(null);
      setClusterError(null);
      return;
    }
    let cancelled = false;
    setClusterLoading(true);
    setClusterError(null);
    setVisitorId(null);
    setJourney(null);
    getPresaleVisitors({
      step: drill.step,
      days,
      lost: drill.lost,
      card_slug: drill.cardSlug,
      channel: drill.channel,
      sort: sortMode,
    })
      .then((data) => {
        if (!cancelled) setCluster(data);
      })
      .catch((e) => {
        if (!cancelled)
          setClusterError(e instanceof Error ? e.message : "Ошибка загрузки");
      })
      .finally(() => {
        if (!cancelled) setClusterLoading(false);
      });
    return () => {
      cancelled = true;
    };
  }, [drill, days, sortMode]);

  useEffect(() => {
    if (!visitorId) {
      setJourney(null);
      return;
    }
    let cancelled = false;
    setJourneyLoading(true);
    getPresaleVisitorJourney(visitorId, 0)
      .then((data) => {
        if (!cancelled) setJourney(data);
      })
      .catch(() => {
        if (!cancelled) setJourney(null);
      })
      .finally(() => {
        if (!cancelled) setJourneyLoading(false);
      });
    return () => {
      cancelled = true;
    };
  }, [visitorId]);

  const steps = funnel?.steps ?? [];
  const prevByKey = new Map(
    (funnel?.steps_prev ?? []).map((s) => [s.key, s] as const),
  );

  const openDrill = (
    step: PresaleFunnelStep["key"],
    lost: boolean,
    extra?: { cardSlug?: string; channel?: string },
  ) => setDrill({ step, lost, ...extra });
  const closeDrill = () => {
    setDrill(null);
    setVisitorId(null);
  };

  return (
    <div className="ac-page">
      <div className="ac-page__head">
        <div>
          <div className="page__title">Пресейл</div>
          <div className="ac-page__lead">
            Продаёт ли витрина и где путь встречает человека: посетители →
            интерес к кейсам → диалог с ассистентом → обращение. Провалитесь в
            любой показатель — вплоть до пути конкретного гостя.
          </div>
        </div>
        <div className="ac-filters-row">
          <select
            className="logs-select"
            value={days}
            onChange={(e) => setDays(Number(e.target.value))}
            aria-label="Период"
          >
            {PERIOD_OPTIONS.map((p) => (
              <option key={p.days} value={p.days}>
                {p.label}
              </option>
            ))}
          </select>
          <button type="button" className="logs-page-btn" onClick={() => load(days)}>
            Обновить
          </button>
        </div>
      </div>

      {loading && <Loading />}

      {!loading && error && <EmptyState message={`Ошибка — ${error}`} />}

      {!loading && !error && funnel && (
        <>
          {/* --- KPI: четыре больших числа периода --- */}
          <div className="ps-kpi">
            {steps.map((step) => {
              const prev = prevByKey.get(step.key);
              const delta = prev ? deltaPercent(step.visitors, prev.visitors) : null;
              const up = prev ? step.visitors >= prev.visitors : true;
              return (
                <button
                  key={step.key}
                  type="button"
                  className="ps-kpi__card"
                  onClick={() => openDrill(step.key, false)}
                >
                  <span className="ps-kpi__value">{step.visitors}</span>
                  <span className="ps-kpi__label">{stepTitle(step.key)}</span>
                  <span className="ps-kpi__sub">
                    {step.events}{" "}
                    {step.key === "case_view"
                      ? plural(step.events, STEP_PLURALS.views)
                      : step.key === "inquiry"
                        ? plural(step.events, STEP_PLURALS.inquiries)
                        : plural(step.events, STEP_PLURALS.touches)}
                  </span>
                  {delta && (
                    <span
                      className={`ps-kpi__delta ${up ? "ps-kpi__delta--up" : "ps-kpi__delta--down"}`}
                    >
                      {up ? "▲" : "▼"} {Math.abs(Number(delta.replace("%", "").replace("+", "")))}
                      % к предыдущему периоду
                    </span>
                  )}
                </button>
              );
            })}
          </div>

          {/* --- Сводка конверсий между соседними шагами --- */}
          <div className="ps-flow">
            {steps.slice(1).map((step, i) => {
              const prev = steps[i];
              // В диалоги приходят и без logged-визита (внешние ссылки,
              // бот-трафик) — конверсия честна только вниз по пути.
              const honest = prev.visitors > 0 && step.visitors <= prev.visitors;
              return (
                <span key={step.key} className="ps-flow__item">
                  <span className="ps-flow__value">
                    {honest ? percent(step.visitors, prev.visitors) : "—"}
                  </span>
                  <span className="ps-flow__label">
                    {stepTitle(prev.key)} → {stepTitle(step.key)}
                  </span>
                  {!honest && (
                    <span className="ps-flow__note">
                      трафик приходит мимо предыдущего шага
                    </span>
                  )}
                </span>
              );
            })}
          </div>

          {/* --- Уровень 2: посетители шага / уровень 3: путь гостя --- */}
          {drill && (
            <section className="ps-drill">
              <div className="ps-drill__head">
                <span className="ps-drill__title">
                  {journey
                    ? `Гость ${guestNumber(visitorId)}`
                    : `${stepTitle(drill.step)}${drill.lost ? " — потеряны на шаге" : ""}`}
                  {journey?.geo?.country_code
                    ? ` · ${countryFlag(journey.geo.country_code)} ${journey.geo.country}${journey.geo.city ? `, ${journey.geo.city}` : ""}`
                    : ""}
                  {journey?.ip ? ` · ${journey.ip}` : ""}
                  {drill.cardSlug ? ` · кейс ${drill.cardSlug}` : ""}
                  {drill.channel
                    ? ` · канал ${CHANNEL_LABELS[drill.channel] ?? drill.channel}`
                    : ""}
                </span>
                {journey ? (
                  <button
                    type="button"
                    className="logs-page-btn"
                    onClick={() => setVisitorId(null)}
                  >
                    ← Все гости шага
                  </button>
                ) : (
                  <button type="button" className="logs-page-btn" onClick={closeDrill}>
                    Закрыть
                  </button>
                )}
              </div>

              {!journey && !drill.lost && steps.length > 1 && (
                <div className="ps-drill__tabs">
                  <button
                    type="button"
                    className={`ps-drill__tab ${!drill.lost ? "ps-drill__tab--active" : ""}`}
                    onClick={() => setDrill({ ...drill, lost: false })}
                  >
                    Дошли до шага
                  </button>
                  <button
                    type="button"
                    className={`ps-drill__tab ${drill.lost ? "ps-drill__tab--active" : ""}`}
                    onClick={() => setDrill({ ...drill, lost: true })}
                    disabled={drill.step === "visit"}
                    title={drill.step === "visit" ? "Это первый шаг пути" : undefined}
                  >
                    Потеряны здесь
                  </button>
                </div>
              )}

              {!journey && (
                <div className="ps-drill__sortrow">
                  <label className="ps-drill__sortlabel" htmlFor="ps-sort">
                    Сортировка
                  </label>
                  <select
                    id="ps-sort"
                    className="logs-select"
                    value={sortMode}
                    onChange={(e) => setSortMode(e.target.value as PresaleVisitorSort)}
                  >
                    <option value="value">По ценности (обращения &gt; диалоги &gt; кейсы)</option>
                    <option value="touches">По касаниям</option>
                    <option value="recent">Свежие</option>
                  </select>
                </div>
              )}

              {journeyLoading && <Loading />}

              {journey && (
                <div className="ps-journey">
                  <div className="ps-journey__summary">
                    {journey.touches.length}{" "}
                    {plural(journey.touches.length, STEP_PLURALS.touches)} · первый —{" "}
                    {journey.first_seen ? formatTimestampLocal(journey.first_seen) : "—"} ·
                    последний —{" "}
                    {journey.last_seen ? formatTimestampLocal(journey.last_seen) : "—"}
                  </div>
                  {journey.touches.map((t, i) => (
                    <div key={`${t.ts}-${i}`} className="ps-journey__row">
                      <span className="ps-journey__time">
                        {formatTimestampLocal(t.ts)}
                      </span>
                      <span className={`ps-journey__kind ps-journey__kind--${t.kind}`}>
                        {TOUCH_LABELS[t.kind] ?? t.kind}
                      </span>
                      <span className="ps-journey__detail">
                        {t.kind === "case_view" && (t.title || t.slug)}
                        {t.kind === "inquiry" &&
                          `${CHANNEL_LABELS[t.channel ?? ""] ?? t.channel}${t.label ? ` — ${t.label}` : ""}`}
                        {t.kind === "visit" && t.path}
                        {t.kind === "chat" && t.session_id && (
                          <a
                            href="/admin/conversations"
                            className="ps-journey__link"
                          >
                            открыть диалоги →
                          </a>
                        )}
                      </span>
                    </div>
                  ))}
                </div>
              )}

              {!journey && clusterLoading && <Loading />}

              {!journey && clusterError && (
                <EmptyState message={`Ошибка — ${clusterError}`} />
              )}

              {!journey && cluster && cluster.visitors.length === 0 && (
                <EmptyState
                  message={
                    drill.lost
                      ? "Никто не потерян на этом шаге — все, кто дошёл до предыдущего, прошли дальше."
                      : "В этом сегменте пока никого нет."
                  }
                />
              )}

              {!journey && cluster && cluster.visitors.length > 0 && (
                <>
                  <div className="ps-drill__count">
                    {cluster.visitors.length < cluster.total
                      ? `Показаны ${cluster.visitors.length} из ${cluster.total} ${plural(cluster.total, STEP_PLURALS.visitors)} — верх списка по выбранной сортировке`
                      : `${cluster.total} ${plural(cluster.total, STEP_PLURALS.visitors)}`}
                  </div>
                  <div className="ps-visitor-list">
                    {cluster.visitors.map((v) => (
                      <button
                        key={v.visitor_id}
                        type="button"
                        className="ps-visitor"
                        onClick={() => setVisitorId(v.visitor_id)}
                      >
                        <span className="ps-visitor__id mono" title={v.visitor_id}>
                          {guestNumber(v.visitor_id)}
                        </span>
                        {v.geo?.country_code && (
                          <span
                            className="ps-chip"
                            title={`${v.geo.country}${v.geo.city ? `, ${v.geo.city}` : ""} · ${v.ip ?? ""}`}
                          >
                            {countryFlag(v.geo.country_code)} {v.geo.country}
                          </span>
                        )}
                        <span className="ps-visitor__chips">
                          {v.visits > 0 && (
                            <span className="ps-chip">
                              визиты {v.visits}
                            </span>
                          )}
                          {v.case_views > 0 && (
                            <span className="ps-chip">
                              кейсы {v.case_views}
                            </span>
                          )}
                          {v.chats > 0 && (
                            <span className="ps-chip">диалоги {v.chats}</span>
                          )}
                          {v.inquiries > 0 && (
                            <span className="ps-chip">обращения {v.inquiries}</span>
                          )}
                        </span>
                        {v.cases.length > 0 && (
                          <span className="ps-visitor__cases">{v.cases.join(" · ")}</span>
                        )}
                        <span className="ps-visitor__seen">
                          был здесь {formatTimestampLocal(v.last_seen)}
                        </span>
                      </button>
                    ))}
                  </div>
                </>
              )}
            </section>
          )}

          {/* --- Брейкдауны: кейсы и каналы обращений --- */}
          <div className="ac-layout">
            <div className="ac-col">
              <div className="ac-col__head">
                <span className="ac-col__title">Что смотрят: кейсы</span>
              </div>
              {funnel.top_cases.length === 0 ? (
                <EmptyState message="Просмотров кейсов пока нет — фиксируются при переходе по ссылке кейса на витрине." />
              ) : (
                <div className="ps-list">
                  {(() => {
                    const maxViews = Math.max(...funnel.top_cases.map((c) => c.views), 1);
                    return funnel.top_cases.map((c) => (
                      <button
                        key={c.card_slug}
                        type="button"
                        className="ps-list__row ps-list__row--click"
                        onClick={() => openDrill("case_view", false, { cardSlug: c.card_slug })}
                      >
                        <span className="ps-list__title">{c.card_title}</span>
                        <span className="ps-list__numbers">
                          {c.visitors} {plural(c.visitors, STEP_PLURALS.visitors)} ·{" "}
                          {c.views} {plural(c.views, STEP_PLURALS.views)}
                        </span>
                        <span
                          className="ps-list__bar"
                          style={{ width: `${Math.max((c.views / maxViews) * 100, 4)}%` }}
                        />
                      </button>
                    ));
                  })()}
                </div>
              )}
            </div>

            <div className="ac-col">
              <div className="ac-col__head">
                <span className="ac-col__title">Куда уходят обращения</span>
              </div>
              {funnel.inquiry_channels.length === 0 ? (
                <EmptyState message="Обращений пока нет — фиксируются при переходе по контактной ссылке (Telegram / email)." />
              ) : (
                <div className="ps-list">
                  {(() => {
                    const maxEvents = Math.max(
                      ...funnel.inquiry_channels.map((c) => c.events),
                      1,
                    );
                    return funnel.inquiry_channels.map((ch) => (
                      <button
                        key={ch.channel}
                        type="button"
                        className="ps-list__row ps-list__row--click"
                        onClick={() =>
                          openDrill("inquiry", false, { channel: ch.channel })
                        }
                      >
                        <span className="ps-list__title">
                          {CHANNEL_LABELS[ch.channel] ?? ch.channel}
                        </span>
                        <span className="ps-list__numbers">
                          {ch.visitors} {plural(ch.visitors, STEP_PLURALS.visitors)} ·{" "}
                          {ch.events} {plural(ch.events, STEP_PLURALS.inquiries)}
                        </span>
                        <span
                          className="ps-list__bar"
                          style={{
                            width: `${Math.max((ch.events / maxEvents) * 100, 4)}%`,
                          }}
                        />
                      </button>
                    ));
                  })()}
                </div>
              )}
            </div>
          </div>

          {/* --- География (геообогащение по IP, решение 02.09) --- */}
          <div className="ac-layout">
            <div className="ac-col">
              <div className="ac-col__head">
                <span className="ac-col__title">Откуда гости</span>
                {geoTotals && (
                  <span className="ac-col__meta">
                    {geoTotals.total_visitors}{" "}
                    {plural(geoTotals.total_visitors, STEP_PLURALS.visitors)} ·{" "}
                    {geoTotals.total_visits}{" "}
                    {plural(geoTotals.total_visits, STEP_PLURALS.views)}
                  </span>
                )}
              </div>
              {geoCountries.length === 0 ? (
                <EmptyState message="География пока не определена — требуется база GeoIP на сервере (см. DEPLOYMENT_GUIDE)." />
              ) : (
                <div className="ps-list">
                  {(() => {
                    const maxVisitors = Math.max(
                      ...geoCountries.map((c) => c.visitors),
                      1,
                    );
                    return geoCountries.map((c) => (
                      <div key={c.code} className="ps-list__row">
                        <span className="ps-list__title">
                          {countryFlag(c.code)} {c.country}
                        </span>
                        <span className="ps-list__numbers">
                          {c.visitors} {plural(c.visitors, STEP_PLURALS.visitors)}
                          {typeof c.share === "number" &&
                            ` · ${(c.share * 100).toFixed(0)}%`}
                        </span>
                        <span
                          className="ps-list__bar"
                          style={{
                            width: `${Math.max((c.visitors / maxVisitors) * 100, 4)}%`,
                          }}
                        />
                      </div>
                    ));
                  })()}
                </div>
              )}
            </div>

            <div className="ac-col">
              <div className="ac-col__head">
                <span className="ac-col__title">Обращения по странам</span>
              </div>
              {geoInquiries.length === 0 ? (
                <EmptyState message="Обращений с определённой географией пока нет." />
              ) : (
                <div className="ps-list">
                  {(() => {
                    const maxInq = Math.max(
                      ...geoInquiries.map((c) => c.visitors),
                      1,
                    );
                    return geoInquiries.map((c) => (
                      <div key={c.code} className="ps-list__row">
                        <span className="ps-list__title">
                          {countryFlag(c.code)} {c.country}
                        </span>
                        <span className="ps-list__numbers">
                          {c.visitors} {plural(c.visitors, STEP_PLURALS.visitors)}
                        </span>
                        <span
                          className="ps-list__bar"
                          style={{
                            width: `${Math.max((c.visitors / maxInq) * 100, 4)}%`,
                          }}
                        />
                      </div>
                    ));
                  })()}
                </div>
              )}
            </div>
          </div>
        </>
      )}
    </div>
  );
}