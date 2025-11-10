# 근무 스케줄 자동 생성 알고리즘

Google OR-Tools CP-SAT Solver를 사용한 근무 스케줄 자동 생성 시스템

## 🎯 주요 기능

- **제약 조건 기반 스케줄 생성**: OR-Tools를 활용한 최적화
- **사전 입력 유지**: 사용자가 미리 지정한 근무코드 보존
- **일일 인원 배정**: 오전 1명, 오후 2명 자동 배치
- **연속 근무 제한**: 오전/오후/총 연속 근무 일수 제한
- **연속 휴무 최적화**: 소프트 제약을 통한 휴무 연속성 고려
- **근무 균등 배분**: 근무자 간 공평한 근무 분배

## 📋 근무 코드

### 알고리즘이 할당하는 코드
- **Z**: 오전 근무
- **HC**: 오후 근무 (13시 출근)
- **IA**: 오후 근무 (14시 출근)
- **R**: 자동 휴무

### 사용자가 입력하는 코드 (알고리즘은 유지)
- **RQ**: 지정 휴무
- **ZT**: 오전 교육 (0.5명 카운트)
- **HCT**: 오후 교육 (0.5명 카운트)
- **IAT**: 오후 교육 (0.5명 카운트)
- **DT**: 종일 교육 (카운트 제외)

## 🚀 설치 및 실행

### 1. 의존성 설치

```bash
cd schdule-generator-algorithm
pip install -r requirements.txt
```

### 2. 테스트 실행

```bash
# 기본 테스트 (test_input.json 사용)
python main.py

# 특정 JSON 파일로 테스트
python main.py input.json
```

### 3. API 서버 모드

```bash
python main.py server
```

서버 시작 후:
- **Endpoint**: `http://localhost:5000/generate`
- **Method**: POST
- **Health Check**: `http://localhost:5000/health`

## 📊 입력 데이터 형식

```json
{
  "schedule": [
    {
      "name": "김철수",
      "days": ["RQ", "", "", "HCT", "HCT", "", ...]
    }
  ],
  "option": {
    "dayOff": "all",
    "dayOffValue": 8,
    "dayOffIndividual": {},
    "dayOffStream": "on",
    "workCodeAverage": "on",
    "continuousWorkLimit": {
      "am": 4,
      "pm": 4,
      "total": 6
    },
    "targetMonth": "2025-06"
  }
}
```

### 옵션 설명

#### `dayOff` + `dayOffValue` + `dayOffIndividual`
- `dayOff: "all"`: 모든 근무자 동일 휴무 일수
- `dayOff: "individual"`: 근무자별 다른 휴무 일수
- `dayOffValue`: 전체 적용 휴무 일수
- `dayOffIndividual`: 개인별 휴무 일수 `{"이름": 일수}`

#### `dayOffStream`
- `"on"`: 연속 휴무 우선 배치 (소프트 제약)
- `"off"`: 연속 휴무 고려 안 함

#### `workCodeAverage`
- `"on"`: 근무 코드 균등 배분 (소프트 제약)
- `"off"`: 균등 배분 고려 안 함

#### `continuousWorkLimit`
- `am`: 오전 근무 최대 연속 일수
- `pm`: 오후 근무 최대 연속 일수
- `total`: 전체 근무 최대 연속 일수

#### `targetMonth`
- 형식: `"YYYY-MM"`
- 예: `"2025-06"`

## 🔧 제약 조건

### 하드 제약 (반드시 충족)

1. **사전 입력 유지**: 빈 칸(`""`)만 알고리즘이 채움
2. **일일 인원**: 매일 오전 1명, 오후 2명 배정
3. **RQ 전후 제한**: RQ 전날/다음날 R 할당 불가
4. **오후→오전 금지**: 오후 근무 다음날 오전 근무 불가
5. **휴무 일수**: 각 근무자 지정된 휴무 일수 충족
6. **연속 근무 제한**: 설정된 연속 근무 일수 초과 불가

### 소프트 제약 (가능하면 충족)

1. **연속 휴무**: `dayOffStream: "on"` 시 휴무 연속 배치 선호
2. **근무 균등**: `workCodeAverage: "on"` 시 근무 균등 분배

## 📤 출력 데이터 형식

```json
{
  "status": "success",
  "schedule": [
    {
      "name": "김철수",
      "days": ["RQ", "HC", "IA", "HCT", "HCT", "Z", ...]
    }
  ]
}
```

실패 시:
```json
{
  "status": "error",
  "message": "스케줄을 생성할 수 없습니다. 제약 조건을 확인해주세요."
}
```

## 🏗️ 아키텍처

```
React 프론트엔드 (schedule-generator-front)
         ↓ HTTP POST
Node.js API (schedule-generator) [port 8000]
         ↓ HTTP POST
Python 알고리즘 (schdule-generator-algorithm) [port 5000]
         ↓
OR-Tools CP-SAT Solver
```

## 📝 예시

`test_input.json` 파일을 참고하세요.

## ⚠️ 문제 해결

### 스케줄 생성 실패 시

1. **제약 조건 충돌 확인**
   - RQ 개수가 너무 많은지
   - 연속 근무 제한이 너무 엄격한지
   - 휴무 일수가 현실적인지

2. **사전 입력 확인**
   - 이미 입력된 코드가 조건 2를 위반하는지 (일일 인원)
   - 오후 다음날 오전이 사전 입력되어 있는지

3. **타임아웃 조정**
   - `schedule_generator.py`의 `max_time_in_seconds` 증가

## 🛠️ 개발 환경

- Python 3.8+
- OR-Tools 9.7+
- Flask 3.0+

## 📄 라이선스

ISC
