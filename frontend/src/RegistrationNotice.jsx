import React, { useState } from 'react';

export default function RegistrationNotice({ profile, completeRegistration }) {
  const [busy, setBusy] = useState(false), [error, setError] = useState('');
  const status = profile?.registration;
  if (!status || status.complete) return null;
  return <section className="card registration-notice" aria-label="Завершение регистрации">
    <div><h2>Завершите регистрацию, чтобы откликаться</h2>
      <p className="muted">Работодателю нужны ваши контактные данные и заполненный профиль. Результат вводного теста может быть любым — подтверждение грейда оценивается отдельно.</p>
      {status.issues.length ? <ul>{status.issues.map(issue => <li key={issue.message}><a href={'#' + issue.url}>{issue.message}</a></li>)}</ul> : <p>Анкета и вводный тест сохранены. Подтвердите завершение регистрации.</p>}
      {error && <p role="alert" className="auth-error">{error}</p>}
    </div>
    {status.can_complete && <button className="pill primary" disabled={busy} onClick={async () => {
      setBusy(true); setError('');
      try { await completeRegistration(); } catch (e) { setError(e.message); } finally { setBusy(false); }
    }}>{busy ? 'Сохраняем…' : 'Завершить регистрацию'}</button>}
  </section>;
}
