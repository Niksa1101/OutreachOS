/**
 * The stream's observable status, split out from the provider component.
 *
 * A `.tsx` that exports both a component and a hook breaks React Fast Refresh —
 * the module can no longer be swapped without remounting, so every edit to the
 * provider would blow away the state it holds. Keeping the context and its hook
 * in a `.ts` file is the standard fix, not a lint workaround.
 */

import { createContext, useContext } from 'react';

export interface StreamStatus {
  connected: boolean;
  /** When the last heartbeat arrived. `null` until the first one. */
  lastHeartbeatAt: Date | null;
  /** The most recent disconnect or resync notice, for the status line. */
  lastMessage: string | null;
}

export const StreamStatusContext = createContext<StreamStatus>({
  connected: false,
  lastHeartbeatAt: null,
  lastMessage: null,
});

export function useStreamStatus(): StreamStatus {
  return useContext(StreamStatusContext);
}
