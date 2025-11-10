"""
근무 스케줄 자동 생성 알고리즘 (OR-Tools CP-SAT 사용)
"""

from ortools.sat.python import cp_model
from typing import List, Dict, Any
from datetime import datetime
import time


# 근무 코드 상수
class WorkCode:
    EMPTY = ""          # 빈 칸 (할당 필요)
    Z = "Z"             # 오전 근무
    HC = "HC"           # 오후 근무 (13시)
    IA = "IA"           # 오후 근무 (14시)
    R = "R"             # 자동 휴무
    RQ = "RQ"           # 사용자 지정 휴무
    ZT = "ZT"           # 오전 교육 (0.5명)
    HCT = "HCT"         # 오후 교육 (0.5명)
    IAT = "IAT"         # 오후 교육 (0.5명)
    DT = "DT"           # 종일 교육 (0명)


# 근무 타입 인덱스
class ShiftType:
    OFF = 0     # 휴무 (R)
    AM = 1      # 오전 (Z)
    PM_HC = 2   # 오후 (HC)
    PM_IA = 3   # 오후 (IA)


class ScheduleGenerator:
    def __init__(self, input_data: Dict[str, Any]):
        """
        Args:
            input_data: {
                "schedule": [{"name": str, "days": List[str]}],
                "option": {
                    "dayOff": "all" | "individual",
                    "dayOffValue": int,
                    "dayOffIndividual": Dict[str, int],
                    "dayOffStream": "on" | "off",
                    "workCodeAverage": "on" | "off",
                    "continuousWorkLimit": {"am": int, "pm": int, "total": int},
                    "targetMonth": "YYYY-MM"
                }
            }
        """
        self.input_data = input_data
        self.schedule_input = input_data["schedule"]
        self.option = input_data["option"]

        # 기본 정보
        self.members = [s["name"] for s in self.schedule_input]
        self.num_members = len(self.members)
        self.num_days = self._get_days_in_month()

        # 인원 축소 요일 (0=일요일, 1=월요일, ..., 6=토요일)
        self.reduced_staffing_days = self.option.get("reducedStaffingDays", [])

        # 모델 초기화
        self.model = cp_model.CpModel()
        self.shifts = {}  # (member_idx, day_idx, shift_type) -> BoolVar
        self.penalties = []  # 소프트 제약 페널티

    def _get_days_in_month(self) -> int:
        """대상 월의 일수 계산"""
        target_month = self.option["targetMonth"]  # "YYYY-MM"
        year, month = map(int, target_month.split("-"))

        if month == 12:
            next_month = datetime(year + 1, 1, 1)
        else:
            next_month = datetime(year, month + 1, 1)

        last_day = datetime(year, month, 1)
        days = (next_month - last_day).days
        return days

    def _get_day_of_week(self, day_index: int) -> int:
        """특정 날짜의 요일 계산 (0=월요일, 6=일요일 -> Python datetime 기준)

        Returns:
            0=월요일, 1=화요일, ..., 5=토요일, 6=일요일
        """
        target_month = self.option["targetMonth"]
        year, month = map(int, target_month.split("-"))
        date = datetime(year, month, day_index + 1)

        # datetime.weekday(): 0=월, 1=화, ..., 6=일
        # 우리 시스템: 0=일, 1=월, ..., 6=토
        # 변환: (weekday + 1) % 7
        weekday = date.weekday()
        return (weekday + 1) % 7

    def _create_variables(self):
        """결정 변수 생성"""
        # shifts[m][d][s] = 근무자 m이 d일에 s 타입 근무를 하는가? (0 or 1)
        for m in range(self.num_members):
            for d in range(self.num_days):
                for s in range(4):  # OFF(0), AM(1), PM_HC(2), PM_IA(3)
                    self.shifts[(m, d, s)] = self.model.NewBoolVar(f'shift_m{m}_d{d}_s{s}')

    def _add_basic_constraints(self):
        """기본 제약 조건"""
        # 각 근무자는 각 날짜에 정확히 하나의 시프트만 가능
        for m in range(self.num_members):
            for d in range(self.num_days):
                self.model.Add(sum(self.shifts[(m, d, s)] for s in range(4)) == 1)

    def _add_predefined_schedule_constraints(self):
        """조건 1: 사전 입력 근무코드 유지"""
        for m, member_schedule in enumerate(self.schedule_input):
            days = member_schedule["days"]

            for d, code in enumerate(days):
                if d >= self.num_days:
                    break

                if code == WorkCode.EMPTY:
                    continue  # 빈 칸은 알고리즘이 채움

                # 사전 입력된 코드는 고정
                # T 코드는 근무로 고정하지만, 일일 인원 계산 시 0.5명으로 처리
                if code in [WorkCode.RQ, WorkCode.R]:
                    # 휴무로 고정
                    self.model.Add(self.shifts[(m, d, ShiftType.OFF)] == 1)
                elif code in [WorkCode.Z, WorkCode.ZT]:
                    # 오전으로 고정
                    self.model.Add(self.shifts[(m, d, ShiftType.AM)] == 1)
                elif code in [WorkCode.HC, WorkCode.HCT]:
                    # 오후 HC로 고정
                    self.model.Add(self.shifts[(m, d, ShiftType.PM_HC)] == 1)
                elif code in [WorkCode.IA, WorkCode.IAT]:
                    # 오후 IA로 고정
                    self.model.Add(self.shifts[(m, d, ShiftType.PM_IA)] == 1)
                elif code == WorkCode.DT:
                    # DT는 휴무로 처리 (근무자 카운트 제외)
                    self.model.Add(self.shifts[(m, d, ShiftType.OFF)] == 1)

    def _add_daily_staffing_constraints(self):
        """조건 2: 일일 근무 인원 배정 (Z 1명, HC+IA 2명 또는 요일별 설정)"""
        for d in range(self.num_days):
            # 해당 날짜의 요일 확인
            day_of_week = self._get_day_of_week(d)

            # 인원 축소 요일인지 확인
            is_reduced_day = day_of_week in self.reduced_staffing_days

            # 사전 입력된 T 코드와 일반 코드 개수 세기
            zt_count = 0  # ZT 개수
            z_count = 0   # Z 개수
            hct_iat_count = 0  # HCT + IAT 개수
            hc_ia_count = 0    # HC + IA 개수

            for m, member_schedule in enumerate(self.schedule_input):
                if d >= len(member_schedule["days"]):
                    continue

                code = member_schedule["days"][d]

                if code == WorkCode.ZT:
                    zt_count += 1
                elif code == WorkCode.Z:
                    z_count += 1
                elif code in [WorkCode.HCT, WorkCode.IAT]:
                    hct_iat_count += 1
                elif code in [WorkCode.HC, WorkCode.IA]:
                    hc_ia_count += 1
                # DT는 0명으로 카운트

            # 오전 근무 인원 설정
            am_total = sum(self.shifts[(m, d, ShiftType.AM)] for m in range(self.num_members))

            if is_reduced_day:
                # 인원 축소 요일: 오전 1명
                # 실제 인원 * 2 = (Z + 알고리즘 Z) * 2 + ZT * 1 = 2
                if zt_count > 0:
                    self.model.Add((am_total - zt_count) * 2 + zt_count == 2)
                else:
                    self.model.Add(am_total == 1)
            else:
                # 일반 요일: 오전 1명
                if zt_count > 0:
                    self.model.Add((am_total - zt_count) * 2 + zt_count == 2)
                else:
                    self.model.Add(am_total == 1)

            # 오후 근무 인원 설정
            pm_total = sum(
                self.shifts[(m, d, ShiftType.PM_HC)] + self.shifts[(m, d, ShiftType.PM_IA)]
                for m in range(self.num_members)
            )

            if is_reduced_day:
                # 인원 축소 요일: 오후 1명
                # 실제 인원 * 2 = (HC + IA) * 2 + (HCT + IAT) * 1 = 2
                if hct_iat_count > 0:
                    self.model.Add((pm_total - hct_iat_count) * 2 + hct_iat_count == 2)
                else:
                    self.model.Add(pm_total == 1)
            else:
                # 일반 요일: 오후 2명
                # 실제 인원 * 2 = (HC + IA) * 2 + (HCT + IAT) * 1 = 4
                if hct_iat_count > 0:
                    self.model.Add((pm_total - hct_iat_count) * 2 + hct_iat_count == 4)
                else:
                    self.model.Add(pm_total == 2)

    def _add_dayoff_constraints(self):
        """휴무 일수 제약"""
        for m, member_schedule in enumerate(self.schedule_input):
            member_name = member_schedule["name"]

            # 개인별 휴무 일수 (individual 모드만 지원)
            target_dayoff = self.option["dayOffIndividual"].get(member_name, 0)

            # 전체 휴무(OFF) 개수 = target_dayoff
            # (사전 입력된 RQ, R, DT + 알고리즘이 할당하는 R 포함)
            off_count = sum(self.shifts[(m, d, ShiftType.OFF)] for d in range(self.num_days))
            self.model.Add(off_count == target_dayoff)

    def _add_rq_adjacent_constraints(self):
        """조건 3: RQ 전후 R 코드 할당 제한"""
        for m, member_schedule in enumerate(self.schedule_input):
            days = member_schedule["days"]

            for d in range(self.num_days):
                if d >= len(days):
                    continue

                if days[d] == WorkCode.RQ:
                    # RQ 전날: R 할당 불가
                    if d > 0 and days[d - 1] == WorkCode.EMPTY:
                        self.model.Add(self.shifts[(m, d - 1, ShiftType.OFF)] == 0)

                    # RQ 다음날: R 할당 불가
                    if d < self.num_days - 1 and (d + 1 >= len(days) or days[d + 1] == WorkCode.EMPTY):
                        self.model.Add(self.shifts[(m, d + 1, ShiftType.OFF)] == 0)

    def _add_pm_to_am_constraints(self):
        """조건 4: 오후 근무 다음날 오전 근무 금지"""
        for m in range(self.num_members):
            for d in range(self.num_days - 1):
                # d일 오후 근무 (HC 또는 IA)이고 d+1일 오전 근무(Z)이면 안 됨
                # PM[d] + AM[d+1] <= 1
                # 즉, 둘 다 1일 수 없음
                pm_today = self.shifts[(m, d, ShiftType.PM_HC)] + self.shifts[(m, d, ShiftType.PM_IA)]
                am_tomorrow = self.shifts[(m, d + 1, ShiftType.AM)]

                self.model.Add(pm_today + am_tomorrow <= 1)

    def _add_continuous_work_constraints(self):
        """연속 근무 제한"""
        am_limit = self.option["continuousWorkLimit"]["am"]
        pm_limit = self.option["continuousWorkLimit"]["pm"]
        total_limit = self.option["continuousWorkLimit"]["total"]

        for m in range(self.num_members):
            # 오전 연속 근무 제한
            for d in range(self.num_days - am_limit):
                am_sum = sum(self.shifts[(m, d + i, ShiftType.AM)] for i in range(am_limit + 1))
                self.model.Add(am_sum <= am_limit)

            # 오후 연속 근무 제한
            for d in range(self.num_days - pm_limit):
                pm_sum = sum(
                    self.shifts[(m, d + i, ShiftType.PM_HC)] + self.shifts[(m, d + i, ShiftType.PM_IA)]
                    for i in range(pm_limit + 1)
                )
                self.model.Add(pm_sum <= pm_limit)

            # 총 연속 근무 제한 (오전 + 오후)
            for d in range(self.num_days - total_limit):
                total_work = sum(
                    self.shifts[(m, d + i, ShiftType.AM)] +
                    self.shifts[(m, d + i, ShiftType.PM_HC)] +
                    self.shifts[(m, d + i, ShiftType.PM_IA)]
                    for i in range(total_limit + 1)
                )
                self.model.Add(total_work <= total_limit)

    def _add_soft_constraints(self):
        """소프트 제약 조건 (목적 함수에 반영)"""
        # 1. dayOffStream: 연속 휴무 선호
        if self.option["dayOffStream"] == "on":
            for m in range(self.num_members):
                for d in range(self.num_days - 1):
                    # 연속 휴무에 보너스
                    consecutive_off = self.model.NewBoolVar(f'consecutive_off_m{m}_d{d}')
                    self.model.Add(
                        self.shifts[(m, d, ShiftType.OFF)] + self.shifts[(m, d + 1, ShiftType.OFF)] == 2
                    ).OnlyEnforceIf(consecutive_off)
                    self.model.Add(
                        self.shifts[(m, d, ShiftType.OFF)] + self.shifts[(m, d + 1, ShiftType.OFF)] < 2
                    ).OnlyEnforceIf(consecutive_off.Not())

                    # 페널티 리스트에 추가 (음수 = 보너스)
                    self.penalties.append((-5, consecutive_off))

        # 2. workCodeAverage: 근무 코드 균등 배분
        if self.option["workCodeAverage"] == "on":
            # 각 근무자의 Z, HC, IA 개수를 계산
            # 평균과의 차이를 최소화

            # 전체 Z, PM 개수
            total_am = sum(
                self.shifts[(m, d, ShiftType.AM)]
                for m in range(self.num_members)
                for d in range(self.num_days)
            )

            total_pm = sum(
                self.shifts[(m, d, ShiftType.PM_HC)] + self.shifts[(m, d, ShiftType.PM_IA)]
                for m in range(self.num_members)
                for d in range(self.num_days)
            )

            # 각 근무자의 근무 개수 차이를 페널티로
            for m in range(self.num_members):
                am_count = sum(self.shifts[(m, d, ShiftType.AM)] for d in range(self.num_days))
                pm_count = sum(
                    self.shifts[(m, d, ShiftType.PM_HC)] + self.shifts[(m, d, ShiftType.PM_IA)]
                    for d in range(self.num_days)
                )

                # 평균과의 차이를 변수로
                # (간단히 하기 위해 전체 균등성을 목표로 함)
                # 이 부분은 복잡도를 위해 간소화
                pass

    def _set_objective(self):
        """목적 함수 설정"""
        if not self.penalties:
            return

        # 페널티 합 최소화
        penalty_sum = sum(weight * var for weight, var in self.penalties)
        self.model.Minimize(penalty_sum)

    def generate(self, num_solutions: int = 1) -> Dict[str, Any]:
        """스케줄 생성

        Args:
            num_solutions: 생성할 스케줄 개수 (기본값: 1)

        Returns:
            num_solutions == 1: 단일 스케줄
            num_solutions > 1: {"status": "success", "schedules": [스케줄1, 스케줄2, ...]}
        """
        # 1. 변수 생성
        self._create_variables()

        # 2. 제약 조건 추가
        print("[DEBUG] Adding basic constraints...")
        self._add_basic_constraints()

        print("[DEBUG] Adding predefined schedule constraints...")
        self._add_predefined_schedule_constraints()

        print("[DEBUG] Adding daily staffing constraints...")
        self._add_daily_staffing_constraints()

        print("[DEBUG] Adding dayoff constraints...")
        self._add_dayoff_constraints()

        print("[DEBUG] Adding RQ adjacent constraints...")
        self._add_rq_adjacent_constraints()

        print("[DEBUG] Adding PM to AM constraints...")
        self._add_pm_to_am_constraints()

        print("[DEBUG] Adding continuous work constraints...")
        self._add_continuous_work_constraints()

        # 3. 소프트 제약 추가
        print("[DEBUG] Adding soft constraints...")
        self._add_soft_constraints()

        # 4. 목적 함수 설정
        print("[DEBUG] Setting objective...")
        self._set_objective()

        # 5. 여러 개의 해 찾기
        if num_solutions == 1:
            return self._solve_single()
        else:
            return self._solve_multiple(num_solutions)

    def _solve_single(self) -> Dict[str, Any]:
        """단일 스케줄 생성"""
        solver = cp_model.CpSolver()
        solver.parameters.max_time_in_seconds = 60.0
        solver.parameters.log_search_progress = True
        status = solver.Solve(self.model)

        if status == cp_model.OPTIMAL:
            print(f"[INFO] Optimal solution found")
            return self._extract_solution(solver)
        elif status == cp_model.FEASIBLE:
            print(f"[INFO] Feasible solution found")
            return self._extract_solution(solver)
        elif status == cp_model.INFEASIBLE:
            return {
                "status": "error",
                "message": "제약 조건을 만족하는 스케줄이 존재하지 않습니다. (INFEASIBLE)"
            }
        elif status == cp_model.MODEL_INVALID:
            return {
                "status": "error",
                "message": "모델이 유효하지 않습니다. (MODEL_INVALID)"
            }
        else:
            return {
                "status": "error",
                "message": f"스케줄을 생성할 수 없습니다. Status: {status}"
            }

    def _solve_multiple(self, num_solutions: int, max_total_time: float = 10.0) -> Dict[str, Any]:
        """여러 개의 다른 스케줄 생성

        Args:
            num_solutions: 생성할 스케줄 목표 개수
            max_total_time: 최대 탐색 시간 (초) - 기본값 10초
        """
        schedules = []
        start_time = time.time()

        print(f"[INFO] Generating up to {num_solutions} schedules within {max_total_time} seconds...")

        for i in range(num_solutions):
            # 경과 시간 체크
            elapsed_time = time.time() - start_time
            remaining_time = max_total_time - elapsed_time

            if remaining_time <= 0:
                print(f"[INFO] Time limit reached ({max_total_time}s). Stopping with {len(schedules)} schedules.")
                break

            solver = cp_model.CpSolver()
            # 남은 시간만큼만 탐색
            solver.parameters.max_time_in_seconds = min(remaining_time, 5.0)
            solver.parameters.random_seed = i  # 랜덤 시드 변경으로 다른 해 찾기
            solver.parameters.log_search_progress = False  # 로그 비활성화

            status = solver.Solve(self.model)

            if status == cp_model.OPTIMAL or status == cp_model.FEASIBLE:
                solution = self._extract_solution(solver)
                if solution["status"] == "success":
                    schedules.append(solution["schedule"])
                    elapsed = time.time() - start_time
                    print(f"[INFO] Schedule {len(schedules)}/{num_solutions} generated (elapsed: {elapsed:.2f}s)")
            else:
                print(f"[WARN] Failed to generate schedule {i+1}/{num_solutions} (status: {solver.StatusName(status)})")

        total_elapsed = time.time() - start_time

        if len(schedules) == 0:
            return {
                "status": "error",
                "message": f"스케줄을 생성할 수 없습니다. (탐색 시간: {total_elapsed:.2f}초)"
            }

        print(f"[INFO] Successfully generated {len(schedules)} schedules in {total_elapsed:.2f}s")
        return {
            "status": "success",
            "schedules": schedules,
            "count": len(schedules),
            "elapsed_time": round(total_elapsed, 2)
        }

    def _extract_solution(self, solver: cp_model.CpSolver) -> Dict[str, Any]:
        """해 추출"""
        result_schedule = []

        for m, member_schedule in enumerate(self.schedule_input):
            member_name = member_schedule["name"]
            days = []

            for d in range(self.num_days):
                # 사전 입력된 값 먼저 체크
                if d < len(member_schedule["days"]) and member_schedule["days"][d] != WorkCode.EMPTY:
                    days.append(member_schedule["days"][d])
                    continue

                # 알고리즘 결과 추출
                if solver.Value(self.shifts[(m, d, ShiftType.OFF)]) == 1:
                    days.append(WorkCode.R)
                elif solver.Value(self.shifts[(m, d, ShiftType.AM)]) == 1:
                    days.append(WorkCode.Z)
                elif solver.Value(self.shifts[(m, d, ShiftType.PM_HC)]) == 1:
                    days.append(WorkCode.HC)
                elif solver.Value(self.shifts[(m, d, ShiftType.PM_IA)]) == 1:
                    days.append(WorkCode.IA)
                else:
                    days.append("")

            result_schedule.append({
                "name": member_name,
                "days": days
            })

        return {
            "status": "success",
            "schedule": result_schedule
        }
