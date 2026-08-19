'use client';

import { useEffect, useState } from 'react';
import { useRouter } from 'next/navigation';
import api from '@/lib/api';
import Nav from '@/components/Nav';

interface Article {
  id: number;
  title: string;
  slug: string;
  status: string;
  assignee_id: number | null;
  publish_date: string | null;
}

const STATUSES = ['briefed', 'drafting', 'editing', 'schema', 'ready', 'published'];

export default function ArticlesPage() {
  const [articles, setArticles] = useState<Article[]>([]);
  const [loading, setLoading] = useState(true);
  const router = useRouter();

  useEffect(() => {
    const token = localStorage.getItem('access_token');
    if (!token) {
      router.push('/login');
      return;
    }

    fetchArticles();
  }, [router]);

  const fetchArticles = async () => {
    try {
      const response = await api.get('/articles');
      setArticles(response.data);
    } catch (error) {
      console.error('Failed to fetch articles', error);
    } finally {
      setLoading(false);
    }
  };

  const handleStatusChange = async (id: number, newStatus: string) => {
    try {
      await api.patch(`/articles/${id}`, { status: newStatus });
      fetchArticles();
    } catch (error) {
      console.error('Failed to update article', error);
    }
  };

  const getArticlesByStatus = (status: string) => {
    return articles.filter((a) => a.status === status);
  };

  // Colours come from the dark ramp in tailwind.config.ts (bg / surface /
  // raised / line / muted). This page previously used bg-gray-50 and white
  // cards left over from the light theme, which put the near-white body text
  // set in globals.css onto a near-white background — invisible.
  return (
    <div className="min-h-screen bg-bg">
      <Nav />
      <div className="max-w-7xl mx-auto px-4 py-8">
        <h1 className="text-3xl font-bold mb-8 text-slate-100">Articles Kanban</h1>

        {loading ? (
          <p className="text-muted">Loading articles…</p>
        ) : (
          <div className="grid grid-cols-1 md:grid-cols-3 lg:grid-cols-6 gap-4">
            {STATUSES.map((status) => (
              <div key={status} className="bg-surface border border-line rounded-xl p-4">
                <h2 className="font-semibold text-xs uppercase tracking-wide mb-3 text-muted">
                  {status}
                </h2>
                <div className="space-y-2">
                  {getArticlesByStatus(status).map((article) => (
                    <div
                      key={article.id}
                      className="bg-raised border border-line p-3 rounded-lg text-sm"
                    >
                      <p className="font-medium mb-1 text-slate-100">{article.title}</p>
                      <p className="text-xs text-muted break-words">{article.slug}</p>
                      {article.publish_date && (
                        <p className="text-xs text-muted mt-1">{article.publish_date}</p>
                      )}
                      <label className="sr-only" htmlFor={`status-${article.id}`}>
                        Status for {article.title}
                      </label>
                      <select
                        id={`status-${article.id}`}
                        value={article.status}
                        onChange={(e) => handleStatusChange(article.id, e.target.value)}
                        className="mt-2 w-full text-xs bg-surface border border-line rounded
                                   px-2 py-1 text-slate-100
                                   focus:outline-none focus:ring-2 focus:ring-primary"
                      >
                        {STATUSES.map((s) => (
                          <option key={s} value={s}>{s}</option>
                        ))}
                      </select>
                    </div>
                  ))}
                  {getArticlesByStatus(status).length === 0 && (
                    <p className="text-xs text-muted">No articles</p>
                  )}
                </div>
              </div>
            ))}
          </div>
        )}
      </div>
    </div>
  );
}
