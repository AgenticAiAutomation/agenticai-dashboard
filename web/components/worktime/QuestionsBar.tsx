'use client';

import { useCallback, useEffect, useState } from 'react';
import { ErrorBanner } from '@/components/ui';
import { msg } from '@/lib/tracker';
import { QInbox, QThread, clock, wtApi } from '@/lib/worktime';

/* v3 Q&A on top of the dashboard and the Tasks page. Jai asks one person about their work; only the two
   of them see it. Red = waiting for you. Done threads go to history (a year back). Hidden when v3 is off. */

const when = (iso: string) => `${new Date(iso).toLocaleDateString('en-IN', { day: 'numeric', month: 'short' })} ${clock(iso)}`;

function Thread({ q, me, isSuper, onReply, onDone, onReopen }: {
  q: QThread; me: string; isSuper: boolean;
  onReply?: (body: string) => Promise<boolean>; onDone?: () => void; onReopen?: () => void;
}) {
  const [text, setText] = useState('');
  const mine = q.status === 'open' ? !isSuper : isSuper && q.status === 'answered';
  return (
    <li className={`rounded-lg border p-3 text-sm ${mine ? 'border-red-500/60 bg-red-500/10' : 'border-line bg-raised'}`}>
      <p className="text-xs text-muted">
        {isSuper ? <>To <b className="text-white">{q.to_name ?? q.to_user}</b></> : 'Jai asks'}
        {q.task_title && <> · about “{q.task_title}”</>} · {when(q.created_at)}
        {q.status === 'answered' && !isSuper && ' · sent, waiting for Jai'}
        {q.status === 'open' && isSuper && ' · waiting for their answer'}
      </p>
      <ul className="mt-2 space-y-1">
        {q.messages.map((m) => (
          <li key={m.id} className={m.user_id === me ? 'text-slate-300' : 'text-white'}>
            <b>{m.user_id === me ? 'You' : m.name}:</b> <span className="whitespace-pre-line">{m.body}</span>
            <span className="ml-2 text-xs text-muted">{clock(m.created_at)}</span>
          </li>
        ))}
      </ul>
      {onReply && (
        <form className="mt-2 flex flex-wrap gap-2" onSubmit={(e) => { e.preventDefault(); onReply(text).then((ok) => ok && setText('')); }}>
          <input aria-label="Your answer" required maxLength={2000} className="input-field flex-1" placeholder={isSuper ? 'Ask more…' : 'Your answer…'}
                 value={text} onChange={(e) => setText(e.target.value)} />
          <button className={mine && !isSuper ? 'btn-danger' : 'btn-secondary'} type="submit">{isSuper ? 'Send' : 'Answer'}</button>
          {onDone && <button type="button" className="btn-primary" onClick={onDone}>Done ✓</button>}
        </form>
      )}
      {onReopen && <button className="mt-2 text-xs text-muted underline hover:text-white" onClick={onReopen}>Reopen</button>}
    </li>
  );
}

export default function QuestionsBar() {
  const [b, setB] = useState<QInbox | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [asking, setAsking] = useState(false);
  const [ask, setAsk] = useState({ to_user: '', task_id: '', question: '' });
  const [hist, setHist] = useState<QThread[] | null>(null);
  const [search, setSearch] = useState({ q: '', who: '' });

  const load = useCallback(() => { wtApi.questions().then((r) => setB(r.data)).catch(() => setB(null)); }, []);
  useEffect(() => { load(); const id = setInterval(load, 60000); return () => clearInterval(id); }, [load]);

  const run = (p: Promise<{ data: QInbox }>) =>
    p.then((r) => { setB(r.data); setError(null); return true; }).catch((e) => { setError(msg(e, 'That did not work.')); return false; });
  const findHistory = () => wtApi.questionHistory(search.q, search.who).then((r) => setHist(r.data.threads))
    .catch((e) => setError(msg(e, 'Could not load the history.')));

  if (!b || (!b.isSuperuser && b.threads.length === 0 && hist === null)) {
    return b && !b.isSuperuser ? <button className="mb-4 text-xs text-muted underline" onClick={findHistory}>Q&amp;A history</button> : null;
  }
  const waiting = b.threads.filter((q) => (b.isSuperuser ? q.status === 'answered' : q.status === 'open'));
  const other = b.threads.filter((q) => !waiting.includes(q));
  const person = b.people?.find((p) => p.user_id === ask.to_user);

  return (
    <section className="mb-6 space-y-3" aria-label="Questions from Jai">
      <ErrorBanner message={error} />
      {waiting.length > 0 && (
        <div className="rounded-xl border border-red-500/60 bg-red-500/5 p-4">
          <h2 className="mb-2 text-sm font-semibold text-red-300">
            {b.isSuperuser ? `${waiting.length} answer${waiting.length > 1 ? 's' : ''} to review` : `Jai is asking (${waiting.length}) · please answer`}
          </h2>
          <ul className="space-y-2">
            {waiting.map((q) => (
              <Thread key={q.id} q={q} me={b.me} isSuper={b.isSuperuser}
                      onReply={(t) => run(wtApi.replyQuestion(q.id, t))}
                      onDone={b.isSuperuser ? () => run(wtApi.questionDone(q.id)) : undefined} />
            ))}
          </ul>
        </div>
      )}
      {other.length > 0 && (
        <details className="rounded-xl border border-line bg-surface p-4">
          <summary className="cursor-pointer text-sm text-slate-200">
            {b.isSuperuser ? `Waiting for their answer (${other.length})` : `Sent, waiting for Jai (${other.length})`}
          </summary>
          <ul className="mt-2 space-y-2">
            {other.map((q) => (
              <Thread key={q.id} q={q} me={b.me} isSuper={b.isSuperuser}
                      onReply={b.isSuperuser ? (t) => run(wtApi.replyQuestion(q.id, t)) : undefined}
                      onDone={b.isSuperuser ? () => run(wtApi.questionDone(q.id)) : undefined} />
            ))}
          </ul>
        </details>
      )}
      <div className="flex flex-wrap gap-3 text-xs">
        {b.isSuperuser && <button className="btn-secondary" onClick={() => setAsking(!asking)}>{asking ? 'Close' : 'Ask someone a question'}</button>}
        <button className="text-muted underline hover:text-white" onClick={() => (hist ? setHist(null) : findHistory())}>
          {hist ? 'Hide Q&A history' : 'Q&A history'}
        </button>
      </div>
      {asking && b.people && (
        <form className="grid gap-2 rounded-xl border border-line bg-surface p-4 sm:grid-cols-2" onSubmit={(e) => {
          e.preventDefault();
          run(wtApi.askQuestion({ to_user: ask.to_user, task_id: ask.task_id ? Number(ask.task_id) : undefined, question: ask.question }))
            .then((ok) => { if (ok) { setAsk({ to_user: '', task_id: '', question: '' }); setAsking(false); } });
        }}>
          <select aria-label="Ask whom" required className="input-field" value={ask.to_user} onChange={(e) => setAsk({ ...ask, to_user: e.target.value, task_id: '' })}>
            <option value="" disabled>Ask whom…</option>
            {b.people.map((p) => <option key={p.user_id} value={p.user_id}>{p.name}</option>)}
          </select>
          <select aria-label="About which task" className="input-field" value={ask.task_id} onChange={(e) => setAsk({ ...ask, task_id: e.target.value })}>
            <option value="">About their work in general</option>
            {person?.tasks.map((t) => <option key={t.id} value={t.id}>{t.title}</option>)}
          </select>
          <textarea aria-label="Question" required minLength={3} maxLength={2000} rows={2} className="input-field sm:col-span-2" placeholder="Your question"
                    value={ask.question} onChange={(e) => setAsk({ ...ask, question: e.target.value })} />
          <div className="sm:col-span-2"><button className="btn-primary" type="submit">Ask</button></div>
        </form>
      )}
      {hist && (
        <div className="rounded-xl border border-line bg-surface p-4">
          <form className="mb-3 flex flex-wrap gap-2" onSubmit={(e) => { e.preventDefault(); findHistory(); }}>
            <input aria-label="Search the history" className="input-field flex-1" placeholder="Search words or a task (last 12 months)"
                   value={search.q} onChange={(e) => setSearch({ ...search, q: e.target.value })} />
            {b.isSuperuser && (
              <select aria-label="Person" className="input-field w-auto" value={search.who} onChange={(e) => setSearch({ ...search, who: e.target.value })}>
                <option value="">Everyone</option>
                {b.people?.map((p) => <option key={p.user_id} value={p.user_id}>{p.name}</option>)}
              </select>
            )}
            <button className="btn-secondary" type="submit">Search</button>
          </form>
          {hist.length === 0 ? <p className="text-sm text-muted">Nothing found.</p> : (
            <ul className="space-y-2">
              {hist.map((q) => (
                <Thread key={q.id} q={q} me={b.me} isSuper={b.isSuperuser}
                        onReopen={b.isSuperuser ? () => run(wtApi.questionReopen(q.id)).then(findHistory) : undefined} />
              ))}
            </ul>
          )}
        </div>
      )}
    </section>
  );
}
