'use client';

import { useEffect } from 'react';
import { useRouter } from 'next/navigation';

/* The static /articles page was removed on 2026-10-13 (archived under
   archive/removed_2026-10-13/). Old bookmarks land here and go home.
   The article pipeline lives at /dashboard/seo/articles. */
export default function ArticlesMoved() {
  const router = useRouter();
  useEffect(() => {
    router.replace('/');
  }, [router]);
  return null;
}
