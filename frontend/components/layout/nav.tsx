'use client';
import Link from 'next/link';
import { usePathname, useRouter } from 'next/navigation';
import { clearToken } from '@/lib/auth';

const links = [
  { href: '/inbox',            label: 'Inbox' },
  { href: '/briefing',         label: '📋 Briefing' },
  { href: '/suggested-tasks',  label: '🗂 Proposals' },
  { href: '/facts',            label: '🧠 Brain' },
  { href: '/usage',            label: '📊 AI Usage' },
  { href: '/settings',         label: 'Settings' },
];

export default function Nav() {
  const path = usePathname();
  const router = useRouter();

  if (path === '/login') return null;

  function logout() {
    clearToken();
    router.push('/login');
  }

  return (
    <nav className="bg-slate-800 text-white px-6 py-3 flex items-center gap-6">
      <span className="font-bold text-lg tracking-tight mr-4">AAKE Agent</span>
      {links.map((l) => (
        <Link
          key={l.href}
          href={l.href}
          className={`text-sm hover:text-slate-200 transition-colors ${
            path.startsWith(l.href) ? 'text-white font-semibold' : 'text-slate-300'
          }`}
        >
          {l.label}
        </Link>
      ))}
      <button
        onClick={logout}
        className="ml-auto text-sm text-slate-400 hover:text-white transition-colors"
      >
        Logout
      </button>
    </nav>
  );
}
