import { store } from '../../../../lib/store'
import { requireAdmin, sameOrigin, jsonBody, failure, privateHeaders } from '../../../../lib/security'
import { PublicError } from '../../../../lib/assessment'
export async function POST(request:Request){try{
 sameOrigin(request);requireAdmin(request)
 const body=await jsonBody(request)
 if(!body || Object.keys(body).join(',')!=='days' || !Number.isInteger(body.days) || body.days<1 || body.days>365)throw new PublicError('보존 기간은 1~365일입니다.')
 return Response.json({deleted:await store.retain(body.days)},{headers:privateHeaders})
}catch(e){return failure(e)}}
