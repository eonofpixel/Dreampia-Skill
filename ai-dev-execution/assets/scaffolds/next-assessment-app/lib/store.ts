import { mkdir, readFile, open, rename, rm } from 'node:fs/promises'
import { resolve, join } from 'node:path'
import { randomUUID } from 'node:crypto'
import type { ScoreResult } from './scoring.ts'
export type Submission = {id:string;createdAt:string;sessionId:string;grade:number;classNumber:number;studentNumber:number;answers:Record<string,number>;scoringVersion:string;scores:Record<string,ScoreResult>}
export type Audit = {at:string;action:string;count?:number;id?:string}
type State = {version:1;submissions:Submission[];audit:Audit[]}
export class DuplicateError extends Error {}
function validState(state:State) {
 const record=(x:unknown):x is Record<string,unknown> => typeof x==='object' && x!==null && !Array.isArray(x)
 const text=(x:unknown)=>typeof x==='string' && x.length>0
 const date=(x:unknown)=>typeof x==='string' && Number.isFinite(Date.parse(x)) && new Date(x).toISOString()===x
 const positive=(x:unknown)=>typeof x==='number' && Number.isInteger(x) && x>0
 return record(state) && state.version===1 && Array.isArray(state.submissions) && Array.isArray(state.audit)
  && state.submissions.every(s=>record(s) && text(s.id) && date(s.createdAt) && text(s.sessionId)
   && positive(s.grade) && positive(s.classNumber) && positive(s.studentNumber) && text(s.scoringVersion)
   && record(s.answers) && Object.values(s.answers).every(a=>positive(a) && a<=5)
   && record(s.scores) && Object.values(s.scores).every(v=>record(v)
    && typeof v.rawAverage==='number' && Number.isFinite(v.rawAverage)
    && typeof v.normalized==='number' && Number.isFinite(v.normalized) && positive(v.level)))
  && state.audit.every(a=>record(a) && date(a.at) && text(a.action)
   && (a.id===undefined || text(a.id)) && (a.count===undefined || (Number.isInteger(a.count) && a.count>=0)))
}
export class LocalStore {
 readonly dir: string
 constructor(dir=process.env.ASSESSMENT_DATA_DIR ?? resolve('.local-data')) {this.dir=resolve(dir)}
 private async transaction<T>(fn:(state:State)=>T):Promise<T> {
  await mkdir(this.dir,{recursive:true,mode:0o700})
  const lock=join(this.dir,'write.lock')
  const deadline=Date.now()+5000
  while(true) {
   try {await mkdir(lock,{mode:0o700}); break} catch(e) {
    if ((e as NodeJS.ErrnoException).code!=='EEXIST') throw e
    if(Date.now()>deadline) throw new Error('Local store locked; operator recovery required')
    await new Promise(r=>setTimeout(r,25))
   }
  }
  const temp=join(this.dir,`.store-${randomUUID()}.tmp`)
  try {
   let state:State={version:1,submissions:[],audit:[]}
   try {state=JSON.parse(await readFile(join(this.dir,'store.json'),'utf8'))} catch(e) {if((e as NodeJS.ErrnoException).code!=='ENOENT') throw e}
   if(!validState(state)) throw new Error('Invalid store; refusing overwrite')
   const result=fn(state)
   // Audit contains no raw answers, codes or student identities. Bound local metadata to 90 days.
   state.audit=state.audit.filter(a=>Date.parse(a.at)>Date.now()-90*86400000)
   const handle=await open(temp,'wx',0o600)
   try {await handle.writeFile(JSON.stringify(state)); await handle.sync()} finally {await handle.close()}
   await rename(temp,join(this.dir,'store.json'))
   const directory=await open(this.dir,'r')
   try {await directory.sync()} finally {await directory.close()}
   return result
  } finally {await rm(temp,{force:true});await rm(lock,{recursive:true,force:true})}
 }
 async insert(item:Submission) {return this.transaction(s=>{
  if(s.submissions.some(x=>x.sessionId===item.sessionId && x.grade===item.grade && x.classNumber===item.classNumber && x.studentNumber===item.studentNumber)) throw new DuplicateError('Duplicate submission')
  s.submissions.push(item);s.audit.push({at:new Date().toISOString(),action:'submit',id:item.id});return item
 })}
 async snapshot(){return this.transaction(s=>structuredClone(s))}
 async audit(action:string){return this.transaction(s=>{s.audit.push({at:new Date().toISOString(),action})})}
 async delete(id:string){return this.transaction(s=>{
  const before=s.submissions.length;s.submissions=s.submissions.filter(x=>x.id!==id)
  const found=before!==s.submissions.length
  s.audit.push({at:new Date().toISOString(),action:'delete',id,count:found?1:0});return found
 })}
 async retain(days:number){
  if(!Number.isInteger(days)||days<1||days>365) throw new Error('Invalid retention')
  return this.transaction(s=>{
   const before=s.submissions.length;s.submissions=s.submissions.filter(x=>Date.parse(x.createdAt)>=Date.now()-days*86400000)
   const count=before-s.submissions.length;s.audit.push({at:new Date().toISOString(),action:'retention',count});return count
  })
 }
}
export const store = new LocalStore()
