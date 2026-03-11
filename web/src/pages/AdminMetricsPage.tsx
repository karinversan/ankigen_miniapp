import { useEffect, useState } from "react";
import { useNavigate } from "react-router-dom";
import {
  authMe,
  downloadAdminMetricsReport,
  runAdminMetricsReport,
  sendAdminMetricsReport
} from "../api/client";
import { useAutoDismiss } from "../hooks/useAutoDismiss";
import { getWebApp } from "../telegram";
import type { AdminMetricsReport } from "../api/types";

const metricToNumber = (value: unknown): number | null => {
  if (typeof value === "number" && Number.isFinite(value)) return value;
  if (typeof value === "string") {
    const parsed = Number(value);
    if (Number.isFinite(parsed)) return parsed;
  }
  return null;
};

export default function AdminMetricsPage() {
  const navigate = useNavigate();
  const [ready, setReady] = useState(false);
  const [isAdmin, setIsAdmin] = useState(false);
  const [limit, setLimit] = useState(50);
  const [loading, setLoading] = useState(false);
  const [sending, setSending] = useState(false);
  const [error, setError] = useAutoDismiss<string>(null);
  const [notice, setNotice] = useAutoDismiss<string>(null);
  const [report, setReport] = useState<AdminMetricsReport | null>(null);
  const clampLimit = (value: number) => Math.min(500, Math.max(5, value));

  useEffect(() => {
    const loadMe = async () => {
      try {
        const me = await authMe();
        setIsAdmin(Boolean(me.is_admin));
      } catch {
        setIsAdmin(false);
      } finally {
        setReady(true);
      }
    };
    loadMe();
  }, []);

  const onRun = async () => {
    setError(null);
    setNotice(null);
    setLoading(true);
    try {
      const payload = await runAdminMetricsReport(limit);
      setReport(payload);
      setNotice("Отчёт сформирован");
    } catch {
      setError("Не удалось сформировать отчёт");
    } finally {
      setLoading(false);
    }
  };

  const onDownload = async (format: "json" | "md") => {
    if (!report?.report_id) return;
    setError(null);
    setNotice(null);
    setLoading(true);
    try {
      await downloadAdminMetricsReport(report.report_id, format);
    } catch {
      setError("Не удалось скачать отчёт");
    } finally {
      setLoading(false);
    }
  };

  const onSend = async () => {
    if (!report?.report_id) return;
    setError(null);
    setNotice(null);
    setSending(true);
    try {
      await sendAdminMetricsReport(report.report_id, "md");
      setNotice("Отчёт отправлен в Telegram");
    } catch {
      setError("Не удалось отправить отчёт");
    } finally {
      setSending(false);
    }
  };

  const onCloseMiniApp = () => {
    const webApp = getWebApp();
    if (webApp?.close) {
      webApp.close();
      return;
    }
    navigate("/");
  };

  const summary =
    report?.summary && typeof report.summary === "object"
      ? (report.summary as Record<string, unknown>)
      : null;
  const e2eRaw =
    summary?.e2e_seconds && typeof summary.e2e_seconds === "object"
      ? (summary.e2e_seconds as Record<string, unknown>)
      : null;
  const qualityRaw =
    summary?.quality_score && typeof summary.quality_score === "object"
      ? (summary.quality_score as Record<string, unknown>)
      : null;
  const throughputRaw =
    summary?.throughput_qps && typeof summary.throughput_qps === "object"
      ? (summary.throughput_qps as Record<string, unknown>)
      : null;

  const e2eP50 = metricToNumber(e2eRaw?.p50);
  const e2eP95 = metricToNumber(e2eRaw?.p95);
  const qualityMean = metricToNumber(qualityRaw?.mean);
  const throughputMean = metricToNumber(throughputRaw?.mean);

  if (!ready) return <div className="centered">Loading...</div>;

  if (!isAdmin) {
    return (
      <div className="page">
        <header className="page-header">
          <h1>Метрики</h1>
          <button className="ghost" onClick={() => navigate("/")}>
            Назад
          </button>
        </header>
        <div className="panel">
          <p className="muted">Страница доступна только администратору.</p>
        </div>
      </div>
    );
  }

  return (
    <div className="page">
      <header className="page-header">
        <div className="page-header-left">
          <button className="ghost" onClick={() => navigate("/")}>
            Назад
          </button>
          <div>
            <h1>Отчёт по метрикам</h1>
            <p className="page-subtitle">Скорость и качество по последним генерациям.</p>
          </div>
        </div>
        <button className="ghost" onClick={onCloseMiniApp}>
          Выйти
        </button>
      </header>

      {error && <div className="error">{error}</div>}
      {notice && <div className="notice">{notice}</div>}

      <div className="panel form">
        <div className="field-row">
          <div>
            <div className="field-label">Окно анализа</div>
            <div className="field-subtitle">Последние 5–500 завершённых задач</div>
          </div>
          <div className="stepper">
            <button className="ghost" type="button" onClick={() => setLimit(clampLimit(limit - 5))}>
              −
            </button>
            <input
              type="number"
              min={5}
              max={500}
              value={limit}
              onChange={(e) => setLimit(clampLimit(Number(e.target.value) || 5))}
            />
            <button className="ghost" type="button" onClick={() => setLimit(clampLimit(limit + 5))}>
              +
            </button>
          </div>
        </div>
        <button className="primary" type="button" onClick={onRun} disabled={loading || sending}>
          {loading ? "Считаем..." : "Сформировать отчёт"}
        </button>
      </div>

      {report && (
        <div className="panel status">
          <h2>Сводка</h2>
          <div className="summary">
            <div className="summary-row">
              <span className="muted">Jobs analyzed</span>
              <span>{report.jobs_analyzed}</span>
            </div>
            <div className="summary-row">
              <span className="muted">Report ID</span>
              <span className="truncate">{report.report_id}</span>
            </div>
            {e2eP50 !== null && (
              <div className="summary-row">
                <span className="muted">E2E p50</span>
                <span>{e2eP50.toFixed(2)} сек</span>
              </div>
            )}
            {e2eP95 !== null && (
              <div className="summary-row">
                <span className="muted">E2E p95</span>
                <span>{e2eP95.toFixed(2)} сек</span>
              </div>
            )}
            {qualityMean !== null && (
              <div className="summary-row">
                <span className="muted">Quality mean</span>
                <span>{qualityMean.toFixed(1)} / 100</span>
              </div>
            )}
            {throughputMean !== null && (
              <div className="summary-row">
                <span className="muted">Throughput mean</span>
                <span>{throughputMean.toFixed(2)} questions/sec</span>
              </div>
            )}
          </div>
          <div className="status-actions">
            <button className="ghost" type="button" onClick={() => onDownload("json")} disabled={loading || sending}>
              Скачать JSON
            </button>
            <button className="ghost" type="button" onClick={() => onDownload("md")} disabled={loading || sending}>
              Скачать MD
            </button>
            <button className="primary" type="button" onClick={onSend} disabled={loading || sending}>
              {sending ? "Отправка..." : "Отправить в Telegram"}
            </button>
          </div>
        </div>
      )}
    </div>
  );
}
