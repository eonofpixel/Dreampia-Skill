'use client'
import { useEffect, useState } from 'react'
import type { FormEvent } from 'react'
import type { Submission, Audit } from '../../lib/store'
import bank from '../../data/questions.sample.json'
type Dashboard={submissions:Submission[];statistics:{count:number;mean:number|null;byClass:Record<string,number>}}
export default function Admin(){
 const [data,setData]=useState<Dashboard|null>(null);const [audit,setAudit]=useState<Audit[]>([])
 const [key,setKey]=useState('');const [error,setError]=useState('');const [message,setMessage]=useState('');const [busy,setBusy]=useState(true);const [days,setDays]=useState('30')
 async function load(){
  const response=await fetch('/api/admin/submissions',{cache:'no-store'})
  if(response.status===401){setData(null);setAudit([]);return}
  const body=await response.json();if(!response.ok)throw new Error(body.error)
  setData(body)
  const log=await fetch('/api/admin/audit',{cache:'no-store'})
  if(log.ok)setAudit((await log.json()).audit)
 }
 useEffect(()=>{load().catch(e=>setError(e.message)).finally(()=>setBusy(false))},[])
 async function action(path:string,body:unknown,method='POST'){
  setError('');setMessage('');setBusy(true)
  try{
   const response=await fetch(path,{method,headers:{'Content-Type':'application/json'},body:JSON.stringify(body)})
   const result=await response.json();if(!response.ok){if(response.status===401){setData(null);setAudit([])}throw new Error(result.error)}
   await load();return result
  }catch(e){setError(e instanceof Error?e.message:'연결에 실패했습니다.')}finally{setBusy(false)}
 }
 async function login(e:FormEvent){e.preventDefault();const result=await action('/api/admin/login',{secret:key});if(result)setKey('')}
 return <main>
  <header className="topbar"><a className="brand" href="/">Dreampia <span>LOCAL LAB</span></a><a href="/">학생 진단</a></header>
  <section className="hero"><p className="eyebrow">로컬 운영 도구</p><h1>{data?'진단 운영 현황':'관리자 인증'}</h1><p>실제 로컬 제출 데이터만 표시합니다. 비밀키가 설정되지 않으면 접근할 수 없습니다.</p></section>
  {error&&<p role="alert" className="error">{error}</p>}{message&&<p role="status" className="success">{message}</p>}
  {!data?<form onSubmit={login} className="panel login"><h2>관리자 로그인</h2><label>관리자 비밀키<input type="password" autoComplete="off" required maxLength={512} value={key} onChange={e=>setKey(e.target.value)}/></label><button disabled={busy}>{busy?'확인 중…':'로그인'}</button><p className="muted">공유 운영 계정이 아닌, 로컬 개발용 비밀키 인증입니다. 세션은 1시간 후 만료됩니다.</p></form>:
  <><div className="stats"><article className="stat">제출 수<strong data-testid="submission-count">{data.statistics.count}건</strong></article><article className="stat">전체 평균<strong>{data.statistics.mean===null?'—':`${data.statistics.mean}점`}</strong></article><article className="stat">반별 제출 수{Object.entries(data.statistics.byClass).map(([label,count])=><p key={label}>{label} · {count}건</p>)}{!data.statistics.count&&<p>아직 제출이 없습니다.</p>}</article></div>
   <div className="admin-controls"><a className="export" href="/admin/export">CSV 내려받기</a><button className="secondary bg-transparent" disabled={busy} onClick={()=>{setError('');setBusy(true);load().catch(e=>setError(e.message)).finally(()=>setBusy(false))}}>새로고침</button><button className="secondary bg-transparent" disabled={busy} onClick={()=>action('/api/admin/logout',{})}>로그아웃</button></div>
   <section className="panel"><h2>제출 목록</h2><p className="muted">이름을 수집하지 않습니다. 삭제하면 해당 번호로 재응답할 수 있습니다. 삭제는 되돌릴 수 없습니다. 좁은 화면에서는 표를 가로로 밀거나 초점을 맞춘 뒤 방향키로 이동하세요.</p><div className="table-wrap" role="region" aria-label="제출 목록 표" tabIndex={0}><table><thead><tr><th>학년·반·번호</th><th>전체</th><th>AI 윤리·보안</th><th>진로 탐색</th><th>제출 시각</th><th>관리</th></tr></thead><tbody>{data.submissions.map(s=><tr key={s.id}><td>{s.grade}학년 {s.classNumber}반 {s.studentNumber}번</td><td>{s.scores.total.normalized}</td><td>{s.scores.ai_ethics_security?.normalized}</td><td>{s.scores.career?.normalized}</td><td>{new Date(s.createdAt).toLocaleString('ko-KR')}</td><td><button className="danger bg-transparent" disabled={busy} onClick={async()=>{const result=await action('/api/admin/submissions',{id:s.id},'DELETE');if(result)setMessage('제출 1건을 삭제했습니다.')}}>삭제</button></td></tr>)}</tbody></table></div>{!data.submissions.length&&<p className="notice">아직 제출된 응답이 없습니다. 학생 진단을 완료하면 여기에 표시됩니다.</p>}
   {data.submissions.map(s=><details key={s.id}><summary>{s.grade}-{s.classNumber}-{s.studentNumber} 응답 상세</summary><p className="muted">채점 버전: {s.scoringVersion}</p><ul>{bank.questions.map(q=><li key={q.id}>{q.text} <strong>{s.answers[q.id]} / 5</strong></li>)}</ul></details>)}
   </section><section className="panel"><h2>보존 기간과 삭제</h2><p className="muted">설정한 기간보다 오래된 제출(응답·식별정보·결과)을 즉시 삭제합니다. 자동 스케줄 작업은 없습니다. 감사 로그는 90일 유지되며, 별도 CSV 파일은 사용자가 직접 삭제해야 합니다.</p><label>보존 기간 (일)<input type="number" min={1} max={365} step={1} value={days} onChange={e=>setDays(e.target.value)}/></label><button disabled={busy} onClick={async()=>{const result=await action('/api/admin/retention',{days:Number(days)});if(result)setMessage(`${result.deleted}건 삭제 · 보존 기간을 적용했습니다.`)}}>보존 기간 적용</button></section>
   <section className="panel"><h2>감사 로그</h2><p className="muted">조회·내보내기·삭제·보존 작업을 확인합니다. 코드, 비밀키, 학생 응답은 로그에 남기지 않습니다.</p><ul className="audit">{audit.slice().reverse().map((a,i)=><li key={i}>{a.at} · {a.action}{a.count!==undefined?` · ${a.count}건`:''}</li>)}</ul></section></>}
  <footer>외부 공개·실제 학교 운영용이 아닙니다. 보호된 로컬 컴퓨터에서 합성 데이터로만 사용하세요.</footer>
 </main>
}
