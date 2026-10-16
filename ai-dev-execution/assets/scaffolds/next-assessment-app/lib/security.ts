import { createHmac, timingSafeEqual, randomBytes } from 'node:crypto'
import { PublicError } from './assessment.ts'
export const cookieName='assessment_admin'
export function secret() {const key=process.env.ASSESSMENT_ADMIN_SECRET;return key && key.length>=32 ? key : null}
export function safeEqual(a:string,b:string){return Buffer.byteLength(a)===Buffer.byteLength(b)&&timingSafeEqual(Buffer.from(a),Buffer.from(b))}
export function adminToken(expires=Date.now()+3600000) {
 const key=secret();if(!key) throw new PublicError('관리자 인증 설정이 필요합니다.',503)
 const payload=`${expires}.${randomBytes(16).toString('hex')}`
 return payload+'.'+createHmac('sha256',key).update(payload).digest('hex')
}
export function isAdmin(request:Request) {
 const key=secret();if(!key)return false
 const token=(request.headers.get('cookie')??'').split(';').map(x=>x.trim()).find(x=>x.startsWith(cookieName+'='))?.slice(cookieName.length+1)
 if(!token || token.length>200)return false
 const parts=token.split('.')
 if(parts.length!==3 || !/^\d+$/.test(parts[0]) || Number(parts[0])<=Date.now() || Number(parts[0])>Date.now()+3600000+1000)return false
 return safeEqual(parts[2],createHmac('sha256',key).update(parts.slice(0,2).join('.')).digest('hex'))
}
export function requireAdmin(request:Request){if(!isAdmin(request))throw new PublicError('관리자 인증이 필요합니다.',401)}
export function sameOrigin(request:Request){
 const host=request.headers.get('host')
 let origin:URL
 try{origin=new URL(request.headers.get('origin')??'')}catch{throw new PublicError('허용되지 않은 요청입니다.',403)}
 // Next may synthesize request.url with localhost; the browser's actual Host is authoritative.
 // Reject non-loopback hosts too, rather than trusting arbitrary or forwarded Host headers.
 if(!host || !['127.0.0.1','localhost','[::1]'].includes(origin.hostname) || origin.host!==host || origin.protocol!==new URL(request.url).protocol)throw new PublicError('허용되지 않은 요청입니다.',403)
}
// Loopback-only throttle, deliberately not a distributed abuse-prevention system.
const attempts=new Map<string,{count:number;until:number}>()
export function throttle(scope:string,limit=20){
 const now=Date.now();let item=attempts.get(scope)
 if(!item || item.until<now){item={count:0,until:now+60000};attempts.set(scope,item)}
 if(++item.count>limit)throw new PublicError('요청이 너무 많습니다. 잠시 후 다시 시도하세요.',429)
}
export async function jsonBody(request:Request) {
 const text=await request.text()
 if(Buffer.byteLength(text)>16384)throw new PublicError('입력 크기가 너무 큽니다.',413)
 try{return JSON.parse(text)}catch{throw new PublicError('JSON 입력을 확인하세요.')}
}
export function failure(error:unknown) {
 const known=error instanceof PublicError
 return Response.json({error:known?error.message:'로컬 저장소에 접근할 수 없습니다. 관리자에게 문의하세요.'},{status:known?error.status:503,headers:{'Cache-Control':'no-store'}})
}
export const privateHeaders={'Cache-Control':'no-store','X-Content-Type-Options':'nosniff'}
