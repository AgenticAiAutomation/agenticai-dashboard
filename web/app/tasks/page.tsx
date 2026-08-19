'use client';

import { useEffect, useState } from 'react';
import { useRouter } from 'next/navigation';
import api from '@/lib/api';
import Nav from '@/components/Nav';

interface Task {
  id: number;
  phase: string;
  task_code: string;
  title: string;
  status: string;
  owner_role: string | null;
}

export default function TasksPage() {
  const [tasks, setTasks] = useState<Task[]>([]);
  const [loading, setLoading] = useState(true);
  const [filter, setFilter] = useState({ phase: '', mine: false });
  const router = useRouter();

  useEffect(() => {
    const token = localStorage.getItem('access_token');
    if (!token) {
      router.push('/login');
      return;
    }

    fetchTasks();
  }, [router, filter]);

  const fetchTasks = async () => {
    try {
      const params = new URLSearchParams();
      if (filter.phase) params.append('phase', filter.phase);
      if (filter.mine) params.append('mine', 'true');

      const response = await api.get(`/tasks?${params}`);
      setTasks(response.data);
    } catch (error) {
      console.error('Failed to fetch tasks', error);
    } finally {
      setLoading(false);
    }
  };

  const handleStatusToggle = async (id: number, currentStatus: string) => {
    const newStatus = currentStatus === 'done' ? 'open' : 'done';
    try {
      await api.patch(`/tasks/${id}`, { status: newStatus });
      fetchTasks();
    } catch (error) {
      console.error('Failed to update task', error);
    }
  };

  return (
    <div className="min-h-screen bg-bg">
      <Nav />
      <div className="max-w-7xl mx-auto px-4 py-8">
        <h1 className="text-3xl font-bold mb-8">Tasks</h1>

        {/* Filters */}
        <div className="card mb-6 flex gap-4 items-center">
          <select
            value={filter.phase}
            onChange={(e) => setFilter({ ...filter, phase: e.target.value })}
            className="input-field w-48"
          >
            <option value="">All Phases</option>
            <option value="0">Phase 0</option>
            <option value="1">Phase 1</option>
            <option value="2">Phase 2</option>
            <option value="3">Phase 3</option>
            <option value="4">Phase 4</option>
            <option value="5">Phase 5</option>
            <option value="6">Phase 6</option>
          </select>

          <label className="flex items-center">
            <input
              type="checkbox"
              checked={filter.mine}
              onChange={(e) => setFilter({ ...filter, mine: e.target.checked })}
              className="mr-2"
            />
            <span className="text-sm">My Tasks Only</span>
          </label>
        </div>

        {/* Tasks List */}
        <div className="card">
          {loading ? (
            <p>Loading tasks...</p>
          ) : (
            <div className="space-y-2">
              {tasks.map((task) => (
                <div key={task.id} className="flex items-center gap-4 p-3 hover:bg-raised rounded">
                  <input
                    type="checkbox"
                    checked={task.status === 'done'}
                    onChange={() => handleStatusToggle(task.id, task.status)}
                    className="w-5 h-5"
                  />
                  <div className="flex-1">
                    <span className="text-xs text-gray-500 mr-2">Phase {task.phase}</span>
                    <span className="text-xs text-gray-500 mr-2">{task.task_code}</span>
                    <span className={task.status === 'done' ? 'line-through text-gray-400' : ''}>
                      {task.title}
                    </span>
                  </div>
                  {task.owner_role && (
                    <span className="text-xs bg-raised text-slate-200 border border-line px-2 py-1 rounded">{task.owner_role}</span>
                  )}
                </div>
              ))}
            </div>
          )}
        </div>
      </div>
    </div>
  );
}
