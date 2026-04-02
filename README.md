# ![App Icon](icon.ico) YouTube Audio Extractor Pro
1. 개요
유튜브 영상의 오디오를 추출하고 파형(Waveform) 기반 UI를 통해 지정 구간을 WAV 파일로 저장하는 데스크톱 애플리케이션임.

2. 주요 기능
오디오 다운로드: yt-dlp 기반 음원 고속 추출.

구간 편집: 파형 UI 클릭 및 드래그를 통한 구간 선택 (최소 0.1초 단위).

무손실 컷팅: Zero-crossing 스냅 기술로 절단면 팝핑 노이즈(Popping noise) 발생 방지.

부가 기능: 선택 구간 반복 재생(Loop), 볼륨 조절, 마우스 휠 줌(Zoom).

히스토리 관리: 최근 사용 URL 자동 저장 및 재호출 지원.

3. 시스템 요구사항
OS: Windows, macOS, Linux

Python: 3.8 이상 (Python 3.14 환경 호환성 확인 완료)

필수 엔진: FFmpeg (오디오 트랜스코딩 및 구간 추출용). 시스템 PATH에 등록되어 있거나 실행 파일과 동일한 경로에 위치해야 함.

4. 설치 및 실행
4.1. 필수 라이브러리 설치
Bash
pip install PyQt6 yt-dlp numpy
4.2. 프로그램 실행
Bash
python main.py
5. 조작 방법 및 단축키
좌클릭: 재생 헤드 이동.

드래그: 오디오 구간 선택 (100ms 이상).

마커 드래그: 선택 구간 시작/종료점 미세 조정.

마우스 휠: 파형 가로 확대/축소.

Space: 재생 / 일시정지.

L: 구간 반복 재생(Loop) 토글.

6. 빌드 가이드 (PyInstaller)
6.1. 기본 빌드 (FFmpeg 미포함)
PowerShell
python -m PyInstaller --noconsole --onefile --add-data "icon.ico;." --icon="icon.ico" main.py
6.2. 독립형 빌드 (FFmpeg 포함, 권장)
PowerShell
python -m PyInstaller --noconsole --onefile --add-data "icon.ico;." --add
