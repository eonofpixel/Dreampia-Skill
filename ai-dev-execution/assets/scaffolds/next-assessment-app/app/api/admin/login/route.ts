import { NextResponse } from 'next/server'
import { secret, safeEqual, adminToken, cookieName, sameOrigin, jsonBody, failure, throttle } from '../../../../lib/security'
import { PublicError } from '../../../../lib/assessment'
import { store } from '../../../../lib/store'
export async function POST(request:Request){
 try{
  sameOrigin(request);throttle('login',10)
  const key=secret();if(!key)throw new PublicError('관리자 인증 설정이 필요합니다.',503)
  const body=await jsonBody(request)
  if(!body || Object.keys(body).join(',')!=='secret' || typeof body.secret!=='string' || body.secret.length>512 || !safeEqual(body.secret,key))throw new PublicError('관리자 인증에 실패했습니다.',401)
  await store.audit('login')
  const response=NextResponse.json({ok:true},{headers:{'Cache-Control':'no-store'}})
  response.cookies.set(cookieName,adminToken(),{httpOnly:true,sameSite:'strict',secure:new URL(request.url).protocol==='https:',path:'/',maxAge:3600})
  return response
 }catch(e){return failure(e)}
}
