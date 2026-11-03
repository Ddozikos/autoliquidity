import React, { useCallback, useEffect, useMemo, useRef, useState } from 'react';
import { createRoot } from 'react-dom/client';
import './styles.css';

const MAX_FILES = 50;
const MAX_FILE_SIZE = 25 * 1024 * 1024;
const fmt = (value) => Number(value || 0).toLocaleString('ru-RU');
const safeUrl = (value) => {
  try { const url = new URL(value); return ['http:', 'https:'].includes(url.protocol) ? url.href : null; }
  catch { return null; }
};
const shortName = (name = '') => {
  const parts = name.trim().split(/\s+/);
  return parts.length === 3 ? `${parts[0]} ${parts[1][0]}. ${parts[2][0]}.` : name || '—';
};
const demandLabel = (score) => score == null ? null : Number(score) >= 85 ? 'Высокий спрос' : Number(score) >= 70 ? 'Средний спрос' : 'Низкий спрос';
const selectable = (car) => car.doc_type === 'ban' && car.status !== 'В залоге';
const displayRequestName = (name = '') => name.replace(/^Пакет(?=\s|$)/u, 'Запрос');

async function request(path, token, options = {}) {
  const headers = new Headers(options.headers || {});
  if (token) headers.set('Authorization', `Bearer ${token}`);
  const response = await fetch(`/api${path}`, { ...options, headers });
  if (!response.ok) {
    let detail = `Ошибка ${response.status}`;
    try { detail = (await response.json()).detail || detail; } catch { /* response has no JSON body */ }
    if (response.status === 401) { localStorage.removeItem('token'); window.dispatchEvent(new Event('session-expired')); }
    throw new Error(detail);
  }
  return response;
}

function Icon({ name, size = 20 }) {
  const paths = {
    upload: <><path d="M12 16V4"/><path d="m7 9 5-5 5 5"/><path d="M20 16.5v2A1.5 1.5 0 0 1 18.5 20h-13A1.5 1.5 0 0 1 4 18.5v-2"/></>,
    history: <><path d="M3 12a9 9 0 1 0 2.64-6.36L3 8"/><path d="M3 3v5h5"/><path d="M12 7v5l3 2"/></>,
    arrow: <><path d="m15 18-6-6 6-6"/></>,
    chevron: <><path d="m6 9 6 6 6-6"/></>,
    download: <><path d="M12 3v12"/><path d="m7 10 5 5 5-5"/><path d="M5 20h14"/></>,
    trash: <><path d="M4 7h16"/><path d="m10 11 0 6m4-6v6"/><path d="m5 7 1 13h12l1-13M9 7V4h6v3"/></>,
    search: <><circle cx="10.8" cy="10.8" r="6.8"/><path d="m16 16 4 4"/></>,
    close: <><path d="m6 6 12 12M18 6 6 18"/></>,
    check: <><path d="m5 12 4 4L19 6"/></>,
    file: <><path d="M13 3H6a2 2 0 0 0-2 2v14a2 2 0 0 0 2 2h12a2 2 0 0 0 2-2V10z"/><path d="M13 3v7h7"/></>,
    info: <><circle cx="12" cy="12" r="9"/><path d="M12 11v5m0-8h.01"/></>,
    eye: <><path d="M2 12s3.5-7 10-7 10 7 10 7-3.5 7-10 7-10-7-10-7Z"/><circle cx="12" cy="12" r="3"/></>,
  };
  return <svg aria-hidden="true" width={size} height={size} viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.7" strokeLinecap="round" strokeLinejoin="round">{paths[name] || paths.file}</svg>;
}

function Login({ onLogin }) {
  const [email, setEmail] = useState('costarevap@yandex.ru');
  const [password, setPassword] = useState('password123');
  const [showPassword, setShowPassword] = useState(false);
  const [error, setError] = useState('');
  const [busy, setBusy] = useState(false);
  async function submit(event) {
    event.preventDefault(); setError(''); setBusy(true);
    try { await onLogin(email.trim(), password); } catch (err) { setError(err.message || 'Не удалось войти'); }
    finally { setBusy(false); }
  }
  return <main className="login-page"><form className="login-card" onSubmit={submit}>
    <div className="brand-mark large" aria-hidden="true"/><h1>Вход в систему</h1><p>Введите ваши данные для доступа к сервису</p>
    <label>Email<input autoComplete="username" type="email" value={email} onChange={(e) => setEmail(e.target.value)} required /></label>
    <div className="login-password-field"><label htmlFor="login-password">Пароль</label><div className="password-wrap"><input id="login-password" className={`password-input ${showPassword ? 'is-visible' : ''}`} autoComplete="current-password" type={showPassword ? 'text' : 'password'} value={password} onChange={(e) => setPassword(e.target.value)} required/><button type="button" className="password-toggle" onClick={() => setShowPassword((visible) => !visible)} aria-label={showPassword ? 'Скрыть пароль' : 'Показать пароль'} aria-pressed={showPassword}><img src={`/static/icons/${showPassword ? 'eye' : 'eye-slash'}.svg`} alt="" aria-hidden="true"/></button></div></div>
    {error && <div className="inline-error" role="alert">{error}</div>}
    <button className="button primary full" disabled={busy}>{busy ? 'Входим…' : 'Войти'}</button>
  </form></main>;
}

function Sidebar({ view, onView, user, collapsed, setCollapsed, onLogout }) {
  return <aside className={`sidebar ${collapsed ? 'collapsed' : ''}`}>
    <button className="brand" onClick={() => onView('upload')} aria-label="Сервис — загрузка документа"><span className="brand-mark"/><span className="brand-name">Сервис</span></button>
    <nav className="side-nav" aria-label="Основная навигация">
      <button className={view === 'upload' ? 'active' : ''} onClick={() => onView('upload')} title="Загрузка документа"><Icon name="upload"/><span>Загрузка документа</span></button>
      <button className={view === 'history' ? 'active' : ''} onClick={() => onView('history')} title="История запросов"><Icon name="history"/><span>История запросов</span></button>
    </nav>
    <div className="sidebar-bottom">
      <div className="user-mini"><div className="avatar">{(user?.name || user?.email || 'С')[0].toUpperCase()}</div><div className="user-mini-text"><strong>{user?.name || user?.email}</strong><span>{user?.email}</span></div><button className="logout" onClick={onLogout} title="Выйти">↪</button></div>
      <button className="collapse-button" onClick={() => setCollapsed(!collapsed)} aria-label={collapsed ? 'Развернуть меню' : 'Свернуть меню'}><span>{collapsed ? '›' : '‹'}</span></button>
    </div>
  </aside>;
}

function UploadPage({ token, onReport, notify }) {
  const inputRef = useRef(null);
  const [files, setFiles] = useState([]);
  const [minPrice, setMinPrice] = useState('300 000');
  const [error, setError] = useState('');
  const [busy, setBusy] = useState(false);
  const [dragging, setDragging] = useState(false);
  const addFiles = (incoming) => {
    const next = [...files], errors = [];
    for (const file of Array.from(incoming || [])) {
      const ext = file.name.split('.').pop().toLowerCase();
      if (!['pdf', 'html', 'htm'].includes(ext)) { errors.push(`${file.name}: разрешены PDF и HTML.`); continue; }
      if (file.size > MAX_FILE_SIZE) { errors.push(`${file.name}: файл больше 25 МБ.`); continue; }
      if (next.length >= MAX_FILES) { errors.push('Достигнут лимит: максимум 50 файлов.'); break; }
      if (!next.some((item) => item.name === file.name && item.size === file.size)) next.push(file);
    }
    setFiles(next); setError(errors.join(' '));
  };
  async function processFiles() {
    if (!files.length || busy) return;
    setBusy(true); setError('');
    const body = new FormData(); files.forEach((file) => body.append('files', file));
    body.append('min_price', minPrice.replace(/\D/g, '') || '300000'); body.append('min_demand', '70');
    try {
      const response = await request('/process', token, { method: 'POST', body });
      const data = await response.json(); setFiles([]); onReport(data.report_id);
    } catch (err) { setError(err.message); notify(err.message); }
    finally { setBusy(false); }
  }
  const formatDebt = (value) => value.replace(/\D/g, '').replace(/\B(?=(\d{3})+(?!\d))/g, ' ');
  return <section className="upload-card">
    <h1>Загрузка документа</h1><p className="muted intro">Загрузите до 50 файлов с документами. После обработки запроса вы получите таблицу с результатами.</p>
    <label className="debt-input"><span>Минимальная сумма долга</span><div className="input-wrap"><input inputMode="numeric" value={minPrice} onChange={(e) => setMinPrice(formatDebt(e.target.value))}/><span>руб</span></div></label>
    {error && <div className="inline-error" role="alert">{error}</div>}
    <div className={`dropzone ${dragging ? 'dragging' : ''}`} role="button" tabIndex="0" onClick={() => inputRef.current?.click()} onKeyDown={(e) => ['Enter', ' '].includes(e.key) && inputRef.current?.click()} onDragEnter={(e) => { e.preventDefault(); setDragging(true); }} onDragOver={(e) => e.preventDefault()} onDragLeave={(e) => { e.preventDefault(); setDragging(false); }} onDrop={(e) => { e.preventDefault(); setDragging(false); addFiles(e.dataTransfer.files); }}>
      <div className="upload-icon"><Icon name="upload" size={28}/></div><strong>Перенесите сюда файлы</strong><span>или <b>выберите файл</b> в формате .pdf и .html</span>
      <input ref={inputRef} hidden type="file" multiple accept=".pdf,.html,.htm" onChange={(e) => { addFiles(e.target.files); e.target.value = ''; }}/>
    </div>
    {files.length > 0 && <div className="file-list"><div className="file-list-head"><strong>Загруженные файлы ({files.length}/{MAX_FILES})</strong><button className="text-button" onClick={() => { setFiles([]); setError(''); }}>Очистить</button></div>
      <div className="files-scroll">{files.map((file, index) => <div className="file-row" key={`${file.name}-${file.size}-${index}`}><span className="file-icon"><Icon name="file"/></span><span className="file-meta"><strong title={file.name}>{file.name}</strong><small>{file.size < 1048576 ? `${Math.max(1, Math.round(file.size / 1024))} КБ` : `${(file.size / 1048576).toFixed(1)} МБ`}</small></span><button className="icon-button remove" onClick={() => setFiles(files.filter((_, itemIndex) => itemIndex !== index))} aria-label={`Удалить ${file.name}`}><Icon name="close"/></button></div>)}</div>
    </div>}
    {files.length > 0 && <div className="card-actions"><button className="button primary" disabled={busy} onClick={processFiles}>{busy ? 'Обработка…' : 'Запустить обработку'}</button></div>}
  </section>;
}

function HistoryPage({ token, onOpen, notify }) {
  const [rows, setRows] = useState([]), [sort, setSort] = useState({ column: 'date', direction: 'desc' }), [loading, setLoading] = useState(true), [downloading, setDownloading] = useState(null);
  const load = useCallback(async () => {
    setLoading(true);
    try { const response = await request('/reports', token); setRows(await response.json()); }
    catch (err) { notify(err.message); }
    finally { setLoading(false); }
  }, [token, notify]);
  useEffect(() => { load(); }, [load]);
  async function rename(id, name) {
    const value = name.trim(); if (!value) return;
    try { await request(`/reports/${id}`, token, { method: 'PATCH', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify({ name: value }) }); setRows((prev) => prev.map((row) => row.id === id ? { ...row, name: value } : row)); }
    catch (err) { notify(err.message); }
  }
  async function downloadReport(id) {
    setDownloading(id);
    try {
      const detailResponse = await request(`/reports/${id}`, token), detail = await detailResponse.json();
      if (detail.status !== 'ready') throw new Error('Дождитесь завершения обработки отчёта');
      const ids = detail.cars.filter(selectable).map((car) => car.id);
      if (!ids.length) throw new Error('Нет подходящих записей для выгрузки');
      const response = await request(`/reports/${id}/export?ids=${encodeURIComponent(ids.join(','))}`, token);
      const url = URL.createObjectURL(await response.blob()), link = document.createElement('a');
      link.href = url; link.download = `report_${id}.xlsx`; link.click(); URL.revokeObjectURL(url);
    } catch (err) { notify(err.message); }
    finally { setDownloading(null); }
  }
  const filtered = useMemo(() => [...rows].sort((a, b) => {
    const left = sort.column === 'name' ? a.name : sort.column === 'user' ? (a.user || '') : a.created_at, right = sort.column === 'name' ? b.name : sort.column === 'user' ? (b.user || '') : b.created_at;
    return (left < right ? -1 : left > right ? 1 : 0) * (sort.direction === 'asc' ? 1 : -1);
  }), [rows, sort]);
  const toggleSort = (column) => setSort((current) => ({ column, direction: current.column === column && current.direction === 'asc' ? 'desc' : 'asc' }));
  return <section className="history-page"><h1>История запросов</h1>
    <div className="table-scroll"><table className="history-table"><thead><tr><th><button className="sort-button" onClick={() => toggleSort('name')}>Название <span>↕</span></button></th><th><button className="sort-button" onClick={() => toggleSort('date')}>Дата <span>↕</span></button></th><th><button className="sort-button" onClick={() => toggleSort('user')}>Пользователь <span>↕</span></button></th><th className="right">Действия</th></tr></thead>
    <tbody>{loading ? <tr><td colSpan="4" className="empty-cell">Загружаем историю…</td></tr> : filtered.length ? filtered.map((row) => {
      const date = new Date(row.created_at);
      return <tr key={row.id} onClick={() => onOpen(row.id)}><td><span className="editable-name" contentEditable suppressContentEditableWarning role="textbox" aria-label="Название запроса" onClick={(e) => e.stopPropagation()} onKeyDown={(e) => { if (e.key === 'Enter') { e.preventDefault(); e.currentTarget.blur(); } }} onBlur={(e) => rename(row.id, e.currentTarget.textContent)}>{displayRequestName(row.name)}</span></td><td className="date-cell">{date.toLocaleDateString('ru-RU')}</td><td><span className="user-cell"><span className="avatar small">{(row.user || 'С')[0].toUpperCase()}</span>{row.user || '—'}</span></td><td className="right action-cell"><button className="icon-button" title="Просмотр" aria-label="Просмотр отчёта" onClick={(e) => { e.stopPropagation(); onOpen(row.id); }}><Icon name="eye"/></button><button className="icon-button" title="Скачать" aria-label="Скачать отчёт" disabled={downloading === row.id} onClick={(e) => { e.stopPropagation(); downloadReport(row.id); }}><Icon name="download"/></button></td></tr>;
    }) : <tr><td colSpan="4" className="empty-cell">Запросы не найдены</td></tr>}</tbody></table></div>
  </section>;
}

function StatusBadge({ car }) {
  const review = Number(car.confidence) < .7;
  const label = review ? 'Требует обработки' : demandLabel(car.demand) || (car.status === 'В залоге' ? 'В залоге' : car.status === 'Свободно' ? 'Свободно' : 'Нет данных');
  const tone = review ? 'warning' : label === 'Высокий спрос' || label === 'Свободно' ? 'success' : label === 'Средний спрос' ? 'info' : label === 'В залоге' ? 'orange' : 'neutral';
  return <span className={`status-badge ${tone}`} title={review ? 'Проверьте распознанные поля вручную' : `Статус проверки: ${car.status || 'не проверен'}`}>{label}</span>;
}

function ReportPage({ token, reportId, onUpload, notify }) {
  const [report, setReport] = useState(null), [loading, setLoading] = useState(true), [error, setError] = useState(''), [filter, setFilter] = useState(''), [filterOpen, setFilterOpen] = useState(false), [alertVisible, setAlertVisible] = useState(true), [page, setPage] = useState(1), [selected, setSelected] = useState(new Set()), [modalCar, setModalCar] = useState(null), [downloading, setDownloading] = useState(false);
  const timer = useRef(null);
  const filterRef = useRef(null);
  const refresh = useCallback(async (id, first = false) => {
    try {
      const response = await request(`/reports/${id}`, token), data = await response.json();
      setReport(data); setError(''); setLoading(data.status === 'processing');
      if (data.status === 'processing') timer.current = setTimeout(() => refresh(id), 1800);
      else setSelected((existing) => existing.size ? existing : new Set((data.cars || []).filter(selectable).map((car) => car.id)));
    } catch (err) { setError(err.message); setLoading(false); }
  }, [token]);
  useEffect(() => { setReport(null); setError(''); setLoading(true); setSelected(new Set()); refresh(reportId, true); return () => clearTimeout(timer.current); }, [reportId, refresh]);
  useEffect(() => {
    const closeOnOutside = (event) => { if (filterRef.current && !filterRef.current.contains(event.target)) setFilterOpen(false); };
    document.addEventListener('pointerdown', closeOnOutside);
    return () => document.removeEventListener('pointerdown', closeOnOutside);
  }, []);
  const cars = report?.cars || [];
  const rows = useMemo(() => {
    if (!filter || filter === 'Выбрать все') return cars;
    if (filter === 'Требует проверки') return cars.filter((car) => Number(car.confidence) < .7);
    return cars.filter((car) => demandLabel(car.demand) === filter);
  }, [cars, filter]);
  const pageCount = Math.max(1, Math.ceil(rows.length / 10));
  useEffect(() => { if (page > pageCount) setPage(pageCount); }, [page, pageCount]);
  const visible = rows.slice((page - 1) * 10, page * 10);
  const eligibleVisible = visible.filter(selectable);
  const toggle = (id) => setSelected((prev) => { const next = new Set(prev); next.has(id) ? next.delete(id) : next.add(id); return next; });
  const toggleVisible = (checked) => setSelected((prev) => { const next = new Set(prev); eligibleVisible.forEach((car) => checked ? next.add(car.id) : next.delete(car.id)); return next; });
  const allVisibleSelected = eligibleVisible.length > 0 && eligibleVisible.every((car) => selected.has(car.id));
  async function download() {
    if (!selected.size) return; setDownloading(true);
    try { const response = await request(`/reports/${reportId}/export?ids=${encodeURIComponent([...selected].join(','))}`, token); const blob = await response.blob(); const url = URL.createObjectURL(blob); const link = document.createElement('a'); link.href = url; link.download = `report_${reportId}.xlsx`; link.click(); URL.revokeObjectURL(url); }
    catch (err) { notify(`Не удалось скачать отчёт: ${err.message}`); }
    finally { setDownloading(false); }
  }
  const tabStart = Math.max(1, Math.min(page - 2, pageCount - 4));
  const pageNumbers = Array.from({ length: Math.min(5, pageCount) }, (_, index) => tabStart + index);
  const statusOptions = ['Выбрать все', 'Высокий спрос', 'Средний спрос', 'Низкий спрос', 'Требует проверки'];
  return <section className="report-page">
    <div className="report-heading"><h1>Просмотр отчета</h1><button className="button primary" onClick={onUpload}>Загрузить постановление</button></div>
    {loading && alertVisible && <div className="alert info" role="status"><Icon name="info"/><div><strong>Идет процесс обработки</strong><p>Пожалуйста, подождите: в данный момент выполняется обработка загруженных файлов и формирование отчета. После завершения обработки готовый отчет станет доступен для скачивания в формате Excel (.xlsx). Это может занять некоторое время.</p></div><button className="alert-close" onClick={() => setAlertVisible(false)} aria-label="Закрыть"><Icon name="close" size={16}/></button></div>}
    {!loading && !error && report?.status === 'ready' && alertVisible && <div className="alert success"><Icon name="check"/><div><strong>Документ обработан</strong><p>Готовый файл доступен для загрузки в формате XLSX.</p></div><button className="alert-close" onClick={() => setAlertVisible(false)} aria-label="Закрыть"><Icon name="close" size={16}/></button></div>}
    {(error || report?.error_text) && !loading && alertVisible && <div className="alert danger" role="alert"><Icon name="info"/><div><strong>Не удалось полностью обработать пакет</strong><p>{error || report.error_text}</p></div><button className="text-button" onClick={() => refresh(reportId)}>Повторить</button><button className="alert-close" onClick={() => setAlertVisible(false)} aria-label="Закрыть"><Icon name="close" size={16}/></button></div>}
    <div className="query-heading"><h2>Запрос</h2><button className="button primary download-button" disabled={!selected.size || downloading || loading} onClick={download}><Icon name="download"/>{downloading ? 'Подготовка…' : 'Скачать'}</button></div>
    <div className="report-controls"><div ref={filterRef} className="status-select" onKeyDown={(e) => e.key === 'Escape' && setFilterOpen(false)}>
      <button className={`status-select-trigger ${filterOpen ? 'open' : ''}`} aria-haspopup="listbox" aria-expanded={filterOpen} onClick={() => setFilterOpen((open) => !open)}><span>{filter || 'Статус'}</span><Icon name="chevron" size={16}/></button>
      {filterOpen && <div className="status-options" role="listbox" aria-label="Статус">{statusOptions.map((option) => <button key={option} role="option" aria-selected={filter === option || (!filter && option === 'Выбрать все')} onClick={() => { setFilter(option === 'Выбрать все' ? '' : option); setPage(1); setFilterOpen(false); }}>{option}</button>)}</div>}
    </div><span className="result-count">{cars.length} автомобилей в отчёте</span></div>
    <nav className="page-tabs" aria-label="Страницы отчёта">{pageNumbers.map((number) => <button key={number} className={page === number ? 'current' : ''} aria-current={page === number ? 'page' : undefined} onClick={() => setPage(number)}>{number}</button>)}</nav>
    <div className="report-table-scroll"><table className="report-table"><colgroup><col className="col-check"/><col className="col-name"/><col className="col-inn"/><col className="col-debt"/><col className="col-vin"/><col className="col-car"/><col className="col-plate"/><col className="col-status"/><col className="col-price"/></colgroup><thead><tr><th className="check-col"><input type="checkbox" aria-label="Выбрать видимые строки" checked={allVisibleSelected} onChange={(e) => toggleVisible(e.target.checked)} disabled={!eligibleVisible.length}/></th><th>ФИО должника</th><th>ИНН</th><th>Долг</th><th>VIN</th><th>Автомобиль</th><th>Номер</th><th>Статус</th><th>Цена рынка</th></tr></thead>
      <tbody>{loading ? Array.from({ length: 7 }, (_, i) => <tr className="skeleton-row" key={i}><td colSpan="9"><span/></td></tr>) : visible.length ? visible.map((car) => {
        const vehicle = [car.make, car.model, car.year].filter(Boolean).join(' ') || '—';
        const offers = car.market_sources || [];
        const vinInfo = car.vin_error ? `Ошибка проверки VIN: ${car.vin_error}` : car.vin_source ? `Проверка VIN: ${car.vin_source}` : 'Источник проверки VIN не подключён';
        return <tr key={car.id} className={car.doc_type === 'removal' ? 'removed-row' : ''}>
          <td className="check-col"><input type="checkbox" checked={selected.has(car.id)} disabled={!selectable(car)} onChange={() => toggle(car.id)} aria-label={`Выбрать ${car.debtor_name || 'строку'}`}/></td>
          <td className="debtor-cell" title={car.debtor_name || ''}>{shortName(car.debtor_name)}</td><td className="inn-cell">{car.inn || '—'}</td><td className="debt-cell">{Number(car.debt_amount) ? fmt(car.debt_amount) : '—'}</td><td className="vin-cell" title={vinInfo}>{car.vin || '—'}</td><td className="vehicle-cell" title={vehicle}>{vehicle}</td><td>{car.plate || '—'}</td>
          <td><StatusBadge car={car}/></td>
          <td>{Number(car.price) > 0 ? <button className="price-link" title={car.market_error || `${offers.length} предложений`} onClick={() => offers.length && setModalCar(car)}>{fmt(car.price)}</button> : <span className="no-data" title={car.market_error || 'Цены пока нет'}>Нет данных</span>}</td>
        </tr>;
      }) : <tr><td colSpan="9" className="empty-cell">{cars.length ? 'Нет данных, удовлетворяющих условиям фильтра' : 'В отчёте пока нет записей'}</td></tr>}</tbody>
    </table></div>
    {modalCar && <div className="modal-backdrop" onMouseDown={(e) => e.target === e.currentTarget && setModalCar(null)}><section className="offers-modal" role="dialog" aria-modal="true" aria-labelledby="offers-title"><header><div><h2 id="offers-title">Объявления: {[modalCar.make, modalCar.model].filter(Boolean).join(' ') || 'автомобиль'}</h2><p>Средняя цена: {modalCar.price ? `${fmt(modalCar.price)} ₽` : 'нет данных'} · {(modalCar.market_sources || []).length} предложений</p></div><button className="icon-button" onClick={() => setModalCar(null)} aria-label="Закрыть"><Icon name="close"/></button></header><div className="offers-list">{(modalCar.market_sources || []).length ? modalCar.market_sources.map((offer, index) => <article key={`${offer.url}-${index}`}><div><strong>{offer.title || offer.source || `Объявление ${index + 1}`}</strong><small>{offer.source || 'Источник'}</small></div><b>{fmt(offer.price)} ₽</b>{safeUrl(offer.url) && <a href={safeUrl(offer.url)} target="_blank" rel="noopener noreferrer">Открыть</a>}</article>) : <p>Источники пока не вернули объявлений.</p>}</div></section></div>}
  </section>;
}

function App() {
  const [token, setToken] = useState(() => localStorage.getItem('token'));
  const [user, setUser] = useState(null), [view, setView] = useState('upload'), [reportId, setReportId] = useState(null), [collapsed, setCollapsed] = useState(() => localStorage.getItem('sidebarCollapsed') === 'true'), [toast, setToast] = useState('');
  const toastTimer = useRef(null);
  const notify = useCallback((message) => { setToast(message); clearTimeout(toastTimer.current); toastTimer.current = setTimeout(() => setToast(''), 7000); }, []);
  const login = async (email, password) => {
    const response = await fetch('/api/login', { method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify({ email, password }) });
    const data = await response.json(); if (!response.ok) throw new Error(data.detail || 'Не удалось войти');
    localStorage.setItem('token', data.access_token); setToken(data.access_token); setUser(data.user); setView('upload');
  };
  const logout = () => { localStorage.removeItem('token'); setToken(null); setUser(null); setReportId(null); setView('upload'); };
  useEffect(() => {
    if (!token) return;
    let alive = true;
    request('/me', token).then((response) => response.json()).then((data) => { if (alive) setUser(data); }).catch(() => { if (alive) logout(); });
    const expired = () => logout(); window.addEventListener('session-expired', expired);
    return () => { alive = false; window.removeEventListener('session-expired', expired); };
  }, [token]);
  const navigate = (target) => { setView(target); if (target === 'history') setReportId(null); };
  const openReport = (id) => { setReportId(id); setView('report'); };
  const toggleCollapse = (value) => { setCollapsed(value); localStorage.setItem('sidebarCollapsed', String(value)); };
  if (!token || !user) return <Login onLogin={login}/>;
  return <div className="app-shell"><Sidebar view={view} onView={navigate} user={user} collapsed={collapsed} setCollapsed={toggleCollapse} onLogout={logout}/><main className={`main-content ${view === 'report' ? 'report-background' : view === 'history' ? 'history-background' : ''}`}>
    {toast && <div className="toast" role="alert">{toast}<button onClick={() => setToast('')} aria-label="Закрыть"><Icon name="close" size={16}/></button></div>}
    {view === 'upload' && <div className="page-center"><UploadPage token={token} onReport={openReport} notify={notify}/></div>}
    {view === 'history' && <HistoryPage token={token} onOpen={openReport} notify={notify}/>}
    {view === 'report' && reportId && <ReportPage key={reportId} token={token} reportId={reportId} onUpload={() => navigate('upload')} notify={notify}/>}
  </main></div>;
}

createRoot(document.getElementById('root')).render(<React.StrictMode><App/></React.StrictMode>);
