// Files are parsed locally before preview. This path never calls an AI model.
export async function readLearningFile(file, post, encode = blob => new Promise((resolve, reject) => {
  const reader = new FileReader();
  reader.onerror = () => reject(new Error('文件读取失败，请重新选择'));
  reader.onload = () => resolve(String(reader.result).split(',')[1]);
  reader.readAsDataURL(blob);
})) {
  if (/\.pdf$/i.test(file.name)) {
    if (file.size > 32 * 1024 * 1024) throw new Error('PDF 最多 32 MB，请按章节拆分');
    const result = await post('/api/material/pdf', {filename: file.name, base64: await encode(file)});
    return {...result, readLocally: true};
  }
  if (/\.(docx|html|htm)$/i.test(file.name)) {
    if (file.size > 32 * 1024 * 1024) throw new Error('DOCX / HTML 最多 32 MB，请按章节拆分');
    return post('/api/material/document', {filename: file.name, base64: await encode(file)});
  }
  if (!/\.(txt|md|markdown|srt|vtt|json|json3)$/i.test(file.name)) throw new Error('请选择 PDF、DOCX、HTML、文字、Markdown 或字幕文件');
  if (file.size > 16 * 1024 * 1024) throw new Error('文字文件最多 16 MB，请按章节拆分');
  const content = await file.text();
  if (content.length > 800000) throw new Error('正文最多 80 万字符，请按章节拆分');
  return {content, filename: file.name, title: file.name.replace(/\.[^.]+$/, ''), warning: '', readLocally: true};
}
