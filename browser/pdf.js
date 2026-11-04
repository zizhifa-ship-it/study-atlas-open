export async function readPDF(file,progress=()=>{}){
  if(file.size>8*1024*1024)throw Error('PDF 最多 8 MB，请按章节拆分');
  // Polyfill for older iPadOS versions before importing the legacy PDF.js build.
  if(!Promise.withResolvers)Promise.withResolvers=function(){let resolve,reject;const promise=new Promise((a,b)=>{resolve=a;reject=b;});return {promise,resolve,reject};};
  let task,document;
  try{
    const pdf=await import('./vendor/pdfjs/pdf.mjs');
    pdf.GlobalWorkerOptions.workerSrc=new URL('./vendor/pdfjs/pdf.worker.mjs',import.meta.url).href;
    task=pdf.getDocument({data:new Uint8Array(await file.arrayBuffer()),isEvalSupported:false,useWasm:false,cMapUrl:new URL('./vendor/pdfjs/cmaps/',import.meta.url).href,cMapPacked:true,standardFontDataUrl:new URL('./vendor/pdfjs/standard_fonts/',import.meta.url).href});
    document=await task.promise;
    if(document.numPages>300)throw Error('PDF 最多 300 页，请按章节拆分');
    const parts=[],empty=[];let size=0;
    for(let i=1;i<=document.numPages;i++){
      progress('正在本机读取 PDF：'+i+'/'+document.numPages+' 页');
      const page=await document.getPage(i),content=await page.getTextContent();
      const text=content.items.map(item=>item.str+(item.hasEOL?'\n':' ')).join('').trim();
      if(!text){empty.push(i);page.cleanup();continue;}
      const part='[PDF 第 '+i+' 页]\n'+text;size+=part.length+2;if(size>800000)throw Error('PDF 正文超过 80 万字符，请分章节导入');parts.push(part);page.cleanup();
    }
    if(parts.join('').length<40)throw Error('未读取到足够正文；扫描版 PDF 请先 OCR，不会依据文件名编造笔记');
    return {text:parts.join('\n\n'),pages:document.numPages,warning:empty.length?'有 '+empty.length+' 页没有可读取文字，可能需要 OCR；图片与图表未被识别。':'已提取文字和页码；图表、公式和排版请对照原 PDF。'};
  }catch(error){if(error.name==='PasswordException')throw Error('PDF 有密码，请先解锁后导入');if(error.message?.includes('Failed to fetch'))throw Error('PDF 组件暂时无法加载，请刷新重试；文字导入仍可使用');throw error;}finally{if(task){try{await task.destroy();}catch{}}}
}
