import { store } from '../../../../lib/store'
import { requireAdmin, sameOrigin, jsonBody, failure, privateHeaders } from '../../../../lib/security'
import { PublicError } from '../../../../lib/assessment'
export const dynamic='force-dynamic'
export async function GET(request:Request){try{
 requireAdmin(request);await store.audit('read')
 const {submissions}=await store.snapshot()
 const count=submissions.length
 const mean=count?Math.round(submissions.reduce((sum,s)=>sum+s.scores.total.normalized,0)/count):null
 const byClass:Record<string,number>={}
 for(const s of submissions){const key=`${s.grade}학년 ${s.classNumber}반`;byClass[key]=(byClass[key]??0)+1}
 return Response.json({submissions,statistics:{count,mean,byClass}},{headers:privateHeaders})
}catch(e){return failure(e)}}
export async function DELETE(request:Request){try{
 sameOrigin(request);requireAdmin(request)
 const body=await jsonBody(request)
 if(!body || Object.keys(body).join(',')!=='id' || typeof body.id!=='string' || !/^[a-f0-9-]{36}$/.test(body.id))throw new PublicError('삭제 대상을 확인하세요.')
 const deleted=await store.delete(body.id)
 if(!deleted)throw new PublicError('대상을 찾을 수 없습니다.',404)
 return Response.json({deleted:true},{headers:privateHeaders})
}catch(e){return failure(e)}}
