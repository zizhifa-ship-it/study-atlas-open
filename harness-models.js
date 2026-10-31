const esc = value => String(value ?? '').replace(/[&<>"']/g, c => ({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[c]));
const effortNames = {off:'关闭推理',low:'低',medium:'中',high:'高',max:'最高'};
export const selectionKey = value => JSON.stringify({provider:value?.provider || '',model:value?.model || ''});
export function modelEntry(catalog, key) {
  for (const group of catalog?.groups || []) for (const model of group.models) {
    if (selectionKey({provider:group.id,model:model.id})===key) return model;
  }
}
export function effortOptions(model, selected) {
  return model?.efforts?.length ? model.efforts.map(e=>`<option value="${esc(e.id)}"${e.id===selected?' selected':''}>${esc(effortNames[e.id] || e.name)}</option>`).join('') : '<option value="">由模型管理</option>';
}
export function harnessModelFields(harness) {
  const catalog=harness.catalog, selected=harness.model || {}, key=selectionKey(selected), model=modelEntry(catalog,key);
  const options=(catalog?.groups || []).map(g=>`<optgroup label="${esc(g.name)}">${g.models.map(m=>{
    const value=selectionKey({provider:g.id,model:m.id});
    return `<option value="${esc(value)}"${value===key?' selected':''}>${esc(m.name)}</option>`;
  }).join('')}</optgroup>`).join('');
  return `<fieldset class="notice"><legend>Harness 模型选择</legend><label class="field"><span>笔记使用的模型</span><select aria-label="笔记使用的模型" name="harnessModel"${harness.configured?'':' disabled'}>${model?'':`<option value="${esc(key)}" selected>${esc(selected.model ? selected.model+'（请刷新确认可用性）' : '请先连接并刷新模型列表')}</option>`}${options}</select></label><label class="field"><span>推理强度</span><select aria-label="推理强度" name="harnessEffort"${model?.efforts?.length?'':' disabled'}>${effortOptions(model,selected.reasoningEffort)}</select></label><p class="metadata">模型来自你的 Harness 可用目录。费用、速度和本机资源需求随模型而变；选择后点击下方保存，新任务才会使用。已有笔记保留。</p><button type="button" class="button small" data-action="harness-check">刷新模型列表</button><details><summary>关于模型切换</summary><p>生成笔记、脑图、译文和自查均使用保存的模型。生成途中不能切换；模型不可用会明确报错。Harness 的选择接口也会记住该模型作为自身默认值。</p></details></fieldset>`;
}
export function bindHarnessModelFields(form, catalog) {
  const select=form?.elements.namedItem('harnessModel'), effort=form?.elements.namedItem('harnessEffort');
  select?.addEventListener('change',()=>{
    const model=modelEntry(catalog,select.value);
    const preferred=model?.efforts?.some(e=>e.id===effort.value) ? effort.value : model?.defaultEffort || model?.efforts?.[0]?.id;
    effort.innerHTML=effortOptions(model,preferred);effort.disabled=!model?.efforts?.length;
  });
}
