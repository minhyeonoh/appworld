import re

DEFAULT_SECTION_HEADERS = [
  "SYSTEM:", 
  "USER:", 
  "ASSISTANT:", 
  "ENVIRONMENT:"
]
def parse_messages(
  text: str,
  start: list[str] = DEFAULT_SECTION_HEADERS,
  end: list[str] = DEFAULT_SECTION_HEADERS,
):
  # start_pattern = f"({})"
  start = '|'.join(re.escape(header) for header in start)
  end   = '|'.join(re.escape(header) for header in end) 
  pattern = f"({start})(?:[ \t]*\n)?(.*?)(?={end}|$)"
  parsed = []
  for header, content in re.findall(pattern, text, re.DOTALL):
    parsed.append((header.strip(), content.rstrip()))
  return parsed


# text = """
# SYSTEM:
# 첫 번째 A 내용입니다.
# USER:
# 여기는 B로 시작된 내용입니다.
# ASSISTANT:
# 또 다시 A가 나왔습니다.
# USER:
# C는 시작 목록에 없으므로 무시되거나 종료 조건으로만 쓰입니다.
# """

# with open("my/response.txt") as fin:
#   print(parse_messages(fin.read()))



import re
from pydantic import BaseModel, Field

class StackFrame(BaseModel):
    """하나의 스택 프레임 정보 (어떤 파일, 몇 번째 줄, 어떤 코드)"""
    filename: str
    lineno: int
    name: str  # 함수 이름 또는 <module>
    code: str  # 실행된 코드 라인
    
    # def __str__(self):
    #     return f"File '{self.filename}', line {self.lineno}, in {self.name}\n  {self.code}"

class Error(BaseModel):
    """파싱된 전체 에러 정보"""
    type: str = Field(description="예외 타입 (예: ValueError, Exception)")
    message: str = Field(description="상세 에러 메시지")
    traceback: list[StackFrame] = Field(description="호출 스택 리스트")
    raw_traceback: str = Field(description="원본 Traceback 문자열 (참고용)")

    @property
    def last_frame(self) -> StackFrame | None:
        """가장 마지막(에러 발생 지점) 프레임 반환"""
        return self.traceback[-1] if self.traceback else None

class Observation(BaseModel):
    at: str  # (AfterDef | AfterCall 등은 실제 객체나 문자열로 처리)
    variables: list[dict] # 간단히 dict로 표현
    error: Error | None = None

def parse_traceback_string(tb_str: str) -> Error:
    """
    Python Traceback 문자열을 파싱하여 구조화된 Error 객체를 반환합니다.
    """
    # 1. 스택 프레임 파싱 (File "...", line ..., in ...)
    # Python 3.11+의 ^^^^ 라인은 무시하도록 처리

    # 이 정규표현식은 Python의 **Traceback 문자열**에서 하나의 **스택 프레임(Stack Frame)** 정보를 추출하기 위해 설계되었습니다.
    # 크게 **"헤더 부분(파일, 라인, 함수명)"**과 **"코드 부분(실제 소스코드)"** 두 덩어리로 나뉩니다. 하나씩 뜯어서 설명해 드릴게요.
    # ---
    # ### **2. 상세 토큰 설명**
    # #### **Part 1: 헤더 파싱 (File, Line, Scope)**
    # 1. `File "`
    #     * 문자열 `File "`을 그대로 찾습니다. (Traceback의 시작점)
    # 2. `(?P<file>[^"]+)`
    #     * **`(?P<name>...)`**: **Named Capture Group**입니다. 찾은 값을 `file`이라는 이름으로 저장합니다.
    #     * **`[^"]+`**: 큰따옴표(`"`)가 **아닌** 문자가 1개 이상 연속되는 구간을 찾습니다. (즉, 파일 경로 추출)
    # 3. `", line `
    #     * 문자열 `", line `을 그대로 찾습니다.
    # 4. `(?P<line>\d+)`
    #     * **`\d+`**: 숫자(digit)가 1개 이상인 구간입니다. (라인 번호 추출)
    # 5. `, in `
    #     * 문자열 `, in `을 그대로 찾습니다.
    # 6. `(?P<scope>.+?)`
    #     * **`.+?`**: 아무 문자나 1개 이상 매칭하되, **Non-greedy(최소 매칭)**하게 찾습니다.
    #     * 바로 뒤에 나오는 `\n`(줄바꿈)을 만나기 전까지만 찾아서 함수/모듈 이름을 `scope`에 저장합니다.
    # #### **Part 2: 코드 파싱 (Code)**
    # 7. `\n\s+`
    #     * **`\n`**: 줄바꿈 문자.
    #     * **`\s+`**: 공백(들여쓰기)이 1개 이상.
    #     * Traceback에서 실제 코드는 항상 다음 줄에 들여쓰기 된 상태로 나오므로 이를 처리합니다.
    # 8. `(?P<code>.+?)`
    #     * 실제 소스 코드를 `code`라는 이름으로 추출합니다.
    #     * **`.+?`**: 아무 문자나 매칭하되 최소한으로 매칭합니다. (어디까지? 바로 뒤의 **Lookahead 조건**을 만날 때까지)
    # #### **Part 3: 종료 조건 (Positive Lookahead)**
    # 이 부분이 가장 핵심입니다. **"코드가 어디서 끝나는지"**를 결정합니다.
    # 9. `(?=\n\s*File|\n\s*[^\s]+:|$)`
    #     * **`(?= ... )`**: **전방 탐색(Positive Lookahead)**입니다. "뒤에 이런 패턴이 오는지 확인만 하고, 문자를 소비(Consume)하지는 않는다"는 뜻입니다.
    #     * 즉, `code` 그룹은 **다음 세 가지 조건 중 하나**가 나오기 직전까지만 매칭됩니다.
    #     **조건 (OR 연산 `|` 로 연결됨):**
    #         1. `\n\s*File`: 다음 스택 프레임의 시작(`File "..."`)이 나올 때.
    #         2. `\n\s*[^\s]+:`: 에러 메시지의 시작(예: `Exception:` 또는 `ValueError:`)이 나올 때.
    #         3. `$`: 문자열의 끝(End of String)일 때.
    # ### **팁: `re.DOTALL**`
    # 코드에 `re.DOTALL` 플래그를 사용하셨는데, 이는 `.`이 줄바꿈 문자(`\n`)도 포함하게 만듭니다. 덕분에 `scope`나 `code` 부분에서 줄바꿈이 섞여 있어도 유연하게 잡아낼 수 있지만, 그렇기에 **Part 3의 종료 조건(Lookahead)**이 더더욱 중요해집니다. 종료 조건이 없으면 끝까지 다 잡아먹어 버리기 때문입니다.
    frame_pattern = re.compile(
        r'File "(?P<file>[^"]+)", line (?P<line>\d+), in (?P<scope>.+?)\n\s+(?P<code>.+?)(?=\n\s*File|\n\s*[^\s]+:|$)',
        re.DOTALL
    )
    
    frames = []
    # Traceback 헤더 이후부터 파싱하기 위해 split 시도 (없으면 전체 사용)
    body = tb_str.split("Traceback (most recent call last):")[-1]
    if "Execution failed. Traceback:" in tb_str:
         body = tb_str.split("Execution failed. Traceback:")[-1]

    for match in frame_pattern.finditer(body):
        # 코드 부분에서 ^^^^ 같은 에러 마커 제거
        code_lines = match.group("code").split('\n')
        clean_code = code_lines[0].strip() # 첫 줄이 실제 코드
        
        frames.append(StackFrame(
            filename=match.group("file"),
            lineno=int(match.group("line")),
            name=match.group("scope"),
            code=clean_code
        ))

    # 2. Exception 타입과 메시지 파싱
    # 스택 프레임들이 끝나고 나오는 마지막 부분이 에러 메시지
    # 예: "Exception: Response status code is 422:..."
    
    # 마지막 프레임 이후의 텍스트 찾기
    last_frame_end = 0
    for match in frame_pattern.finditer(body):
        last_frame_end = match.end()
    
    exception_part = body[last_frame_end:].strip()
    
    # ^^^^^ 같은 마커가 남았을 수 있으니 제거
    exception_part = re.sub(r'^\s*\^+\s*\n', '', exception_part, flags=re.MULTILINE).strip()

    if ":" in exception_part:
        exc_type, exc_msg = exception_part.split(":", 1)
    else:
        exc_type = "Error"
        exc_msg = exception_part

    return Error(
        type=exc_type.strip(),
        message=exc_msg.strip(),
        traceback=frames,
        raw_traceback=tb_str
    )

raw_error = """Execution failed. Traceback:
  File "<python-input>", line 148, in <module>
    raise e
  File "<python-input>", line 144, in <module>
    main()
  File "<python-input>", line 121, in main
    owe_list = read_owe_list_from_csv()
                   ^^^^^^^^^^^^^^^^^^^^^^^^
  File "<python-input>", line 110, in read_owe_list_from_csv
    file_content = file_system.show_file(
                   ^^^^^^^^^^^^^^^^^^^^^^
Exception: Response status code is 422:
{"message":"File with path /owe_list.csv is not available in your account."}"""

# 파싱 수행
# error_obj = parse_traceback_string(raw_error)
# for frame in error_obj.traceback:
#     print(frame)