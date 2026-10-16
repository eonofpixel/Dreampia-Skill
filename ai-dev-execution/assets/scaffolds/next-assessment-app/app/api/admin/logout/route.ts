import { NextResponse } from 'next/server'
import { cookieName, sameOrigin, requireAdmin, failure } from '../../../../lib/security'
import { store } from '../../../../lib/store'
export async function POST(request:Request){try{
 sameOrigin(request);requireAdmin(request);await store.audit('logout')
 const response=NextResponse.json({ok:true},{headers:{'Cache-Control':'no-store'}})
 response.cookies.set(cookieName,'',{httpOnly:true,sameSite:'strict',path:'/',maxAge:0})
 return response
}catch(e){return failure(e)}}
