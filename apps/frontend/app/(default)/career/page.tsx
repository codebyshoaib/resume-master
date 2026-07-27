'use client';

import React from 'react';
import Link from 'next/link';
import ArrowLeft from 'lucide-react/dist/esm/icons/arrow-left';
import { CareerDocuments } from '@/components/career/career-documents';
import { useTranslations } from '@/lib/i18n';

export default function CareerPage() {
  const { t } = useTranslations();
  return (
    <main
      className="min-h-[100dvh] w-full bg-background px-4 py-6 md:px-8"
      style={{
        backgroundImage:
          'linear-gradient(rgba(29, 78, 216, 0.1) 1px, transparent 1px), linear-gradient(90deg, rgba(29, 78, 216, 0.1) 1px, transparent 1px)',
        backgroundSize: '40px 40px',
      }}
    >
      <div className="mx-auto w-full max-w-[80rem]">
        <Link
          href="/dashboard"
          className="mb-3 inline-flex items-center gap-1 font-mono text-xs uppercase text-ink-soft hover:text-primary"
        >
          <ArrowLeft className="h-3.5 w-3.5" />
          {t('nav.backToDashboard')}
        </Link>

        <div className="border border-black bg-background shadow-sw-lg">
          <div className="border-b border-black p-8 md:p-10">
            <h1 className="font-serif text-4xl uppercase leading-[0.95] tracking-tight text-black md:text-6xl">
              {t('career.title')}
            </h1>
            <p className="mt-4 max-w-md font-mono text-sm font-bold uppercase tracking-wide text-blue-700">
              {'// '}
              {t('career.subtitle')}
            </p>
          </div>

          <div className="p-4 md:p-6">
            <CareerDocuments />
          </div>
        </div>
      </div>
    </main>
  );
}
