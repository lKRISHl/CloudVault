export function ScanStatus({ state }: { state?: string }) {
  if (state === 'clean') return <p>Scan complete: no known threats detected. Scanning does not guarantee safety.</p>;
  if (state === 'blocked') return <p aria-live="polite">Quarantined: a threat or scanner policy violation was detected. Replace this content or delete it.</p>;
  if (state === 'oversized') return <p aria-live="polite">Quarantined: this file exceeds the scanner limit. It cannot be downloaded, shared or previewed.</p>;
  if (state === 'error') return <p aria-live="polite">Quarantined: scanning failed. Retry the failed scan from version history.</p>;
  return <p aria-live="polite">Quarantined: {state === 'scanning' ? 'scanning in progress' : 'waiting for scanning'}. Downloads, sharing and previews remain blocked.</p>;
}
