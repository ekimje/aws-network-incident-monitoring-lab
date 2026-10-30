# AWS 네트워크·방화벽 장애 관제 프로젝트 계획서

## 프로젝트 개요

AWS에 **실시간 시세 수집·조회 서비스**를 3계층(웹·앱, DB, 모니터링)으로 Terraform을 써서 구축하고, 방화벽(SG·NACL) 장애와 앱 장애를 Prometheus·Grafana로 감지하고 원인을 좁혀 복구하는 실습 프로젝트다.

- **목적**: 서버관제·클라우드 운영 직무 지원용 포트폴리오. "발생 → 감지 → 원인 확인 → 복구 → 재발 방지" 흐름을 직접 재현하고 문서로 남긴다.
- **배경**: 이전 Terraform 실습과 Prometheus·Grafana 모니터링 실습을 복습하면서, 네트워크 분리와 계층별 방화벽을 새로 추가한다.
- **핵심 포인트**: 외부와 내부 두 지점에서 헬스체크해서 "앱 문제인지, 네트워크·방화벽 문제인지"를 그래프로 구분한다.
- **자동화 경계**: 인프라(네트워크·방화벽)는 Terraform, 서버 안(설치·설정·장애 조치)은 Ansible이 맡는다.
- **데이터 소스**: 업비트 Quotation API(코인 시세). 키 없이 쓸 수 있고 24시간 시세가 움직여서 평일 저녁·주말 언제 테스트해도 데이터가 바뀐다. 갱신이 멈추면 시간대와 상관없이 장애로 본다. 코인은 데이터 소스일 뿐이고, 보여주고 싶은 것은 인프라와 관제다.
- **저장소**: [ekimje/aws-network-incident-monitoring-lab](https://github.com/ekimje/aws-network-incident-monitoring-lab)

## 목표와 범위

방화벽 장애 시나리오 2개를 재현하고 문서화하는 것까지를 1차 완성본으로 잡고, 나머지는 2차 확장으로 둔다.

**1차 최소 완성본**

- [ ] Terraform으로 VPC, 서브넷 2개(public/private), EC2 3대, 계층별 SG 구성
- [ ] Ansible 플레이북으로 서버 3대 구성 (Docker, 앱, PostgreSQL, node\_exporter, 모니터링 스택)
- [ ] 앱(시세 수집기 + 조회 웹) 배포 후 시세 저장, `/health`, `/metrics` 동작 확인
- [ ] Prometheus + node\_exporter + blackbox\_exporter + Grafana 대시보드 1개
- [ ] Alertmanager 알림 2개 이상 (서비스 다운, 5xx 증가, 시세 갱신 중단)
- [ ] 장애 시나리오 2개(웹 SG 차단, 앱→DB 차단) 재현, 스크린샷, README 정리

**2차 확장**

- [ ] NACL 장애 시나리오 + VPC Flow Logs로 REJECT 확인
- [ ] Loki + Promtail로 앱 에러 로그 수집
- [ ] 부하 테스트(k6), 컨테이너·DB 중지, 디스크 풀 시나리오
- [ ] 외부 API 경로 차단(SG 아웃바운드), 업비트 요청 제한 초과 시나리오
- [ ] Ansible 런북 플레이북(앱·DB 재시작, 디스크 정리): 알림을 보고 사람이 원인을 확인한 뒤 실행 (반자동)
- [ ] (아이디어) 주식 시세 API를 두 번째 소스로 추가하고, 장 운영 시간에 맞춰 소스별 알림 시간대 분리

**3차 (시간이 남으면)**

- [ ] 장애 자동 해결: 장애 알림 → Ansible 자동 조치 → 조치 결과 알림 → 해결 알림 (Discord)

범위 밖: 멀티 AZ·ALB·Auto Scaling 같은 고가용성 구성, HTTPS·도메인, CI/CD, 쿠버네티스.

## 아키텍처

VPC 하나에 public·private 서브넷을 두고, 웹·앱, DB, 모니터링 EC2 3대를 계층별 SG로 분리한다.

```mermaid
flowchart LR
    user[사용자] --> inet((인터넷))
    inet -->|80, 퍼블릭 IP| web
    subgraph VPC
        subgraph public[public 서브넷]
            web[웹·앱 EC2<br/>Nginx + FastAPI]
            mon[모니터링 EC2<br/>Prometheus · Grafana · Alertmanager]
        end
        subgraph private[private 서브넷]
            db[(DB EC2<br/>PostgreSQL)]
        end
    end
    web -->|5432| db
    web -->|시세 요청 HTTPS 443| upbit[업비트 Quotation API]
    pc[내 PC · WSL<br/>Terraform · Ansible] -.->|SSH 22| web
    web -.->|SSH 점프| db
    mon -.->|내부 HTTP 80| web
    mon -.->|DB TCP 5432| db
    mon -.->|외부 HTTP 체크| inet
    mon -->|웹훅| discord[Discord]
```

외부 체크는 퍼블릭 IP로 인터넷을 거쳐 들어오므로 웹 SG의 0.0.0.0/0 규칙이 막히면 실패하고, 내부 체크는 모니터링 SG 규칙으로 들어오므로 그대로 성공한다. 이 차이로 방화벽 문제와 앱 문제를 구분한다.

**SG 규칙 (인바운드)**

| SG | 포트 | 출처 | 용도 |
| --- | --- | --- | --- |
| 웹·앱 SG | 80 | 0.0.0.0/0 | 사용자·외부 체크 |
| 웹·앱 SG | 80, 8000, 9100 | 모니터링 SG | 내부 체크, 앱 메트릭, node\_exporter |
| 웹·앱 SG | 22 | 내 IP | SSH 관리 |
| DB SG | 5432 | 웹·앱 SG | 앱의 DB 접속 |
| DB SG | 5432, 9100 | 모니터링 SG | DB 체크, node\_exporter |
| DB SG | 22 | 웹·앱 SG | 점프 호스트 경유 SSH |
| 모니터링 SG | 3000 | 내 IP | Grafana 접속 |
| 모니터링 SG | 22 | 내 IP | SSH 관리 |

아웃바운드는 SG 기본값(전체 허용)을 쓰지 않고 Terraform에 명시한다. 웹·앱 SG는 업비트 API 호출용 443, DB 접속용 5432를 열고, 웹·앱 서버는 public 서브넷에 있어서 NAT 없이 인터넷으로 나간다.

Ansible은 내 IP에서 SSH(22)로 웹·앱·모니터링 서버에 접속하고, private 서브넷의 DB 서버에는 웹·앱 서버를 점프 호스트로 거쳐 들어간다(ProxyJump). 위 SG 규칙만으로 충분하다. 3차 자동 해결을 넣을 때만 "모니터링 SG → 웹·앱·DB SG 22" 규칙을 추가한다.

NACL은 처음에는 기본값(전체 허용)으로 두고, 2차 시나리오에서 규칙을 추가한다.

## 기술 스택

| 영역 | 사용 기술 | 비고 |
| --- | --- | --- |
| IaC | Terraform (AWS provider) | 기존 코드 복습, 모듈로 재구성 |
| 클라우드 | AWS VPC, EC2, Security Group, NACL | Flow Logs는 2차 |
| 앱 | Python FastAPI, PostgreSQL | 바이브 코딩, 코드 이해 정리 필수 |
| 데이터 소스 | 업비트 Quotation API | 키 불필요, 주식 API는 2차 아이디어 |
| 배포 | Docker, Docker Compose, Nginx | 컨테이너 `restart: unless-stopped` |
| 구성 관리 | Ansible | 서버 설치·설정, 런북. Windows에서는 WSL(Ubuntu)에서 실행 |
| 모니터링 | Prometheus, node\_exporter, blackbox\_exporter, Grafana | 모니터링 전용 EC2 |
| 알림 | Alertmanager → Discord 웹훅 | Slack이나 이메일도 가능 |
| 로그 (2차) | Loki, Promtail | 메모리 여유 보고 결정 |
| 테스트 | curl, k6 | 부하 테스트는 2차 |

## 구성 요소별 상세

### Terraform

- 모듈 분리: `network`(VPC, 서브넷, 라우팅, NACL), `security`(SG), `compute`(EC2)
- 네트워크 대역 (리전 `ap-northeast-2`, 가용 영역 `ap-northeast-2a` 하나)

  | 구분 | CIDR | 들어가는 서버 |
  | --- | --- | --- |
  | VPC | `10.0.0.0/16` | |
  | public 서브넷 | `10.0.1.0/24` | 웹·앱, 모니터링 |
  | private 서브넷 | `10.0.2.0/24` | DB |
- 내 IP, 인스턴스 타입, 키 이름은 변수로 관리하고 `terraform.tfvars`는 커밋하지 않음
- EC2 `user_data`는 쓰지 않는다. 서버 안 설치·설정은 Ansible이 맡는다
- `outputs`로 각 서버 IP 출력 → Ansible 인벤토리에 사용. `terraform apply` + `ansible-playbook` 두 줄로 전체 환경 재현

### Ansible

- **컨트롤 노드**: 내 PC의 WSL(Ubuntu). Ansible은 Windows에서 직접 실행되지 않는다
- **인벤토리**: Terraform output의 IP로 작성. DB 서버는 웹·앱 서버를 거치는 ProxyJump 설정
- **구성 플레이북** `site.yml`: 역할(role)별로 나눈다 — `docker`, `app`(Compose + Nginx), `postgresql`, `node_exporter`, `monitoring`(Prometheus·blackbox·Grafana·Alertmanager)
- **멱등성**: 여러 번 실행해도 결과가 같게 작성한다. 설치가 중간에 실패하면 서버를 다시 만들지 않고 플레이북만 다시 실행한다
- **런북 플레이북 (2차)**: `restart-app.yml`, `restart-db.yml`, `cleanup-disk.yml`. 알림 메시지(`annotations.runbook`)에 실행할 플레이북 이름을 적어 둔다
- **기본 자동 복구**: 프로세스가 죽는 장애는 Docker `restart: unless-stopped`가 먼저 처리한다. Ansible은 그걸로 안 되는 경우를 맡는다

### 앱 (실시간 시세 수집·조회 서비스)

- **수집기**: 업비트 Quotation API에서 몇 개 종목(KRW-BTC, KRW-ETH 등) 현재가를 몇 초마다 받아 DB에 저장. FastAPI 프로세스 안의 백그라운드 작업으로 돌려서 메트릭을 같은 `/metrics`로 내보낸다 (포트·SG 규칙 추가 없음)
- **웹**: 종목별 최신 시세와 간단한 차트
- **엔드포인트**: `GET /prices`(종목별 최신 시세), `GET /prices/{market}`(최근 시세 이력, 차트용), `/health`(DB 연결까지 확인, 실패 시 503), `/metrics`
- **메트릭**
  - 웹: 경로·상태코드별 요청 수, 응답시간 히스토그램, DB 연결 에러 수
  - 수집기: 수집 성공·실패 수, 업비트 API 응답시간, 마지막 갱신 시각, 남은 요청 수(응답 헤더 `Remaining-Req`), DB 저장 건수
- **데이터량 조절**: 종목 수와 수집 주기를 환경변수로 두어 트래픽과 DB 증가 속도를 조절 (부하·디스크 시나리오 연출용)
- Nginx가 80포트로 받아 앱 컨테이너로 전달
- 바이브 코딩으로 만들되, 각 파일 역할과 주요 코드를 README에 직접 설명할 수 있게 정리

### 모니터링

- Prometheus 수집 대상: node\_exporter(3대), 앱 `/metrics`, blackbox\_exporter
- blackbox 체크 3종: 외부 HTTP(웹 서버 퍼블릭 IP), 내부 HTTP(웹 서버 사설 IP), DB TCP 5432
- Grafana 대시보드 패널: 외부·내부·DB 체크 성공 여부, 5xx 비율, p95 응답시간, 수집 성공률, 마지막 갱신 후 경과 시간, 업비트 API 응답시간, CPU·메모리·디스크

### 알림 규칙

| 알림 | 조건 | 의미 |
| --- | --- | --- |
| ServiceDownExternal | 외부 HTTP 체크 실패 1분 지속 | 사용자 입장에서 접속 불가 |
| ServiceDownInternal | 내부 HTTP 체크 실패 1분 지속 | 앱이나 서버 자체 문제 |
| DBUnreachable | DB TCP 체크 실패 1분 지속 | DB 서버나 DB 포트 문제 |
| High5xxRate | 5xx 비율 5% 이상 2분 지속 | 앱 내부 오류, DB 연결 실패 등 |
| PriceDataStale | 마지막 갱신 후 1분 이상 지남 | 수집 중단 (외부 API 경로, 업비트 장애, DB 저장 실패 등) |
| CollectorErrors (2차) | 수집 실패율 50% 이상 2분 지속 | 업비트 API 오류·요청 제한 초과 |

Alertmanager는 `send_resolved: true`로 두어 장애가 풀리면 해결 알림도 Discord로 보낸다.

### 장애 자동 해결 (3차, 시간이 남으면)

```mermaid
flowchart LR
    am[Alertmanager] -->|장애 알림| discord[Discord]
    am -->|웹훅| hook[웹훅 수신 서버<br/>모니터링 EC2]
    hook -->|허용된 알림만| ansible[Ansible 런북 실행]
    ansible -->|조치 결과| discord
    am -->|해결 알림 send_resolved| discord
```

- **대상**: 원인과 조치가 정해진 장애만 — 앱 컨테이너 다운, DB 다운, 디스크 풀
- **제외**: SG·NACL 장애. 원인 판단이 프로젝트의 핵심이고, 방화벽은 Terraform이 관리하는 영역이라 Ansible로 고치면 drift가 생긴다
- **안전장치**: 허용 목록(알림 이름), 같은 알림은 10분에 1번만 실행, 조치 후에도 안 풀리면 사람에게 넘김
- **필요한 변경**: 모니터링 서버에 Ansible 설치, 모니터링 SG → 웹·앱·DB SG 22 규칙 추가
| DiskAlmostFull (2차) | 디스크 사용률 90% 이상 | 디스크 풀 위험 |

### VPC Flow Logs (2차)

- public 서브넷 Flow Logs를 CloudWatch Logs로 보내 방화벽에 막힌 트래픽(`REJECT`)을 원인 확인 증거로 사용

## 장애 시나리오

1차는 1·2번만 완성하고, 시나리오마다 "발생 → 감지 → 원인 확인 → 복구 → 재발 방지"를 스크린샷과 함께 README에 남긴다.

| # | 시나리오 | 발생 방법 | 감지 신호 | 원인 확인 | 복구 | 단계 |
| --- | --- | --- | --- | --- | --- | --- |
| 1 | 웹 SG 80포트 차단 | 웹 SG에서 0.0.0.0/0 인바운드 80 규칙 삭제 | 외부 체크 실패, 내부 체크 정상 | 앱은 정상 → 외부 경로 문제 → SG 규칙 확인 | `terraform apply`로 원래 규칙 복구 (drift 확인) | 1차 |
| 2 | 앱→DB 경로 차단 | DB SG에서 앱 SG 출처의 5432 규칙 삭제 | `/health` 503, 5xx 급증, 시세 갱신 중단, DB TCP 체크는 정상 | DB는 살아 있음 → 앱↔DB 사이 방화벽 문제 | `terraform apply`로 복구 | 1차 |
| 3 | 앱 프로세스 강제 종료 | `docker compose exec app kill 1` | 외부·내부 체크가 잠깐 실패 후 회복, node\_exporter 정상 | `docker ps`의 STATUS(Up 몇 초), 로그로 재시작 흔적 확인 | restart 정책으로 자동 복구 확인, 반복되면 런북 `restart-app.yml` | 2차 |
| 4 | DB 중지 | DB 서비스 중지 | DB TCP 체크 실패, `/health` 503 | DB 서버 접속 후 서비스 상태 확인 | 런북 `restart-db.yml` | 2차 |
| 5 | NACL 아웃바운드 차단 | public 서브넷 NACL에서 아웃바운드 1024\~65535 거부 | 외부 체크 실패, SG는 정상 | SG만 봐서는 안 보임 → NACL이 stateless라 응답이 막힘 → Flow Logs `REJECT` | NACL 규칙 복구 | 2차 |
| 6 | 부하 증가 | k6로 동시 요청 | p95 응답시간·CPU 상승 | 대시보드에서 자원 사용률 확인 | 부하 중지, 인스턴스 크기 검토 | 2차 |
| 7 | 디스크 풀 | 큰 파일 생성(`fallocate`) | DiskAlmostFull 알림 | `df -h`, `du`로 원인 파일 확인 | 런북 `cleanup-disk.yml`, 로그 로테이션 설정 | 2차 |
| 8 | 외부 API 경로 차단 | 웹·앱 SG에서 아웃바운드 443 규칙 삭제 | PriceDataStale 알림, 수집 실패 증가, 외부·내부 체크와 `/health`는 정상 | 서비스는 살아 있음 → 나가는 길 문제 → 아웃바운드 SG 규칙 확인 | `terraform apply`로 복구 | 2차 |
| 9 | 업비트 요청 제한 초과 | 수집 주기를 아주 짧게, 종목 수를 늘림 | 남은 요청 수 0 근접, 429 응답 증가, CollectorErrors 알림 | 우리 쪽 장애가 아닌 외부 의존성 한도 문제 → 요청량 계산 | 주기·종목 수 조정, 재시도 백오프 추가 | 2차 |

## 단계별 일정

평일 저녁과 주말 기준으로 약 3주 안에 1차 완성본을 끝내고, 그 뒤에 2차 확장을 붙인다.

1. **1주차 — 인프라와 앱 뼈대**
   - 아키텍처·SG 규칙 확정, Terraform으로 VPC·서브넷·EC2·SG 생성
   - 앱(시세 수집기 + 조회 웹) 바이브 코딩, 로컬에서 Docker Compose로 실행하고 시세 저장 확인
2. **2주차 — 배포와 모니터링**
   - WSL에 Ansible 설치, 플레이북으로 서버 3대 구성(앱 배포 포함), 외부 접속 확인
   - Prometheus·blackbox·Grafana 구성, 대시보드 1개, 알림 2개
3. **3주차 — 장애 재현과 문서화 (1차 완성)**
   - 시나리오 1·2 재현, 알림 수신과 대시보드 스크린샷
   - README 1차 작성, repo public 전환
4. **4주차 이후 — 2차 확장**
   - NACL·Flow Logs, Loki, Ansible 런북, 나머지 시나리오를 하나씩 추가
5. **시간이 남으면 — 3차**
   - 웹훅 → Ansible 장애 자동 해결, 조치 결과 알림 (약 10~15시간)

시작일과 1차 완성 목표일은 아직 정하지 않았다.

## 비용 관리

작업할 때만 띄우고 끝나면 `terraform destroy`하는 것이 기본 원칙이다.

- **인스턴스**: 웹·앱과 DB는 t3.micro, 모니터링 서버는 메모리 여유를 위해 t3.small 검토
- **NAT Gateway 사용 안 함**: private DB 서버에 패키지 설치가 필요하면 그때만 잠깐 만들고 지우거나, 작은 NAT 인스턴스로 대체
- **퍼블릭 IPv4 최소화**: 웹 서버와 모니터링 서버 2개만 퍼블릭 IP 부여 (퍼블릭 IP에도 시간당 요금이 붙음)
- **로그 보존 기간**: Flow Logs·CloudWatch Logs는 보존 기간을 짧게 설정
- **예산 알림**: 시작 전에 AWS Budgets로 소액 월 예산 알림 설정
- **습관**: 작업 종료 시 `terraform destroy`, 다음 작업 때 `apply`로 재생성

## 산출물과 면접 활용

최종 산출물은 GitHub repo 하나이고, README가 장애 대응 보고서 역할을 한다.

**repo 구조 (안)**

```
├─ terraform/
│   ├─ modules/ (network, security, compute)
│   ├─ main.tf, variables.tf, outputs.tf
├─ ansible/
│   ├─ inventory.ini, site.yml
│   ├─ roles/ (docker, app, postgresql, node_exporter, monitoring)
│   └─ runbooks/ (restart-app.yml, restart-db.yml, cleanup-disk.yml)
├─ app/ (FastAPI 웹·수집기, Dockerfile, docker-compose.yml, nginx.conf)
├─ monitoring/ (prometheus.yml, alert rules, blackbox.yml, alertmanager.yml, grafana 대시보드 JSON)
├─ docs/
│   ├─ architecture.png
│   └─ incidents/ (시나리오별 보고서 + 스크린샷)
└─ README.md
```

**README 목차**

1. 프로젝트 개요와 아키텍처 그림
2. 실행 방법 (`terraform apply`부터 대시보드 접속까지)
3. 모니터링 구성과 대시보드 스크린샷
4. 장애 시나리오별 보고서: 발생 → 감지 → 원인 확인 → 복구 → 재발 방지
5. 배운 점과 개선할 점

**면접에서 쓸 포인트**

- 서비스는 "코인 앱"이 아니라 **실시간 시세 수집·조회 서비스**로 소개 (README·이력서 동일)
- 외부·내부 두 지점에서 체크해 "앱 문제 vs 네트워크 문제"를 구분한 설계 이유
- 데이터 갱신 지연(마지막 갱신 시각)을 따로 감시해 "서버는 살아 있는데 데이터가 멈춘" 장애까지 잡은 점
- SG(stateful)와 NACL(stateless)의 차이를 장애로 직접 확인한 경험
- 수동으로 바꾼 방화벽 규칙을 `terraform apply`로 되돌리며 IaC로 설정 drift를 복구한 경험
- Terraform(인프라)과 Ansible(서버 구성·장애 조치)의 역할을 나눈 이유, 방화벽 장애는 자동 해결에서 뺀 이유
- 프로세스 장애는 restart 정책 같은 플랫폼 기능으로 먼저 해결하고, 원인 판단이 필요한 장애는 런북으로 남긴 설계
- 앱은 AI 도움을 받아 만들었고, 인프라·모니터링·장애 대응은 직접 설계했다고 솔직하게 설명

## 리스크와 대응

| 리스크 | 대응 |
| --- | --- |
| 평일 수업으로 일정 지연 | 1차 범위만 먼저 끝내고 2차는 하나씩 추가 |
| 바이브 코딩 코드를 설명 못 함 | 앱 기능을 최소로 유지, 파일별 역할과 핵심 코드를 직접 주석·정리 |
| AWS 비용 초과 | 작업 후 destroy, NAT Gateway 미사용, Budgets 알림 |
| 모니터링 서버 메모리 부족 | t3.small 사용, 부족하면 Loki 제외 |
| SG 실수로 내 SSH 접속 끊김 | SSH는 내 IP만 허용하는 별도 규칙 유지, 필요하면 SSM Session Manager 사용 |
| 업비트 API 요청 제한·장애 | 종목 수·수집 주기를 작게 시작, `Remaining-Req` 모니터링, 업비트 쪽 장애는 내 서비스 장애와 구분해 기록 |
| 시세 데이터로 DB 용량 증가 | 오래된 시세는 주기적으로 삭제(예: 7일 보존), 디스크 사용률 대시보드 확인 |
| Ansible을 Windows에서 실행할 수 없음 | WSL(Ubuntu)에 설치해 컨트롤 노드로 사용 |
| 자동 조치가 장애를 숨기거나 무한 재시작 (3차) | 허용 목록·횟수 제한, 조치 결과를 Discord에 기록 |
| 키·웹훅 URL 유출 | `.gitignore`에 tfvars·키·`.env` 추가, Discord 웹훅 URL은 변수로 분리 |
