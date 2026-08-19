'use client';

import { useEffect, useState } from 'react';
import { useRouter } from 'next/navigation';
import api from '@/lib/api';
import Nav from '@/components/Nav';

interface Keyword {
  id: number;
  keyword: string;
  pillar: string;
  score: number;
  ubersuggest_volume: number | null;
  ubersuggest_kd: number | null;
  status: string;
  assignee_id: number | null;
}

export default function KeywordsPage() {
  const [keywords, setKeywords] = useState<Keyword[]>([]);
  const [loading, setLoading] = useState(true);
  const [filter, setFilter] = useState({ pillar: '', status: '' });
  const router = useRouter();

  useEffect(() => {
    const token = localStorage.getItem('access_token');
    if (!token) {
      router.push('/login');
      return;
    }

    fetchKeywords();
  }, [router, filter]);

  const fetchKeywords = async () => {
    try {
      const params = new URLSearchParams();
      if (filter.pillar) params.append('pillar', filter.pillar);
      if (filter.status) params.append('status', filter.status);

      const response = await api.get(`/keywords?${params}`);
      setKeywords(response.data);
    } catch (error) {
      console.error('Failed to fetch keywords', error);
    } finally {
      setLoading(false);
    }
  };

  const handleStatusChange = async (id: number, newStatus: string) => {
    try {
      await api.patch(`/keywords/${id}`, { status: newStatus });
      fetchKeywords();
    } catch (error) {
      console.error('Failed to update keyword', error);
    }
  };

  return (
    <div className="min-h-screen bg-bg">
      <Nav />
      <div className="max-w-7xl mx-auto px-4 py-8">
        <h1 className="text-3xl font-bold mb-8">Keywords</h1>

        {/* Filters */}
        <div className="card mb-6 flex gap-4">
          <select
            value={filter.pillar}
            onChange={(e) => setFilter({ ...filter, pillar: e.target.value })}
            className="input-field w-48"
          >
            <option value="">All Pillars</option>
            <option value="BFSI">BFSI</option>
            <option value="Logistics">Logistics</option>
            <option value="D2C">D2C</option>
            <option value="Coaching">Coaching</option>
          </select>

          <select
            value={filter.status}
            onChange={(e) => setFilter({ ...filter, status: e.target.value })}
            className="input-field w-48"
          >
            <option value="">All Statuses</option>
            <option value="draft">Draft</option>
            <option value="validated">Validated</option>
            <option value="assigned">Assigned</option>
            <option value="published">Published</option>
            <option value="killed">Killed</option>
          </select>
        </div>

        {/* Keywords Table */}
        <div className="card overflow-x-auto">
          {loading ? (
            <p>Loading keywords...</p>
          ) : (
            <table className="table-auto">
              <thead>
                <tr>
                  <th>Keyword</th>
                  <th>Pillar</th>
                  <th>Score</th>
                  <th>Volume</th>
                  <th>KD</th>
                  <th>Status</th>
                </tr>
              </thead>
              <tbody>
                {keywords.map((kw) => (
                  <tr key={kw.id}>
                    <td>{kw.keyword}</td>
                    <td><span className="px-2 py-1 bg-blue-100 text-blue-800 text-xs rounded">{kw.pillar}</span></td>
                    <td>{kw.score}</td>
                    <td>{kw.ubersuggest_volume || '-'}</td>
                    <td>{kw.ubersuggest_kd || '-'}</td>
                    <td>
                      <select
                        value={kw.status}
                        onChange={(e) => handleStatusChange(kw.id, e.target.value)}
                        className="text-sm border rounded px-2 py-1"
                      >
                        <option value="draft">Draft</option>
                        <option value="validated">Validated</option>
                        <option value="assigned">Assigned</option>
                        <option value="published">Published</option>
                        <option value="killed">Killed</option>
                      </select>
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          )}
        </div>
      </div>
    </div>
  );
}
