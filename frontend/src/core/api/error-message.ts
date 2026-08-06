import { ApiError, ApiTransportError } from '@/core/api/client';

/** Plain-language message for any API or transport failure. */
export function errorMessage(error: unknown): string {
  if (error instanceof ApiError || error instanceof ApiTransportError) {
    return error.message;
  }
  return 'Something went wrong. Try again in a moment.';
}
