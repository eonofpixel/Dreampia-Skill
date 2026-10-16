import { store } from '../../../lib/store'
import { submissionsCSV } from '../../../lib/csv'
import { requireAdmin, failure, privateHeaders } from '../../../lib/security'
export const dynamic='force-dynamic'
export async function GET(request:Request){try{
 requireAdmin(request)
 const {submissions}=await store.snapshot();await store.audit('export')
 return new Response(submissionsCSV(submissions),{headers:{...privateHeaders,'Content-Type':'text/csv; charset=utf-8','Content-Disposition':'attachment; filename="assessment-submissions.csv"'}})
}catch(e){return failure(e)}}
