'use client';

import { FormEvent, useCallback, useEffect, useState } from 'react';
import { Card, EmptyState, ErrorBanner } from '@/components/ui';
import { IDEA_LABEL, Idea, TrackerStatus, msg, trackerApi } from '@/lib/tracker';

const TONE: Record<Idea['status'], string> = {
  new: 'text-slate-300 border-line bg-raised',
  shortlisted: 'text-primary border-primary/40 bg-primary/10',
  in_trial: 'text-warning border-warning/40 bg-warning/10',
  worked: 'text-success border-success/40 bg-success/10',
  didnt_work: 'text-muted border-line bg-raised',
};

const BLANK = { project_id: '', title: '', problem: '', idea: '', test_plan: '', expected_result: '', metric: '', effort: '' };

export default function IdeasPanel({ status }: { status: TrackerStatus }) {
  const [ideas, setIdeas] = useState<Idea[]>([]);
  const [winners, setWinners] = useState<{ month: string; user_name: string; idea_id: number }[]>([]);
  const [form, setForm] = useState({ ...BLANK, project_id: status.allowed[0] ?? '' });
  const [open, setOpen] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [results, setResults] = useState<Record<number, string>>({});

  const load = useCallback(async () => {
    try {
      const r = await trackerApi.ideas();
      setIdeas(r.data.ideas);
      setWinners(r.data.winners);
    } catch (e) {
      setError(msg(e, 'Could not load ideas.'));
    }
  }, []);
  useEffect(() => { load(); }, [load]);

  const submit = async (e: FormEvent) => {
    e.preventDefault();
    setError(null);
    try {
      await trackerApi.createIdea(form);
      setForm({ ...BLANK, project_id: form.project_id });
      setOpen(false);
      load();
    } catch (err) {
      setError(msg(err));
    }
  };

  const replace = (i: Idea) => setIdeas((all) => all.map((x) => (x.id === i.id ? i : x)));
  const vote = async (id: number) => {
    try { replace((await trackerApi.vote(id)).data.idea); } catch (e) { setError(msg(e)); }
  };
  const decide = async (id: number, st: Idea['status']) => {
    try {
      replace((await trackerApi.ideaStatus(id, { status: st, result_note: results[id] })).data.idea);
      load();
    } catch (e) { setError(msg(e)); }
  };

  const field = (k: keyof typeof BLANK, label: string, area = false) => (
    <div className={area ? 'sm:col-span-2' : ''}>
      <label className="label" htmlFor={`idea-${k}`}>{label}</label>
      {area ? (
        <textarea id={`idea-${k}`} rows={3} className="input-field" value={form[k]}
                  onChange={(e) => setForm({ ...form, [k]: e.target.value })} />
      ) : (
        <input id={`idea-${k}`} className="input-field" value={form[k]}
               onChange={(e) => setForm({ ...form, [k]: e.target.value })} />
      )}
    </div>
  );

  return (
    <div className="space-y-6">
      <ErrorBanner message={error} />
      <Card
        title={status.taskManager ? 'Idea Board · one idea a week' : 'Idea Board · monthly bonus'}
        action={status.allowed.length > 0 && (
          <button className="btn-primary" onClick={() => setOpen(!open)}>{open ? 'Close' : 'Submit an idea'}</button>
        )}
      >
        <p className="text-sm text-muted">
          Suggest something new for your website. Jai picks ideas to trial; any idea marked <b className="text-success">Worked</b> that
          month earns its author the winner badge and the monthly bonus (handled offline).
        </p>
        {winners.length > 0 && (
          <p className="mt-3 text-sm text-slate-200">
            🏆 Recent winners: {winners.slice(0, 6).map((w) => `${w.user_name} (${w.month})`).join(' · ')}
          </p>
        )}
        {open && (
          <form onSubmit={submit} className="mt-5 grid grid-cols-1 gap-4 sm:grid-cols-2">
            <div>
              <label className="label" htmlFor="idea-project">Website</label>
              <select id="idea-project" className="input-field" value={form.project_id}
                      onChange={(e) => setForm({ ...form, project_id: e.target.value })}>
                {status.allowed.map((p) => <option key={p} value={p}>{status.sites[p]?.domain || p}</option>)}
              </select>
            </div>
            {field('title', 'Title')}
            {field('problem', 'Problem you noticed', true)}
            {field('idea', 'Your idea', true)}
            {field('test_plan', 'How to test it in 2 weeks or less', true)}
            {field('expected_result', 'Expected result')}
            {field('metric', 'Success metric')}
            {field('effort', 'Effort (e.g. 2 days)')}
            <div className="sm:col-span-2"><button className="btn-primary" type="submit">Submit idea</button></div>
          </form>
        )}
      </Card>

      {ideas.length === 0 ? (
        <EmptyState title="No ideas yet" description="Be the first — small, testable ideas are best." />
      ) : (
        <div className="grid grid-cols-1 gap-4 lg:grid-cols-2">
          {ideas.map((i) => (
            <article key={i.id} className="card">
              <header className="mb-2 flex flex-wrap items-start justify-between gap-2">
                <div>
                  <h3 className="font-semibold text-white">{i.title}</h3>
                  <p className="text-xs text-muted">{i.user_name} · {i.site} · {i.created_at.slice(0, 10)}</p>
                </div>
                <span className={`badge ${TONE[i.status]}`}>{IDEA_LABEL[i.status]}</span>
              </header>
              {i.problem && <p className="text-sm text-slate-300"><b className="text-slate-100">Problem:</b> {i.problem}</p>}
              <p className="mt-1 text-sm text-slate-300"><b className="text-slate-100">Idea:</b> {i.idea}</p>
              {i.expected_result && <p className="mt-1 text-sm text-slate-300"><b className="text-slate-100">Expected:</b> {i.expected_result}</p>}
              {i.test_plan && <p className="mt-1 text-sm text-slate-300"><b className="text-slate-100">Test:</b> {i.test_plan}</p>}
              {i.metric && <p className="mt-1 text-sm text-slate-300"><b className="text-slate-100">Measure:</b> {i.metric}</p>}
              {i.effort && <p className="mt-1 text-sm text-slate-300"><b className="text-slate-100">Effort:</b> {i.effort}</p>}
              {i.result_note && <p className="mt-2 text-sm text-success"><b>Result:</b> {i.result_note}</p>}
              <footer className="mt-3 flex flex-wrap items-center gap-2">
                <button
                  disabled={i.isMine}
                  onClick={() => vote(i.id)}
                  className={`rounded-md border px-2.5 py-1 text-sm ${i.votedByMe ? 'border-primary bg-primary/15 text-white' : 'border-line text-slate-300'} disabled:opacity-40`}
                  title={i.isMine ? 'You cannot vote for your own idea' : 'Like this idea'}
                >👍 {i.votes}</button>
                {status.isAdmin && (
                  <>
                    <input className="input-field max-w-[220px] py-1" placeholder="Result, e.g. +X traffic"
                           value={results[i.id] ?? ''} onChange={(e) => setResults({ ...results, [i.id]: e.target.value })} />
                    <select className="input-field w-auto py-1" value={i.status}
                            onChange={(e) => decide(i.id, e.target.value as Idea['status'])}>
                      {(Object.keys(IDEA_LABEL) as Idea['status'][]).map((s) => <option key={s} value={s}>{IDEA_LABEL[s]}</option>)}
                    </select>
                  </>
                )}
              </footer>
            </article>
          ))}
        </div>
      )}
    </div>
  );
}
