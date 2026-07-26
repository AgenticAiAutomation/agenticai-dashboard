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

  return (
    <div className="min-h-screen bg-gray-50">
      <Nav />
      <div className="max-w-7xl mx-auto px-4 py-8">
        <h1 className="text-3xl font-bold mb-8">Articles Kanban</h1>

        {loading ? (
          <p>Loading articles...</p>
        ) : (
          <div className="grid grid-cols-1 md:grid-cols-3 lg:grid-cols-6 gap-4">
            {STATUSES.map((status) => (
              <div key={status} className="bg-gray-100 rounded-lg p-4">
                <h3 className="font-semibold text-sm uppercase mb-3 text-gray-700">{status}</h3>
                <div className="space-y-2">
                  {getArticlesByStatus(status).map((article) => (
                    <div key={article.id} className="bg-white p-3 rounded shadow-sm text-sm">
                      <p className="font-medium mb-1">{article.title}</p>
                      <p className="text-xs text-gray-500">{article.slug}</p>
                      {article.publish_date && (
                        <p className="text-xs text-gray-400 mt-1">{article.publish_date}</p>
                      )}
                      <select
                        value={article.status}
                        onChange={(e) => handleStatusChange(article.id, e.target.value)}
                        className="mt-2 w-full text-xs border rounded px-1 py-1"
                      >
                        {STATUSES.map((s) => (
                          <option key={s} value={s}>{s}</option>
                        ))}
                      </select>
                    </div>
                  ))}
                  {getArticlesByStatus(status).length === 0 && (
                    <p className="text-xs text-gray-400">No articles</p>
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
