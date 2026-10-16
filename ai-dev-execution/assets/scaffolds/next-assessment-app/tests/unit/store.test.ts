import { test } from 'node:test'
import assert from 'node:assert/strict'
import { mkdtemp, readFile, rm, writeFile } from 'node:fs/promises'
import { spawn } from 'node:child_process'
import { tmpdir } from 'node:os'
import { join } from 'node:path'
import { LocalStore } from '../../lib/store.ts'
import { csvCell } from '../../lib/csv.ts'
test('durable concurrency, duplicates, deletion, retention and audit', async () => {
 const dir = await mkdtemp(join(tmpdir(),'assessment-unit-'))
 try {
  const store = new LocalStore(dir)
  const item = {id:'a',createdAt:new Date().toISOString(),sessionId:'test',grade:1,classNumber:1,studentNumber:1,answers:{Q001:5},scoringVersion:'v1',scores:{total:{rawAverage:5,normalized:100,level:5}}}
  const results = await Promise.allSettled(Array.from({length:6},()=>store.insert(item)))
  assert.equal(results.filter(r=>r.status==='fulfilled').length,1)
  assert.equal((await new LocalStore(dir).snapshot()).submissions.length,1)
  await store.audit('export')
  assert.equal(await store.delete('a'),true)
  await store.insert({...item,id:'b',createdAt:'2000-01-01T00:00:00.000Z'})
  assert.equal(await store.retain(30),1)
  const data = await store.snapshot()
  assert.equal(data.submissions.length,0)
  assert.deepEqual(data.audit.map(a=>a.action),['submit','export','delete','submit','retention'])
  assert.ok(!(await readFile(join(dir,'store.json'),'utf8')).includes('studentNumber'))
 } finally {await rm(dir,{recursive:true,force:true})}
})
test('separate processes share atomic duplicate lock and persisted state',async()=>{
 const dir=await mkdtemp(join(tmpdir(),'assessment-process-'))
 const item={id:'process-test',createdAt:new Date().toISOString(),sessionId:'test',grade:1,classNumber:1,studentNumber:1,answers:{Q001:5},scoringVersion:'v1',scores:{total:{rawAverage:5,normalized:100,level:5}}}
 const source=`import {LocalStore,DuplicateError} from ${JSON.stringify(new URL('../../lib/store.ts',import.meta.url).href)};try{await new LocalStore(${JSON.stringify(dir)}).insert(${JSON.stringify(item)})}catch(e){process.exit(e instanceof DuplicateError?2:3)}`
 try{
  const codes=await Promise.all(Array.from({length:4},()=>new Promise<number|null>((done,reject)=>{
   const child=spawn(process.execPath,['--experimental-strip-types','--input-type=module','-e',source],{stdio:'ignore'})
   child.once('error',reject);child.once('exit',done)
  })))
  assert.deepEqual(codes.sort(),[0,2,2,2])
  assert.equal((await new LocalStore(dir).snapshot()).submissions.length,1)
 }finally{await rm(dir,{recursive:true,force:true})}
})
test('corrupt storage is never silently overwritten',async()=>{
 const dir=await mkdtemp(join(tmpdir(),'assessment-corrupt-'))
 try{
  await writeFile(join(dir,'store.json'),'broken-json')
  await assert.rejects(new LocalStore(dir).snapshot())
  assert.equal(await readFile(join(dir,'store.json'),'utf8'),'broken-json')
 }finally{await rm(dir,{recursive:true,force:true})}
})
test('valid JSON with invalid submission or audit dates is preserved on snapshot and retention',async()=>{
 const dir=await mkdtemp(join(tmpdir(),'assessment-structural-corrupt-'))
 try{
  for(const data of [
   {version:1,submissions:[{id:'broken',createdAt:'not-a-date',sessionId:'test',grade:1,classNumber:1,studentNumber:1,answers:{Q001:5},scoringVersion:'v1',scores:{total:{rawAverage:5,normalized:100,level:5}}}],audit:[]},
   {version:1,submissions:[],audit:[{at:'not-a-date',action:'submit'}]},
  ]){
   const original=JSON.stringify(data)
   await writeFile(join(dir,'store.json'),original)
   await assert.rejects(new LocalStore(dir).snapshot())
   assert.equal(await readFile(join(dir,'store.json'),'utf8'),original)
   await assert.rejects(new LocalStore(dir).retain(30))
   assert.equal(await readFile(join(dir,'store.json'),'utf8'),original)
  }
 }finally{await rm(dir,{recursive:true,force:true})}
})
test('CSV spreadsheet injection and RFC quoting',()=>{
 for(const value of ['=1+1','+cmd','-2','@SUM(A1)','\t=cmd','\r=cmd',' =cmd','\n=cmd']) assert.ok(csvCell(value).startsWith('"\''))
 assert.equal(csvCell('a,"b"'), '"a,""b"""')
})
