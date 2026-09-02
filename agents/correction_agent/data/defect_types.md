# 용접 결함 유형 코드 정의

> **문서 성격** 사내 결함 판정 코드표. 강관 원주 용접 / RT(방사선) 영상 판독 기준.
> **출처** `vectordb/결함 유형.csv` (2026-08-19 수신) 를 그대로 옮긴 것.
> **범위** 결함 15종의 **코드 · 명칭 · 정의 · 위치 · 형상 특징**.
> **한계** 허용 한계(치수·등급)는 이 문서에 없다. **합격/불합격 판정 근거로 쓸 수 없다.**
> **원본에서 제외한 항목** CSV의 `비고4`(다른 코드로 판정되는 경우) 는 요청에 따라 적재 대상에서 제외했다.

---

## 0. 요약표

| 코드 | 영문명 | 한글명 | 위치 | 정의 |
| --- | --- | --- | --- | --- |
| **SD** | Surface Defect | 표면 결함 | 표면 | 판정 범위 내의 표면의 물리적 손상 (찍힘, 긁힘 등) |
| **CT** | Contamination | 이물질 | 표면 | 강관 내부에 이물질이 잔존 |
| **LF** | Lack of Fusion | 융합부족 | 내부 | 내면 용접과 외면 용접 간의 융합 부족 |
| **IP** | Incomplete Penetration | 용입부족 | 내부 | 아크에 의한 모재부 불완전 용입 |
| **PO** | Porosity | 기공 | 내부 | 용접부 내에 잔존한 기체 |
| **SI** | Slag Inclusion | 슬래그혼입 | 내부 | 용접부 내에 잔존한 플럭스 또는 불순물 |
| **BT** | Burn Through | 용락 | 내부 | 용접열에 의해 완전히 모재가 용융 |
| **CR** | Crack | 균열 | 내부 | 금속학적인 파단 |
| **UC** | Under-Cut | 언더컷 | 표면 | 아크열에 의한 모재 개선부 표면 파임 또는 미용융 |
| **TI** | Tungsten Inclusion | 텅스텐혼입 | 내부 | TIG 용접에만 적용 |
| **PM** | Pork Mark | 포크마크 | 표면 | 용접부 표면과 슬래그 사이에 갇힌 기체에 의한 용접부 표면 손상 |
| **RC** | Root Concavity | 루트부오목 | 내부 | 한쪽 용접인 경우 (강관은 양쪽 용접 임) |
| **SP** | Spatter | 스패터 | 표면 | (원본에 정의 없음) |
| **OL** | Over lap | 오버랩 | 표면 | 과대한 용접 비드(비드 높이 허용 기준 초과) / 용접 재시작부 |
| **UF** | Underfill | 언더필 | 내부 | 과소한 용접 비드 (모재 높이 이하) |

**위치별 분포** — 표면 6종(SD·CT·UC·PM·SP·OL) / 내부 9종(LF·IP·PO·SI·BT·CR·TI·RC·UF)

---

## 1. 결함별 상세

> 각 항목이 VectorDB 청크 1개가 된다. `검색 동의어` 는 원본 CSV에 없는 **검색 보조용 필드**로,
> 현장 표현·영문 이형·약어로 물었을 때도 찾히게 하려고 덧붙였다. 판정 근거로 인용하지 않는다.

## SD — Surface Defect (표면 결함)

- 코드: SD
- 영문명: Surface Defect
- 한글명: 표면 결함
- 위치: 표면
- 정의: 판정 범위 내의 표면의 물리적 손상 (찍힘, 긁힘 등)
- 형상 특징: 다양한 형상, 두께 감소 또는 증가
- 검색 동의어: 표면손상, 찍힘, 긁힘, 스크래치, surface damage, scratch, dent

## CT — Contamination (이물질)

- 코드: CT
- 영문명: Contamination
- 한글명: 이물질
- 위치: 표면
- 정의: 강관 내부에 이물질이 잔존
- 형상 특징: 다양한 형상
- 검색 동의어: 이물질, 잔존물, 오염, contamination, foreign material, debris

## LF — Lack of Fusion (융합부족)

- 코드: LF
- 영문명: Lack of Fusion
- 한글명: 융합부족
- 위치: 내부
- 정의: 내면 용접과 외면 용접 간의 융합 부족
- 형상 특징: 용접부 중심, 강관 길이 방향 선형
- 검색 동의어: 융합불량, 융착불량, 미융합, lack of fusion, incomplete fusion, LOF

## IP — Incomplete Penetration (용입부족)

- 코드: IP
- 영문명: Incomplete Penetration
- 한글명: 용입부족
- 위치: 내부
- 정의: 아크에 의한 모재부 불완전 용입
- 형상 특징: 개선부, 강관 길이 방향 선형
- 검색 동의어: 용입불량, 불완전 용입, incomplete penetration, lack of penetration, LOP

## PO — Porosity (기공)

- 코드: PO
- 영문명: Porosity
- 한글명: 기공
- 위치: 내부
- 정의: 용접부 내에 잔존한 기체
- 형상 특징: 대부분 용접부 중심, 구형
- 검색 동의어: 기공, 공동, 블로홀, 가스공, porosity, gas pore, blowhole, void

## SI — Slag Inclusion (슬래그혼입)

- 코드: SI
- 영문명: Slag Inclusion
- 한글명: 슬래그혼입
- 위치: 내부
- 정의: 용접부 내에 잔존한 플럭스 또는 불순물
- 형상 특징: 대부분 용접부 중심, 강관 길이 방향 긴 구형
- 검색 동의어: 슬래그, 개재물, 혼입, 불순물, slag inclusion, slag, flux

## BT — Burn Through (용락)

- 코드: BT
- 영문명: Burn Through
- 한글명: 용락
- 위치: 내부
- 정의: 용접열에 의해 완전히 모재가 용융
- 형상 특징: 용접부
- 검색 동의어: 용락, 번스루, 관통, burn through, melt through

## CR — Crack (균열)

- 코드: CR
- 영문명: Crack
- 한글명: 균열
- 위치: 내부
- 정의: 금속학적인 파단
- 형상 특징: 용접부 중심 또는 개선부, 강관 길이 방향 선형 (단, 저온 균열은 강관 길이 방향의 수직일 수 있음)
- 검색 동의어: 균열, 크랙, 갈라짐, 저온균열, crack, cold crack, fissure

## UC — Under-Cut (언더컷)

- 코드: UC
- 영문명: Under-Cut
- 한글명: 언더컷
- 위치: 표면
- 정의: 아크열에 의한 모재 개선부 표면 파임 또는 미용융
- 형상 특징: 표면 개선부, 강관 길이 방향 긴 반구형
- 검색 동의어: 언더컷, 비드 가장자리 파임, 가장자리 파임, undercut, under cut

## TI — Tungsten Inclusion (텅스텐혼입)

- 코드: TI
- 영문명: Tungsten Inclusion
- 한글명: 텅스텐혼입
- 위치: 내부
- 정의: TIG 용접에만 적용
- 형상 특징: 대부분 용접부 중심, 대부분 구형
- 검색 동의어: 텅스텐 혼입, 텅스텐 개재물, tungsten inclusion, TIG, GTAW

## PM — Pork Mark (포크마크)

- 코드: PM
- 영문명: Pork Mark
- 한글명: 포크마크
- 위치: 표면
- 정의: 용접부 표면과 슬래그 사이에 갇힌 기체에 의한 용접부 표면 손상
- 형상 특징: 용접부, 불완전 구형
- 검색 동의어: 포크마크, 표면 기공 자국, pork mark, pockmark

## RC — Root Concavity (루트부오목)

- 코드: RC
- 영문명: Root Concavity
- 한글명: 루트부오목
- 위치: 내부
- 정의: 한쪽 용접인 경우 (강관은 양쪽 용접 임)
- 형상 특징: 용접부 중심, 강관 길이 방향 긴 타원형
- 검색 동의어: 루트 오목, 이면 오목, 루트부 오목, root concavity, suck back

## SP — Spatter (스패터)

- 코드: SP
- 영문명: Spatter
- 한글명: 스패터
- 위치: 표면
- 정의: (원본 CSV에 정의 없음)
- 형상 특징: 모재부, 작은 구형
- 검색 동의어: 스패터, 용접 튐, 비산, spatter, weld spatter

## OL — Over lap (오버랩)

- 코드: OL
- 영문명: Over lap
- 한글명: 오버랩
- 위치: 표면
- 정의: 과대한 용접 비드(비드 높이 허용 기준 초과) / 용접 재시작부
- 형상 특징: 용접부
- 검색 동의어: 오버랩, 과대 비드, 겹침, overlap, over lap, excessive reinforcement

## UF — Underfill (언더필)

- 코드: UF
- 영문명: Underfill
- 한글명: 언더필
- 위치: 내부
- 정의: 과소한 용접 비드 (모재 높이 이하)
- 형상 특징: 용접부
- 검색 동의어: 언더필, 비드 부족, 충전 부족, underfill, under fill

---

## 2. VectorDB 적재 규칙

| 항목 | 값 |
| --- | --- |
| 컬렉션 | `standards` (기존과 동일 — 문서는 `doc_id` 로 구분) |
| `doc_id` | `defect-types` |
| 청킹 단위 | **결함 1종 = 청크 1개** (총 15청크) |
| `chunk_type` | `defect_definition` |
| `citation_path` | `결함유형표 § UC` 형식 |
| `parent_id` | `defect-types#표면` / `defect-types#내부` — 위치별 묶음 조회용 |
| `status` | `internal` (사내 문서. active/unverified 와 구분) |
| 임베딩 입력 | `passage: ` + 코드·영문명·한글명·정의·형상·동의어를 이은 문자열 |
| 제외 | CSV `비고4` |

> **왜 이 문서가 필요한가** — 기존 적재 3종(49 CFR 192 · MIL-STD-2035A · NASA-STD-5006A)에는
> **결함의 정의문이 없다.** 결함명은 조항 제목(`4.2.16 Undercut`)으로만 등장한다.
> 이 문서가 들어가면 "이 결함은 무엇인가" 계열 질문의 커버리지가 🟡 → ✅ 로 올라가고,
> 동시에 **자체 코드 체계(SD·CT·LF…)가 3개 외부 문서를 잇는 조인 키** 역할을 하게 된다.
