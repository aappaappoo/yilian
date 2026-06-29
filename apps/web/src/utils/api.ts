const backendOrigin = import.meta.env.VITE_BACKEND_ORIGIN?.replace(/\/$/, '') ?? ''

export function apiUrl(path: string): string {
  if (!backendOrigin) {
    return path
  }
  return `${backendOrigin}${path.startsWith('/') ? path : `/${path}`}`
}
