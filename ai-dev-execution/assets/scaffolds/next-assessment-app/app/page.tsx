'use client'
import { useState } from 'react'
import type { FormEvent } from 'react'
import bank from '../data/questions.sample.json'
import type { ScoreResult } from '../lib/scoring'
const scale=['전혀 아니다','아니다','보통이다','그렇다','매우 그렇다']
export default function Page(){
 const [identity,setIdentity]=useState({code:'',grade:'',classNumber:'',studentNumber:''})
 const [started,setStarted]=useState(false)
 const [answers,setAnswers]=useState<Record<string,number>>({})
 const [scores,setScores]=useState<Record<string,ScoreResult>|null>(null)
 const [error,setError]=useState('');const [busy,setBusy]=useState(false)
 async function send(event:FormEvent){
  event.preventDefault();setError('');setBusy(true)
  try {
   const response=await fetch(started?'/api/submit':'/api/access',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify(started?{...identity,grade:Number(identity.grade),classNumber:Number(identity.classNumber),studentNumber:Number(identity.studentNumber),answers}:{code:identity.code})})
   const data=await response.json();if(!response.ok)throw new Error(data.error)
   if(started){setScores(data.scores);setIdentity({code:'',grade:'',classNumber:'',studentNumber:''});setAnswers({})}else setStarted(true)
  }catch(e){setError(e instanceof Error?e.message:'연결에 실패했습니다. 다시 시도하세요.')}finally{setBusy(false)}
 }
 return <main>
  <header className="topbar"><a className="brand" href="/">Dreampia <span>LOCAL LAB</span></a><a href="/admin">관리자</a></header>
  <section className="hero"><p className="eyebrow">나를 알아가는 작은 시작</p><h1>{bank.title}</h1><p>정답은 없어요. 평소 나의 모습과 가장 가까운 응답을 골라주세요.</p><div className="chips"><span>회원가입 없이</span><span>4문항 · 약 2분</span><span>이름 수집 없음</span></div></section>
  {error&&<p role="alert" className="error">{error}</p>}
  {scores?<section className="panel result" aria-labelledby="result-title"><p className="eyebrow">제출 및 로컬 저장 완료</p><h2 id="result-title">나의 진단 결과</h2><p className="big-score" data-testid="total-score">{scores.total.normalized} / 100</p><p>이 결과는 현재의 자기 인식을 돌아보기 위한 참고 자료입니다. 능력의 등급이나 확정된 평가는 아니에요.</p><div className="domain-grid">{Object.entries(bank.domains).map(([id,title])=><article className="domain" key={id}><h3>{title}</h3><strong>{scores[id].normalized}점</strong><p>{scores[id].normalized>=61?'잘하고 있는 실천을 이어가세요. 다음에는 친구와 경험을 나눠보세요.':'작은 실천부터 시작해보세요. 오늘 할 수 있는 한 가지 목표를 정해보세요.'}</p></article>)}</div><p className="muted">개인 결과 재조회 링크는 제공하지 않습니다. 필요한 경우 화면을 기록하세요.</p><button onClick={()=>{setScores(null);setStarted(false)}}>시작 화면으로</button></section>:
  <form onSubmit={send} className="panel">
   <div className="section-heading"><span className="step">{started?'02':'01'}</span><div><h2>{started?'나의 모습에 응답하기':'진단에 참여하기'}</h2><p className="muted">{started?`${Object.keys(answers).length} / ${bank.questions.length}문항 응답 · 모두 선택해야 제출할 수 있어요.`:'담당자가 알려준 코드와 학년·반·번호를 입력하세요.'}</p></div></div>
   {!started?<><label>진단 코드<input autoComplete="off" spellCheck={false} value={identity.code} required maxLength={128} onChange={e=>setIdentity({...identity,code:e.target.value})} placeholder="담당자가 알려준 코드"/></label><div className="identity-grid">{[['grade','학년',12],['classNumber','반',50],['studentNumber','번호',60]].map(([key,label,max])=><label key={key}>{label}<input type="number" inputMode="numeric" min={1} max={max} step={1} required value={identity[key as keyof typeof identity]} onChange={e=>setIdentity({...identity,[key]:e.target.value})}/></label>)}</div><aside className="notice">학년·반·번호와 응답만 로컬 컴퓨터에 저장합니다. 같은 번호로는 한 번만 제출할 수 있으며, 재응답은 관리자 삭제 후 가능합니다.</aside><button disabled={busy}>{busy?'확인 중…':'진단 시작'}</button></>:
   <><div className="questions">{bank.questions.map((q,i)=><fieldset key={q.id}><legend><span className="question-number">{String(i+1).padStart(2,'0')}</span>{q.text}</legend><div className="scale">{scale.map((label,index)=><label className={answers[q.id]===index+1?'option selected':'option'} key={label}><input type="radio" name={q.id} value={index+1} required checked={answers[q.id]===index+1} onChange={()=>setAnswers({...answers,[q.id]:index+1})}/><span className="option-number">{index+1}</span><span>{label}</span></label>)}</div></fieldset>)}</div><div className="actions"><button type="button" className="secondary bg-transparent" disabled={busy} onClick={()=>setStarted(false)}>참여 정보 수정</button><button disabled={busy}>{busy?'저장 중…':'결과 확인'}</button></div></>}
  </form>}
  <footer>로컬 개발용 진단 · 실제 학생 데이터 및 외부 공개 운영에 사용하지 마세요.</footer>
 </main>
}
