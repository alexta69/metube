// The message of a { status: 'error', msg } result from the server, or null
// when the action succeeded. Service calls catch HTTP errors into that shape.
export function actionError(res: unknown): string | null {
  const status = res as { status?: string; msg?: string } | null;
  return status?.status === 'error' ? status.msg || null : null;
}
