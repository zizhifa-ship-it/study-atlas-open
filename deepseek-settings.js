const esc = value => String(value ?? '').replace(/[&<>"']/g, c => ({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[c]));

export function deepseekFields(status) {
  return `<p class="notice">${status.deployment?.mode==='private-server'?esc(status.deployment.message):'网页 API 模式：由网站后端直接调用 DeepSeek，不需要启动 Harness。网站部署在服务器后，iPad 可独立使用；只在电脑启动网站时，电脑仍需保持运行。'}</p>
    <label class="field"><span>官方 API 模型</span><input aria-label="官方 API 模型" name="model" maxlength="100" value="${esc(status.ai.model)}" list="deepseek-models"><datalist id="deepseek-models"></datalist><small>可填写实际模型 ID，或检查连接后从账号模型中选择。</small></label>
    <label class="field"><span>DeepSeek API Key</span><input aria-label="DeepSeek API Key" name="apiKey" type="password" autocomplete="new-password" placeholder="${status.ai.hasApiKey?'已保存；留空保留现有密钥':'填写你的 DeepSeek API Key'}"><small>密钥仅保存在网站后端，不写入网页存储或导出文件。学习资料会发送至 api.deepseek.com，费用由你的 DeepSeek 账号承担。</small></label>
    <button type="button" class="button small soft" data-deepseek-check>检查连接并读取模型</button><p class="metadata" role="status" data-deepseek-status></p>`;
}

export function bindDeepseekFields(form, post) {
  const button=form.querySelector('[data-deepseek-check]');
  if(!button)return;
  button.addEventListener('click',async()=>{
    const status=form.querySelector('[data-deepseek-status]');
    button.disabled=true;status.textContent='正在检查官方 API…';
    try {
      const result=await post('/api/integrations/deepseek/models',{apiKey:form.elements.namedItem('apiKey').value});
      const list=form.querySelector('#deepseek-models');list.replaceChildren();
      for(const model of result.models){const option=document.createElement('option');option.value=model.id;list.append(option);}
      const input=form.elements.namedItem('model');if(!input.value && result.models.length)input.value=result.models[0].id;
      status.textContent=result.message+' 共 '+result.models.length+' 个模型。';
    }catch(error){status.textContent=error.message;}
    finally{button.disabled=false;}
  });
}
