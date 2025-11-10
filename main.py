"""
스케줄 생성기 메인 실행 파일
"""

import json
import sys
from schedule_generator import ScheduleGenerator


def test_from_file(filepath: str):
    """JSON 파일에서 테스트 데이터를 읽어서 스케줄 생성"""
    print(f"[입력 파일] {filepath}")
    print("=" * 80)

    # 입력 데이터 로드
    with open(filepath, 'r', encoding='utf-8') as f:
        input_data = json.load(f)

    print(f"[근무자 수] {len(input_data['schedule'])}명")
    print(f"[대상 월] {input_data['option']['targetMonth']}")

    # 개인별 휴무 일수 표시
    day_off_individual = input_data['option'].get('dayOffIndividual', {})
    if day_off_individual:
        print(f"[개인별 휴무]")
        for name, days in day_off_individual.items():
            print(f"  - {name}: {days}일")

    print(f"[연속 휴무 고려] {input_data['option']['dayOffStream']}")
    print(f"[근무 코드 균등] {input_data['option']['workCodeAverage']}")
    print(f"[연속 근무 제한] AM {input_data['option']['continuousWorkLimit']['am']}일, "
          f"PM {input_data['option']['continuousWorkLimit']['pm']}일, "
          f"Total {input_data['option']['continuousWorkLimit']['total']}일")
    print("=" * 80)
    print()

    # 스케줄 생성 (5개)
    print("[5개의 다른 스케줄 생성 중...]")
    generator = ScheduleGenerator(input_data)
    result = generator.generate(num_solutions=5)

    # 결과 출력
    print()
    print("=" * 80)
    if result["status"] == "success":
        print(f"[SUCCESS] {result['count']}개의 스케줄 생성 성공!")
        print("=" * 80)
        print()

        # 각 스케줄 출력
        for idx, schedule in enumerate(result["schedules"], 1):
            print(f"\n{'='*80}")
            print(f"스케줄 #{idx}")
            print(f"{'='*80}")
            print_schedule(schedule, input_data['option']['targetMonth'])

        # 결과 파일 저장
        output_file = "output_schedules.json"
        with open(output_file, 'w', encoding='utf-8') as f:
            json.dump(result, f, ensure_ascii=False, indent=2)
        print()
        print(f"[결과 저장] {output_file} ({result['count']}개 스케줄)")

    else:
        print(f"[ERROR] 스케줄 생성 실패: {result['message']}")


def print_schedule(schedule, target_month):
    """스케줄 출력"""
    from datetime import datetime

    year, month = map(int, target_month.split("-"))
    if month == 12:
        next_month = datetime(year + 1, 1, 1)
    else:
        next_month = datetime(year, month + 1, 1)
    last_day = datetime(year, month, 1)
    num_days = (next_month - last_day).days

    # 헤더
    print(f"{'근무자':<10}", end="")
    for d in range(1, num_days + 1):
        print(f"{d:>4}", end="")
    print()
    print("-" * (10 + num_days * 4))

    # 각 근무자 스케줄
    for member in schedule:
        print(f"{member['name']:<10}", end="")
        for day_code in member['days']:
            code_display = day_code if day_code else "-"
            print(f"{code_display:>4}", end="")
        print()

    print()

    # 통계
    print("[통계]")
    for member in schedule:
        name = member['name']
        days = member['days']

        z_count = days.count('Z')
        hc_count = days.count('HC')
        ia_count = days.count('IA')
        r_count = days.count('R') + days.count('RQ')

        print(f"  {name}: Z={z_count}, HC={hc_count}, IA={ia_count}, 휴무={r_count}")


def start_api_server():
    """Flask API 서버 시작"""
    from flask import Flask, request, jsonify
    from flask_cors import CORS

    app = Flask(__name__)
    CORS(app)

    @app.route('/generate', methods=['POST'])
    def generate_schedule():
        """스케줄 생성 API (5개의 다른 스케줄 반환)"""
        try:
            input_data = request.json
            num_solutions = input_data.get('numSolutions', 5)  # 기본값 5개

            generator = ScheduleGenerator(input_data)
            result = generator.generate(num_solutions=num_solutions)
            return jsonify(result)
        except Exception as e:
            return jsonify({
                "status": "error",
                "message": str(e)
            }), 500

    @app.route('/health', methods=['GET'])
    def health_check():
        """헬스 체크"""
        return jsonify({"status": "ok"})

    print("[Flask API 서버 시작]")
    print("Endpoint: http://localhost:5000/generate")
    print("Health Check: http://localhost:5000/health")
    app.run(host='0.0.0.0', port=5000, debug=True)


if __name__ == "__main__":
    if len(sys.argv) > 1:
        if sys.argv[1] == "server":
            # API 서버 모드
            start_api_server()
        else:
            # 파일 테스트 모드
            test_from_file(sys.argv[1])
    else:
        # 기본: test_input.json 사용
        test_from_file("test_input.json")
