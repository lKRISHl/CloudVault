export function Icon({ name, className = '' }: { name: 'vault' | 'folder' | 'file' | 'grid' | 'settings' | 'shield' | 'upload' | 'search' | 'trash'; className?: string }) {
  const paths = {
    trash: 'M4 7h16 M9 7V3h6v4 M6 7l1 14h10l1-14 M10 11v6 M14 11v6',
    vault: 'M5 4h14v16H5z M9 9h6v6H9z M12 9v6 M9 12h6',
    folder: 'M3 7V5h6l2 2h10v12H3z',
    file: 'M6 3h8l4 4v14H6z M14 3v5h4 M9 12h6 M9 16h6',
    grid: 'M3 3h7v7H3z M14 3h7v7h-7z M3 14h7v7H3z M14 14h7v7h-7z',
    settings: 'M4 7h16 M4 17h16 M8 4v6 M16 14v6',
    shield: 'M12 3l8 3v6c0 5-8 9-8 9s-8-4-8-9V6z M8 12l3 3 5-6',
    upload: 'M12 16V3 M7 8l5-5 5 5 M4 15v6h16v-6',
    search: 'M20 20l-5-5 M17 10a7 7 0 1 1-14 0 7 7 0 0 1 14 0',
  };
  return <svg className={className} width="22" height="22" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.7" strokeLinecap="round" strokeLinejoin="round" aria-hidden="true"><path d={paths[name]} /></svg>;
}
