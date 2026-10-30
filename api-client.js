// 令牌仅驻留内存。403 明确表示尚未执行时，才在服务重启后刷新一次。
export function createApiFetch(fetcher = fetch) {
  let pending;
  const token = () => pending ||= fetcher('/api/security', {cache:'no-store', credentials:'same-origin'})
    .then(async response => {
      if (!response.ok) throw new Error('安全连接未建立，请刷新页面');
      const data = await response.json();
      if (typeof data.token !== 'string' || !/^[a-f0-9]{64}$/.test(data.token)) throw new Error('安全连接响应无效');
      return data.token;
    }).catch(error => {pending = undefined; throw error;});
  return async function apiFetch(url, options = {}) {
    if (typeof url !== 'string' || !url.startsWith('/api/')) throw new Error('接口地址必须属于当前知识库');
    const method = (options.method || 'GET').toUpperCase();
    if (['GET','HEAD'].includes(method)) return fetcher(url, {...options, credentials:'same-origin'});
    const send = async () => {
      const headers = new Headers(options.headers);
      headers.set('X-Study-Atlas-Token', await token());
      return fetcher(url, {...options, headers, credentials:'same-origin'});
    };
    let response = await send();
    if (response.status === 403) {
      const error = await response.clone().json().catch(() => ({}));
      if (error.code === 'security_token') {pending = undefined; response = await send();}
    }
    return response;
  };
}
export const apiFetch = createApiFetch();
