import { store } from '../../../../lib/store'
import { requireAdmin, failure, privateHeaders } from '../../../../lib/security'
export const dynamic='force-dynamic'
export async function GET(request:Request){try{
 requireAdmin(request);await store.audit('audit_read')
 return Response.json({audit:(await store.snapshot()).audit},{headers:privateHeaders})
}catch(e){return failure(e)}}
