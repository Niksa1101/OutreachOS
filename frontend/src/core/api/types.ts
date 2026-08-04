/**
 * Ergonomic aliases over the generated schema.
 *
 * `schema.d.ts` is machine-written and shaped for completeness, not for use:
 * reaching a response body means
 * `paths['/api/v1/settings']['get']['responses'][200]['content']['application/json']`.
 * Naming the ones we actually use here keeps that shape in one file instead of
 * spread across every call site.
 *
 * Q21 predicted friction between `exactOptionalPropertyTypes` and
 * `openapi-typescript` output — generated optional properties are not
 * `| undefined`-explicit. Nothing in P0 has hit it yet; when it does, the
 * workaround belongs here, at the boundary, rather than in application code.
 */

import type { components, paths } from '@/core/api/schema';

/** The whole generated component set, for anything not aliased below. */
export type Schemas = components['schemas'];

type JsonResponse<T> = T extends { content: { 'application/json': infer B } } ? B : never;

export type HealthResponse = JsonResponse<paths['/api/v1/health']['get']['responses'][200]>;

export type SettingsResponse = JsonResponse<paths['/api/v1/settings']['get']['responses'][200]>;

export type ClientLogBatch = NonNullable<
  paths['/api/v1/client-logs']['post']['requestBody']
>['content']['application/json'];

/**
 * The error envelope, as the server actually sends it.
 *
 * Q94: this type existing here — rather than FastAPI's `HTTPValidationError` —
 * is the whole point of the 422 override in `core/openapi.py`. Without it the
 * generated client would describe a shape the server never sends, for the most
 * common error in the application.
 */
export type ErrorEnvelope = Schemas['ErrorEnvelope'];
