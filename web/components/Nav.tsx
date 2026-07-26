'use client';

import Link from 'next/link';
import { useRouter, usePathname } from 'next/navigation';

export default function Nav() {
  const router = useRouter();
  const pathname = usePathname();

  const handleLogout = () => {
    localStorage.removeItem('access_token');
    localStorage.removeItem('refresh_token');
    router.push('/login');
  };

  const navItems = [
    { href: '/dashboard', label: 'Dashboard' },
    { href: '/keywords', label: 'Keywords' },
    { href: '/articles', label: 'Articles' },
    { href: '/countries', label: 'Countries' },
    { href: '/tasks', label: 'Tasks' },
    { href: '/settings/users', label: 'Users' },
  ];

  return (
    <nav className="bg-white shadow-sm border-b">
      <div className="max-w-7xl mx-auto px-4">
        <div className="flex justify-between items-center h-16">
          <div className="flex items-center space-x-8">
            <h1 className="text-lg font-bold text-primary">AgenticAI SEO</h1>
            <div className="hidden md:flex space-x-4">
              {navItems.map((item) => (
                <Link
                  key={item.href}
                  href={item.href}
                  className={`px-3 py-2 rounded-md text-sm font-medium ${
                    pathname === item.href
                      ? 'bg-primary text-white'
                      : 'text-gray-700 hover:bg-gray-100'
                  }`}
                >
                  {item.label}
                </Link>
              ))}
            </div>
          </div>
          <button onClick={handleLogout} className="text-sm text-gray-600 hover:text-gray-900">
            Logout
          </button>
        </div>
      </div>
    </nav>
  );
}
