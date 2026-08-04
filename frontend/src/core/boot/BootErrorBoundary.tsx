/**
 * The outermost error boundary.
 *
 * Two jobs, and the second is the non-obvious one:
 *
 * 1. Capture render-phase errors that `window.onerror` never sees and route
 *    them to the boot log (Q23, Q64).
 * 2. Call `app_ready` on mount. Q77: a caught crash should reveal the window
 *    immediately rather than after 3s of apparent hang. The user sees a
 *    failure, which is bad, instead of nothing at all, which is worse.
 */

import { Component, type ErrorInfo, type ReactNode } from 'react';

import { signalAppReady } from '@/core/boot/appReady';
import { reportClientError } from '@/core/boot/clientErrors';

interface Props {
  children: ReactNode;
}

interface State {
  error: Error | null;
}

export class BootErrorBoundary extends Component<Props, State> {
  override state: State = { error: null };

  static getDerivedStateFromError(error: Error): State {
    return { error };
  }

  override componentDidCatch(error: Error, info: ErrorInfo): void {
    void reportClientError({
      message: `${error.name}: ${error.message}`,
      source: 'error-boundary',
      stack: `${error.stack ?? '(no stack)'}\n--- component stack ---${info.componentStack ?? ''}`,
      route: window.location.hash || window.location.pathname,
    });
  }

  override componentDidMount(): void {
    // Deliberately unconditional. If the boundary mounted, React is running
    // and there is something on screen worth showing the window for.
    signalAppReady();
  }

  override render(): ReactNode {
    const { error } = this.state;

    if (error) {
      // No design tokens are referenced here on purpose: this component has to
      // render correctly when the failure *is* the stylesheet. It is the one
      // place in the application where inline styles are not a review failure.
      return (
        <main
          style={{
            fontFamily: 'ui-monospace, monospace',
            padding: '2rem',
            color: '#fafafa',
            background: '#09090b',
            minHeight: '100vh',
          }}
        >
          <h1 style={{ fontSize: '1rem', margin: '0 0 1rem' }}>OutreachOS could not start</h1>
          <p style={{ margin: '0 0 1rem', opacity: 0.7 }}>
            The details below were written to the boot log.
          </p>
          <pre style={{ whiteSpace: 'pre-wrap', margin: 0, fontSize: '0.8125rem' }}>
            {error.name}: {error.message}
          </pre>
        </main>
      );
    }

    return this.props.children;
  }
}
