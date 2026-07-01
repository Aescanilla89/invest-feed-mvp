interface ExplanationBulletsProps {
  explanation: string;
  className?: string;
}

export function ExplanationBullets({ explanation, className }: ExplanationBulletsProps) {
  const bullets = explanation
    .split("\n")
    .map((line) => line.replace(/^[•\-]\s*/, "").trim())
    .filter(Boolean);

  if (bullets.length === 0) return null;

  return (
    <ul className={className}>
      {bullets.map((bullet, i) => (
        <li key={i} className="flex gap-2 text-sm leading-snug text-foreground/90">
          <span className="mt-0.5 shrink-0 text-[--color-accent]">•</span>
          <span>{bullet}</span>
        </li>
      ))}
    </ul>
  );
}
