interface Props {
  message: string | null;
  className?: string;
}

export function InlineError({ message, className }: Props) {
  if (message == null) {
    return null;
  }

  return (
    <p role="alert" className={className ?? 'text-sm text-destructive'}>
      {message}
    </p>
  );
}
