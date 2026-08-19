'use client';

import { useEffect, useState } from 'react';
import { useRouter } from 'next/navigation';
import api from '@/lib/api';
import Nav from '@/components/Nav';

interface Article {
  id: number;
  title: string;
  country: string | null;
  vertical: string | null;
  status: string;
}

export default function CountriesPage() {
  const [countryArticles, setCountryArticles] = useState<Article[]>([]);
  const [loading, setLoading] = useState(true);
  const router = useRouter();

  useEffect(() => {
    const token = localStorage.getItem('access_token');
    if (!token) {
      router.push('/login');
      return;
    }

    fetchCountryArticles();
  }, [router]);

  const fetchCountryArticles = async () => {
    try {
      const response = await api.get('/articles');
      const countries = response.data.filter((a: Article) => a.country);
      setCountryArticles(countries);
    } catch (error) {
      console.error('Failed to fetch articles', error);
    } finally {
      setLoading(false);
    }
  };

  return (
    <div className="min-h-screen bg-bg">
      <Nav />
      <div className="max-w-7xl mx-auto px-4 py-8">
        <h1 className="text-3xl font-bold mb-8">Country Landing Pages</h1>

        {loading ? (
          <p>Loading...</p>
        ) : (
          <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 gap-6">
            {countryArticles.map((article) => (
              <div key={article.id} className="card">
                <h3 className="font-semibold text-lg mb-2">{article.country}</h3>
                <p className="text-sm text-gray-600 mb-2">{article.title}</p>
                <div className="flex items-center gap-2">
                  <span className="text-xs bg-blue-100 text-blue-800 px-2 py-1 rounded">
                    {article.vertical}
                  </span>
                  <span className={`text-xs px-2 py-1 rounded ${
                    article.status === 'published' ? 'bg-green-100 text-green-800' : 'bg-yellow-100 text-yellow-800'
                  }`}>
                    {article.status}
                  </span>
                </div>
              </div>
            ))}
          </div>
        )}
      </div>
    </div>
  );
}
