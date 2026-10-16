# Audit Log Pattern

visibility: internal_only

## Log Actions

- LOGIN_SUCCESS / LOGIN_FAILED
- VIEW_RESULT
- EXPORT_CSV
- RESET_SUBMISSION
- UPDATE_QUESTION
- UPDATE_SCORING
- OPEN_SESSION / CLOSE_SESSION

## Fields

actor_id, action, target_type, target_id, timestamp, ip_hash(optional), user_agent_hash(optional), details(redacted)

## Rules

- 비밀/토큰/원시 개인정보를 details에 넣지 않는다.
- CSV 다운로드와 개인정보 조회는 반드시 기록한다.
