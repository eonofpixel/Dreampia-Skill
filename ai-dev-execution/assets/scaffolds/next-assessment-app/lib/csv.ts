import type { Submission } from './store.ts'
export function csvCell(value:unknown) {
 let text=String(value ?? '')
 if (/^[\s\u0000-\u001f]*[=+\-@]/.test(text) || /^[\t\r\n]/.test(text)) text="'"+text
 return '"'+text.replaceAll('"','""')+'"'
}
export function submissionsCSV(rows:Submission[]) {
 const headers=['id','created_at','session_id','grade','class','number','scoring_version','total','ai_ethics_security','career','answers_json']
 return '\uFEFF'+[headers,...rows.map(s=>[s.id,s.createdAt,s.sessionId,s.grade,s.classNumber,s.studentNumber,s.scoringVersion,s.scores.total.normalized,s.scores.ai_ethics_security?.normalized,s.scores.career?.normalized,JSON.stringify(s.answers)])].map(row=>row.map(csvCell).join(',')).join('\r\n')+'\r\n'
}
