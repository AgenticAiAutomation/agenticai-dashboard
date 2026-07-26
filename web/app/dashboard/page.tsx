'use client';

import { useEffect, useState } from 'react';
import { useRouter } from 'next/navigation';
import api from '@/lib/api';
import Nav from '@/components/Nav';

interface DashboardSummary {
  total_keywords: number;
  total_articles: number;
  published_articles: number;
  tasks_open: number;
  tasks_done: number;
  phase_progress: Record<string, number>;
}

export default function DashboardPage() {
  const [summary, setSummary] = useState<DashboardSummary | null>(null);
  const [loading, setLoading] = useState(true);
  const router = useRouter();

  useEffect(() => {
    const fetchSummary = async () => {
      try {
        const response = await api.get('/metrics/summary');
        setSummary(response.data);
      } catch (error) {
        console.error('Failed to fetch summary', error);
      } finally {
        setLoading(false);
      }
    };

    const token = localStorage.getItem('access_token');
    if (!token) {
      router.push('/login');
      return;
    }

    fetchSummary();
  }, [router]);

  if (loading) {
    return (
      <div className="min-h-screen">
        <Nav />
        <div className="max-w-7xl mx-auto px-4 py-8">
          <p>Loading...</p>
        </div>
      </div>
    );
  }

  return (
    <div className="min-h-screen bg-gray-50">
      <Nav />
      <div className="max-w-7xl mx-auto px-4 py-8">
        <h1 className="text-3xl font-bold mb-8">Dashboard</h1>

        {/* Summary Cards */}
        <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-4 gap-6 mb-8">
          <div className="card">
            <h3 className="text-sm font-medium text-gray-600 mb-2">Total Keywords</h3>
            <p className="text-3xl font-bold text-primary">{summary?.total_keywords || 0}</p>
          </div>
          <div className="card">
            <h3 className="text-sm font-medium text-gray-600 mb-2">Total Articles</h3>
            <p className="text-3xl font-bold text-primary">{summary?.total_articles || 0}</p>
          </div>
          <div className="card">
            <h3 className="text-sm font-medium text-gray-600 mb-2">Published</h3>
            <p className="text-3xl font-bold text-success">{summary?.published_articles || 0}</p>
          </div>
          <div className="card">
            <h3 className="text-sm font-medium text-gray-600 mb-2">Tasks Open</h3>
            <p className="text-3xl font-bold text-warning">{summary?.tasks_open || 0}</p>
          </div>
        </div>

        {/* Phase Progress */}
        <div className="card mb-8">
          <h2 className="text-xl font-bold mb-4">Phase Progress</h2>
          <div className="space-y-3">
            {Object.entries(summary?.phase_progress || {}).map(([phase, count]) => (
              <div key={phase}>
                <div className="flex justify-between text-sm mb-1">
                  <span>Phase {phase}</span>
                  <span>{count} tasks</span>
                </div>
                <div className="w-full bg-gray-200 rounded-full h-2">
                  <div
                    className="bg-primary h-2 rounded-full"
                    style={{ width: `${Math.min((count / 10) * 100, 100)}%` }}
                  ></div>
                </div>
              </div>
            ))}
          </div>
        </div>

        {/* This Week's Tasks */}
        <div className="card">
          <h2 className="text-xl font-bold mb-4">Today's Tasks</h2>
          <p className="text-gray-600">No tasks assigned yet. Check the Tasks page to get started.</p>
        </div>
      </div>
    </div>
  );
}
