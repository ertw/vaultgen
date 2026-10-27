// Shared HTTP and download behavior for the configurator and label editor.
export const isActive = job => job && ['queued', 'running'].includes(job.status);
export const errorMessage = error => error instanceof Error ? error.message : String(error);

export async function api(path, options = {}) {
  const response = await fetch(path, { cache: 'no-store', ...options });
  if (response.status === 401) throw new Error('Session expired. Refresh to sign in; an existing build may still be running.');
  if (!response.ok) {
    let message = `Request failed (${response.status}).`;
    try { const body = await response.json(); message = body.error || message; } catch { /* Keep the HTTP error. */ }
    throw new Error(message);
  }
  return response.json();
}

export function downloadLink(node, url) {
  const valid = typeof url === 'string' && /^\/(?:files\/|api\/(?:jobs|builds)\/)[^\s]*$/.test(url) && !url.includes('\\');
  node.hidden = !valid;
  if (valid) { node.href = url; node.setAttribute('download', ''); }
  else node.removeAttribute('href');
}
