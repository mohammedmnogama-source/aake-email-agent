import type { Metadata } from 'next';
import './globals.css';
import NavWrapper from '@/components/layout/nav';

export const metadata: Metadata = {
  title: 'AAKE Email Agent',
};

export default function RootLayout({ children }: { children: React.ReactNode }) {
  return (
    <html lang="en">
      <body className="bg-slate-50 text-slate-900 min-h-screen">
        <NavWrapper />
        <main>{children}</main>
      </body>
    </html>
  );
}
