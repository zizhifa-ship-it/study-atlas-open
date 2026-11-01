const form = document.querySelector('#login-form');
const input = document.querySelector('#code');
const status = document.querySelector('#status');

fetch('/api/session', {headers: {'Accept': 'application/json'}})
  .then(response => response.ok ? response.json() : null)
  .then(value => { if (value?.authenticated) location.replace('/'); })
  .catch(() => {});

form.addEventListener('submit', async event => {
  event.preventDefault();
  const button = form.querySelector('button');
  const code = input.value.trim();
  if (!code) return;
  button.disabled = true;
  status.textContent = '正在验证…';
  try {
    const response = await fetch('/api/session', {
      method: 'POST',
      headers: {'Content-Type': 'application/json', 'Accept': 'application/json'},
      body: JSON.stringify({code}),
    });
    const result = await response.json().catch(() => ({}));
    if (!response.ok) throw new Error(result.error || '登录码不正确');
    status.textContent = '登录成功，正在打开…';
    location.replace('/');
  } catch (error) {
    status.textContent = error.message || '登录失败，请重试';
    input.select();
  } finally {
    button.disabled = false;
  }
});
