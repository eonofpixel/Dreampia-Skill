import { validateCode, PublicError } from '../../../lib/assessment'
import { sameOrigin, jsonBody, failure, throttle, privateHeaders } from '../../../lib/security'
export async function POST(request:Request) {
 try {
  sameOrigin(request);throttle('access')
  const body=await jsonBody(request)
  if(!body || Object.keys(body).join(',')!=='code')throw new PublicError('진단 코드를 확인하세요.')
  validateCode(body.code)
  return Response.json({ok:true},{headers:privateHeaders})
 }catch(e){return failure(e)}
}
