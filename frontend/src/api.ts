let connection: Promise<{ url: string; token: string }> | undefined;
export async function request<T>(
  path: string,
  options: RequestInit = {},
): Promise<T> {
  if (!window.nodeglass)
    throw new Error(
      "Open Nodeglass through Electron to connect to the local analysis server.",
    );
  connection ??= window.nodeglass.connection();
  const config = await connection;
  const response = await fetch(config.url + path, {
    ...options,
    headers: {
      ...options.headers,
      Authorization: `Bearer ${config.token}`,
      "Content-Type": "application/json",
    },
  });
  const data = await response.json();
  if (!response.ok)
    throw new Error(
      typeof data.detail === "string"
        ? data.detail
        : `Request failed (${response.status})`,
    );
  return data;
}
