import {hash} from './ai.js';
export const normalizeSource=text=>String(text||'').replace(/\r\n?/g,'\n').replace(/^(?:[ \t]*\n)+|(?:\n[ \t]*)+$/g,'');
export const hasNotes=video=>!!(video?.summary?.trim()&&video.knowledge?.modules?.length&&!video.notesStale);
export const auditFinished=video=>['reviewed','needs_review'].includes(video?.knowledge?.review?.status)&&video.knowledge.review.completed===true;
export function duplicateSource(videos,source,url,except=''){const normalized=normalizeSource(source);return videos.find(v=>v.id!==except&&((normalized.length>=20&&normalizeSource(v.transcript)===normalized)||(/^https?:/.test(url||'')&&v.url===url)));}
const stamp=()=>new Date().toISOString();

// Durable phases: a failed audit or a reload never sends the course through notes again.
export class NoteJobs {
  constructor({ai,readLibrary,saveLibrary,getJob,setJob,onChange=()=>{}}){Object.assign(this,{ai,readLibrary,saveLibrary,getJob,setJob,onChange});this.active=new Map();}
  async queue(video){const source=normalizeSource(video.transcript);if(source.length<20)return;const fingerprint=await hash(source),old=await this.getJob(video.id);if(hasNotes(video)&&!video.notesStale&&(!old||old.fingerprint===fingerprint)&&(!video.generation?.language||video.generation.language===(video.noteLanguage||'简体中文')))return old;
    if(old?.fingerprint===fingerprint&&old.language===(video.noteLanguage||'简体中文')&&old.status!=='done')return old;
    const job={videoId:video.id,fingerprint,language:video.noteLanguage||'简体中文',stage:'notes',status:'queued',createdAt:stamp(),updatedAt:stamp()};await this.setJob(job);return job;}
  run(id,options={}){if(this.active.has(id))return this.active.get(id);const work=async()=>this._run(id,options);const promise=globalThis.navigator?.locks?globalThis.navigator.locks.request('study-atlas-notes:'+id,{ifAvailable:true},lock=>{if(!lock)throw Error('另一标签页正在整理这份资料，请直接等待其保存');return work();}):work();this.active.set(id,promise);return promise.finally(()=>this.active.delete(id));}
  async _run(id,{force=false,signal}={}){
    let library=await this.readLibrary(),video=library.videos.find(v=>v.id===id);if(!video)throw Error('这份资料已移除');
    const source=normalizeSource(video.transcript),fingerprint=await hash(source),language=video.noteLanguage||'简体中文';let job=await this.getJob(id);
    if(!force&&hasNotes(video)&&(!video.generation?.language||video.generation.language===language)&&(!job||job.status==='done'||job.fingerprint!==fingerprint))return {reused:true};
    if(!job||job.fingerprint!==fingerprint||job.language!==language||force){job={videoId:id,fingerprint,language,stage:!force&&hasNotes(video)?'audit':'notes',status:'queued',createdAt:stamp(),baselineSummary:video.summary||'',force};}
    const update=async fields=>{job={...job,...fields,updatedAt:stamp()};await this.setJob(job);await this.onChange();};
    try{
      await update({status:'running',error:''});
      if(job.stage==='notes'){
        const result=await this.ai.notes(source,language,signal,{revision:job.force?job.createdAt:undefined});
        await update({stage:'apply',result,model:this.ai.model,baselineSummary:job.baselineSummary??video.summary});
      }
      if(job.stage==='apply'){
        library=await this.readLibrary();video=library.videos.find(v=>v.id===id);
        if(!video||normalizeSource(video.transcript)!==source||video.summary!==(job.baselineSummary||''))throw Error('资料或笔记已被修改，生成结果已保存，未覆盖你的编辑');
        const result=job.result;
        if(video.summary&&video.summary!==result.summary)video.notes.push({id:crypto.randomUUID(),timeSec:null,text:'旧版总结（'+stamp()+'）\n'+video.summary,createdAt:stamp()});
        let category=library.categories.find(c=>c.name===result.category);if(!category){category={id:crypto.randomUUID().replaceAll('-',''),name:result.category,parentId:null,color:'green',description:''};library.categories.push(category);}
        Object.assign(video,{aiTitle:result.title,categoryId:category.id,tags:result.tags,summary:result.summary,cornell:result.cornell,notesStale:false,studyProgress:{},generation:{sourceHash:fingerprint,language,model:job.model,createdAt:stamp()},knowledge:{title:result.title,overview:result.overview,modules:result.modules,materialKind:source.length>12000?'原文的分层摘录':'用户提供的实际资料',materialHash:fingerprint,model:job.model,review:{status:'needs_review',completed:false,summary:'笔记已保存，独立自查尚未完成；无需重做笔记。',issues:[],corrections:[],checkedAt:stamp()}},updatedAt:stamp()});
        job={...job,stage:'audit',status:'running',updatedAt:stamp()};await this.saveLibrary(library,library.revision,job);await this.onChange();
      }
      if(job.stage==='audit'){
        library=await this.readLibrary();video=library.videos.find(v=>v.id===id);
        if(!video||normalizeSource(video.transcript)!==source)throw Error('资料已改变，旧自查结果不会覆盖新内容');
        const summary=video.summary,material=job.result?.material||await this.ai.prepare(source,signal);
        const review=await this.ai.review({title:video.aiTitle||video.title,summary,modules:video.knowledge.modules},material,signal);
        library=await this.readLibrary();video=library.videos.find(v=>v.id===id);
        if(!video||normalizeSource(video.transcript)!==source||video.summary!==summary)throw Error('笔记已更新，自查结果没有覆盖你的编辑');
        video.knowledge.review={...review,completed:true};job={...job,stage:'done',status:'done',result:undefined,error:'',updatedAt:stamp()};
        await this.saveLibrary(library,library.revision,job);await this.onChange();
      }
      return {reused:false};
    }catch(error){await update({status:error.code==='RESULT_UNCERTAIN'?'uncertain':error.code==='MISSING_KEY'?'queued':'paused',error:error.message,errorCode:error.code||'',hasSavedNotes:job.stage==='audit'||job.stage==='done'});throw error;}
  }
}
