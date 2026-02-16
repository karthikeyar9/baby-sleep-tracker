import * as d3 from "d3";

export const BACKEND_API = `http://${process.env.REACT_APP_BACKEND_IP}`;
export const RESOURCE_SERVER = `http://${process.env.REACT_APP_RESOURCE_SERVER_IP}`;

export async function fetchApi<T>(path: string, options?: RequestInit): Promise<T> {
  const res = await fetch(`${BACKEND_API}${path}`, options);
  if (!res.ok) throw new Error(`API error: ${res.status} ${res.statusText}`);
  return res.json();
}

export async function fetchText(path: string): Promise<string> {
  const res = await fetch(`${BACKEND_API}${path}`);
  if (!res.ok) throw new Error(`API error: ${res.status} ${res.statusText}`);
  return res.text();
}

export async function fetchCSV(filename: string): Promise<d3.DSVRowArray<string>> {
  return d3.csv(`${RESOURCE_SERVER}/${filename}.csv`);
}
