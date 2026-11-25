# 열차 고장 유사 사례 검색

FRACAS 운행장애 기록 CSV에서 고장 증상과 비슷한 사례 상위 5건을 찾는 로컬 웹앱입니다. AI 모델이 준비되면 자동으로 **키워드 + AI 의미 검색(하이브리드)**을 쓰고, 준비 전이거나 실패하면 **키워드 검색**으로 검색합니다. 모든 처리는 이 PC에서만 이루어지며, CSV·사례 원문·임베딩·검색어를 외부로 보내지 않습니다.

## 화면

지금 발생한 고장을 기록하는 화면이며, 과거 사례는 참고용으로 함께 보여줍니다.

- **왼쪽 위 · 고장 증상**: 증상을 입력하거나 마이크를 눌러 말하면 검색합니다. 위쪽 상태 표시로 검색 방식(키워드 + AI / AI 준비 중 / 키워드)을 알 수 있습니다.
- **왼쪽 아래 · 유사 과거 사례**: 유사도 상위 5건을 최근 발생 순으로 보여줍니다. 행마다 번호, 발생 일시(`고장발생일자` `고장발생시각`), 발생 장소(`발생장소명`), 원문(`운행장애개요내용`), 정비유형과 유사도 순위 태그가 붙습니다. 검색어와 겹치는 표현은 형광펜으로 표시합니다. 행을 누르면 관리번호(`FRACAS관리번호`), 차량 수(`열차차량수`), 시발·종착역(`시발역명`, `종착역명`), 당시 조치가 펼쳐지고, 그 사례가 참고 사례로 지정됩니다.
- **오른쪽 · 고장 기록**: 두 가지 방식 중 고를 수 있습니다.
  - `검색한 증상으로 기록`: 왼쪽에서 검색한 증상과 펼쳐 본 참고 사례가 자동으로 들어갑니다.
  - `직접 기록`: 검색과 관계없이 증상을 직접 쓰거나 말합니다. 참고 사례는 붙지 않습니다.
  - 조치 내용(필수, 음성 입력 가능)과 장소·차량(선택)을 넣고 `기록 저장`을 누르면 아래 최근 기록에 보입니다.
- **지연 통계**: 원본의 `고장지연분간시간수`(지연 분), `지장열차수량`을 그대로 읽습니다. 유사 사례 목록 위에 평균·최대 지연과 지연 발생 건수를, 각 사례에 지연 분과 지장열차 수를 보여줍니다. 값이 없는 사례는 통계에서 빼고 `미기록`으로 표시합니다.
- **장치 분류**: `classify.py`의 키워드 규칙으로 원문을 출입문, 신호·제어, 제동, 전력·보조전원, 견인·추진, 냉난방, 공기·압축기, 연기·냄새, 객실·방송, 기타로 자동 분류합니다(학습 모델이 아닌 단어 규칙이라 틀릴 수 있음). 실제 데이터 7,503건 중 약 20%(1,472건)가 '기타'로 남습니다. 고장 기록을 저장할 때도 증상·조치로 `장치분류`를 자동으로 붙입니다.
- **조치 정보**: CSV에 `정비단`, `정비유형`, `조치내용`, `조치구분` 열이 있을 때만 표시합니다. `조치구분`이 "가상 조치 (데모)"면 "시연용 데모 데이터, 실제 정비 기록 아님" 안내를 붙입니다. 원본 CSV에는 이 열이 없어 조치 정보가 나오지 않습니다.
- 빈 값은 `미기록`으로, 시연용으로 채운 값은 `가상`으로 표시합니다. AI를 쓸 수 없으면 원인을 화면에 표시하고 키워드 검색은 그대로 씁니다.

## 1. 키워드 검색만 실행 (추가 설치 없음)

Python 3.10 이상이 필요합니다. VS Code에서 이 폴더를 열고 PowerShell 터미널에서 실행합니다.

```powershell
python app.py --csv "C:\Users\user\Downloads\FRACAS_20220830_utf8.csv" --no-ai
```

브라우저에서 `http://127.0.0.1:8000`을 엽니다. 종료는 터미널에서 Ctrl+C입니다. 포트가 사용 중이면 `--port 8001`을 붙입니다.

## 2. AI 의미 검색 설치 (처음 한 번)

프로젝트 안의 가상 환경(`.venv`)에만 설치합니다. 인터넷이 필요한 단계는 이 설치와 모델 다운로드뿐입니다.

```powershell
python -m venv .venv
.\.venv\Scripts\python.exe -m pip install --retries 10 --timeout 120 torch --index-url https://download.pytorch.org/whl/cpu
.\.venv\Scripts\python.exe -m pip install --retries 10 --timeout 120 -r requirements-ai.txt
.\.venv\Scripts\python.exe download_model.py
```

`download_model.py`는 공개 모델 [intfloat/multilingual-e5-small](https://huggingface.co/intfloat/multilingual-e5-small)의 필요한 파일만 `.models\multilingual-e5-small`에 받습니다(약 470MB). 중간에 끊기면 같은 명령을 다시 실행하면 이어서 받습니다. `--check`를 붙이면 다운로드 없이 파일이 다 있는지만 검사합니다.

## 3. AI 의미 검색과 함께 실행

```powershell
.\.venv\Scripts\python.exe app.py --csv "C:\Users\user\Downloads\FRACAS_20220830_utf8.csv"
```

접속 주소가 먼저 표시되고, 키워드 검색은 바로 쓸 수 있습니다. 사례 임베딩은 서버 시작 시 한 번만 만들어 메모리에 보관합니다(CPU에서 약 3~4분, 파일로 저장하지 않음). 준비가 끝나면 화면 오른쪽 위 표시가 새로고침 없이 `키워드 + AI 의미 검색`으로 바뀌고, 이후 검색은 하이브리드로 처리됩니다. 실패하면 `[AI] 로드 실패: 원인`이 터미널과 화면에 표시됩니다.

데모 조치 열이 들어 있는 CSV로 실행하려면 `--csv` 경로만 바꿉니다.

```powershell
.\.venv\Scripts\python.exe app.py --csv "C:\Users\user\Downloads\FRACAS_20220830_with_demo_maintenance.csv"
```

## 음성 입력 (faster-whisper)

- **음성 입력**: 마이크 버튼을 누르고 말한 뒤 다시 누르면 받아쓴 글자가 들어갑니다(최대 30초). 고장 증상 칸에서는 바로 검색합니다.
- **고장 기록 저장**: 기록은 원본과 별개인 `Downloads\현장고장기록.csv`에 `기록번호(날짜-순번), 저장일시, 발생일시, 발생장소, 차량번호, 고장증상, 장치분류, 조치내용, 참고사례`로 쌓입니다. 고장 증상과 조치 내용은 필수입니다. 증상 마이크에 "장소 용산역, 차량 311-14, 증상 출입문 닫힘 불량, 조치 구동부 교체 후 정상 확인"처럼 한 번에 말하면 장소·차량·증상·조치라는 말머리를 기준으로 각 칸에 나눠 넣습니다(말머리가 없으면 증상 칸에 넣음). 다른 위치에 저장하려면 `--records 경로`를 붙입니다.
- 음성은 [faster-whisper small](https://huggingface.co/Systran/faster-whisper-small) 모델로 이 PC의 CPU에서 받아쓰며, 녹음은 메모리에서만 쓰고 저장하거나 외부로 보내지 않습니다. 정비 용어(BC압, SIV, MCB 등)를 잘 알아듣도록 힌트 문장을 함께 줍니다.
- 처음 한 번 모델을 받습니다(약 480MB). 처음 마이크를 쓸 때 브라우저가 권한을 물으면 허용합니다.

```powershell
.\.venv\Scripts\python.exe -m pip install --retries 10 --timeout 120 faster-whisper
.\.venv\Scripts\python.exe -c "from huggingface_hub import snapshot_download; snapshot_download('Systran/faster-whisper-small', local_dir='.models/faster-whisper-small', allow_patterns=['config.json','model.bin','tokenizer.json','vocabulary.txt'])"
```

음성을 끄려면 `--no-voice`를 붙입니다. 모델이 없으면 마이크 버튼이 나타나지 않고, 원인은 터미널에 표시됩니다.

## 시연용 가상 값 CSV

시연 화면에서 빈 칸 대신 값을 보여주고 싶을 때만 사용합니다. 발생 장소, 시발·종착역, 차량 수, 차량 도입일의 빈 칸을 가상 값으로 채운 **새 파일**을 만듭니다(입력 파일은 바꾸지 않음). 역 이름은 실제 노선의 역 중에서 고르고, 차량 수는 4~20량, 도입일은 1995년부터 고장 1년 전 사이에서 정합니다. 데모 조치의 정비단은 발생 장소 지역에 따라 실제 코레일 차량정비단 4곳(수도권·대전·부산·호남철도차량정비단) 중 하나로 배정합니다. 실제 정비 이력이 아니라 시연용 배정입니다. 채운 칸은 `가상채움열` 열에 기록되며, 화면에 노란 **가상** 표시가 붙습니다. 실제 기록이 아니므로 시연 외의 용도로 쓰지 마세요.

```powershell
python make_demo_csv.py "C:\Users\user\Downloads\FRACAS_20220830_with_demo_maintenance.csv" "C:\Users\user\Downloads\FRACAS_20220830_demo_filled.csv"
.\.venv\Scripts\python.exe app.py --csv "C:\Users\user\Downloads\FRACAS_20220830_demo_filled.csv"
```

## 검색 방식

- **키워드 검색**: 검색어와 원문을 단어와 연속 두 글자(예: `출입문` → `출입`, `입문`)로 나눈 뒤 TF-IDF 코사인 유사도로 비교합니다. 여러 기록에 흔한 표현일수록 가중치가 낮습니다.
- **AI 의미 검색**: E5 모델로 검색어에 `query: `, 사례 원문에 `passage: `를 붙여 임베딩하고, 정규화된 벡터의 코사인 유사도로 순위를 매깁니다.
- **하이브리드 결합(RRF)**: 키워드 순위와 의미 순위 각각의 상위 100위 안에서 `1 / (60 + 순위)` 점수를 더해 다시 정렬합니다. 점수 크기가 다른 두 방식을 순위만으로 공평하게 섞습니다.

## 비교와 테스트

```powershell
.\.venv\Scripts\python.exe compare.py --csv "C:\Users\user\Downloads\FRACAS_20220830_utf8.csv"
.\.venv\Scripts\python.exe -m unittest -v test_app test_speech test_classify
```

`compare.py`는 개발·평가용으로, 세 검색어를 키워드와 하이브리드로 각각 검색해 상위 5건을 터미널에만 출력합니다. `test_app.py`는 가짜(모의) 모델과 작은 예시 CSV로 동작만 확인하며, 실제 모델의 검색 품질을 뜻하지 않습니다.

## 한계와 향후 과제

- 유사 사례 검색은 앱을 시작할 때 읽은 CSV만 대상으로 합니다. 화면에서 새로 저장한 고장 기록(`현장고장기록.csv`)은 검색에 반영되지 않으며, 이를 검색 대상에 포함하는 것은 향후 과제입니다.
- 장치 분류는 단어 규칙이라 틀릴 수 있고, 약 20%는 '기타'로 남습니다.
- 음성 인식은 현장 소음과 발음에 따라 정확도가 달라지므로 저장 전 확인이 필요합니다.
- 세 검색어 비교 결과만으로 전체 검색 정확도를 판단할 수 없습니다.

## 파일

| 파일 | 역할 |
|---|---|
| `app.py` | 웹 서버와 검색 API |
| `static/index.html` | 검색 화면 |
| `keyword_search.py` | CSV 읽기, 키워드 검색 |
| `semantic.py` | AI 의미 검색, 모델 파일 검사, 순위 결합 |
| `download_model.py` | 공개 모델 다운로드와 완전성 검사 |
| `compare.py` | 두 방식 비교 출력 |
| `speech.py` | 음성 받아쓰기, 현재 고장 기록 저장 |
| `test_speech.py` | 음성 기능 모의 테스트 |
| `classify.py` | 장치 자동 분류 규칙 |
| `test_classify.py` | 장치 분류·지연 요약 테스트 |
| `make_demo_csv.py` | 빈 칸을 가상 값으로 채운 시연용 CSV 생성 |
| `test_app.py` | 모의 모델 테스트 |
