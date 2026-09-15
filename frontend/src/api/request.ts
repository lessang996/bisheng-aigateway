export async function request(input: RequestInfo | URL, init?: RequestInit): Promise<Response> {
  const response = await fetch(input, init)
  if (!response.ok) throw new Error(`请求失败（${response.status}）`)
  return response
}
