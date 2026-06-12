'use client';
import { useState, useEffect, useRef } from 'react';
import { api } from '@/lib/api';

interface Contact {
  email: string;
  name: string | null;
  frequency: number;
}

interface Props {
  value: string;
  onChange: (value: string) => void;
  placeholder?: string;
  className?: string;
}

export default function EmailAutocomplete({ value, onChange, placeholder, className }: Props) {
  const [suggestions, setSuggestions] = useState<Contact[]>([]);
  const [open, setOpen] = useState(false);
  const [activeIdx, setActiveIdx] = useState(0);
  const debounceRef = useRef<ReturnType<typeof setTimeout> | null>(null);
  const containerRef = useRef<HTMLDivElement>(null);

  useEffect(() => {
    const handleClickOutside = (e: MouseEvent) => {
      if (containerRef.current && !containerRef.current.contains(e.target as Node)) {
        setOpen(false);
      }
    };
    document.addEventListener('mousedown', handleClickOutside);
    return () => document.removeEventListener('mousedown', handleClickOutside);
  }, []);

  const handleChange = (raw: string) => {
    onChange(raw);
    setActiveIdx(0);

    if (debounceRef.current) clearTimeout(debounceRef.current);

    const query = raw.split(',').pop()?.trim() ?? '';
    if (query.length < 1) {
      setSuggestions([]);
      setOpen(false);
      return;
    }

    debounceRef.current = setTimeout(async () => {
      try {
        const results = await api.searchContacts(query);
        setSuggestions(results);
        setOpen(results.length > 0);
      } catch {
        setSuggestions([]);
        setOpen(false);
      }
    }, 200);
  };

  const select = (contact: Contact) => {
    // Support multiple addresses separated by comma
    const parts = value.split(',');
    parts[parts.length - 1] = ' ' + contact.email;
    onChange(parts.join(',').trimStart());
    setSuggestions([]);
    setOpen(false);
  };

  const handleKeyDown = (e: React.KeyboardEvent<HTMLInputElement>) => {
    if (!open) return;
    if (e.key === 'ArrowDown') {
      e.preventDefault();
      setActiveIdx(i => Math.min(i + 1, suggestions.length - 1));
    } else if (e.key === 'ArrowUp') {
      e.preventDefault();
      setActiveIdx(i => Math.max(i - 1, 0));
    } else if (e.key === 'Enter' || e.key === 'Tab') {
      if (suggestions[activeIdx]) {
        e.preventDefault();
        select(suggestions[activeIdx]);
      }
    } else if (e.key === 'Escape') {
      setOpen(false);
    }
  };

  return (
    <div ref={containerRef} className="relative">
      <input
        type="text"
        value={value}
        onChange={e => handleChange(e.target.value)}
        onKeyDown={handleKeyDown}
        onFocus={() => value.length >= 1 && suggestions.length > 0 && setOpen(true)}
        placeholder={placeholder}
        className={className}
        autoComplete="off"
      />

      {open && suggestions.length > 0 && (
        <ul className="absolute z-50 mt-1 w-full bg-white border border-slate-200 rounded-lg shadow-lg overflow-hidden">
          {suggestions.map((c, i) => (
            <li
              key={c.email}
              onMouseDown={() => select(c)}
              className={`flex items-center gap-3 px-3 py-2 cursor-pointer text-sm transition-colors
                ${i === activeIdx ? 'bg-slate-100' : 'hover:bg-slate-50'}`}
            >
              <div className="w-7 h-7 rounded-full bg-slate-200 flex items-center justify-center text-xs font-semibold text-slate-600 shrink-0">
                {(c.name ?? c.email)[0].toUpperCase()}
              </div>
              <div className="min-w-0">
                {c.name && (
                  <div className="font-medium text-slate-800 truncate">{c.name}</div>
                )}
                <div className="text-slate-500 truncate">{c.email}</div>
              </div>
              <div className="ml-auto text-xs text-slate-400 shrink-0">{c.frequency}×</div>
            </li>
          ))}
        </ul>
      )}
    </div>
  );
}
